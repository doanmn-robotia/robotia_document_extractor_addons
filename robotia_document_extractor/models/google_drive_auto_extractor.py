# -*- coding: utf-8 -*-

import json
import time
import base64
import logging
import traceback
from odoo import api, models

_logger = logging.getLogger(__name__)


class GoogleDriveAutoExtractor(models.AbstractModel):
    _name = 'google.drive.auto.extractor'
    _description = 'Google Drive Auto Extractor Service'

    @api.model
    def process_drive_files(self):
        """Main cron method - Process max 3 PDF files from Drive folders"""
        try:
            ICP = self.env['ir.config_parameter'].sudo()

            # Check if enabled
            if not ICP.get_param('google_drive_enabled'):
                _logger.info("Google Drive integration is disabled")
                return

            # Get folder IDs
            form01_folder = ICP.get_param('google_drive_form01_folder_id')
            form02_folder = ICP.get_param('google_drive_form02_folder_id')
            processed_folder = ICP.get_param('google_drive_processed_folder_id')

            if not all([form01_folder, form02_folder, processed_folder]):
                _logger.warning("Google Drive folders not fully configured")
                return

            # Scan folders for new files (max 4 total)
            files_to_process = self._scan_folders(form01_folder, form02_folder, limit=4)

            if not files_to_process:
                _logger.info("No new files to process")
                return

            _logger.info(f"Found {len(files_to_process)} files to process")

            # Process each file
            for file_data in files_to_process:
                self._process_single_file(file_data, processed_folder)
                time.sleep(2)  # Avoid API rate limit

        except Exception as e:
            _logger.exception("Google Drive cron job failed: %s", e)

    def _scan_folders(self, form01_folder, form02_folder, limit=4):
        """
        Scan both folders with balanced strategy
        - Try to get 2 files from each folder (if available)
        - If one folder has fewer files, take more from the other
        - Maximum 4 files per run
        """
        drive_service = self.env['google.drive.service']
        log_model = self.env['google.drive.extraction.log']

        # Get already processed file IDs
        processed_ids = log_model.search([
            ('drive_file_id', '!=', False),
            ('status', 'in', ['success', 'processing'])
        ]).mapped('drive_file_id')

        form01_files = []
        form02_files = []

        # Scan Form 01 folder - try to get up to 4 (may need all if Form 02 is empty)
        try:
            result = drive_service.list_files(
                folder_id=form01_folder,
                query="mimeType='application/pdf'",
                page_size=limit  # Get up to 4 in case Form 02 has none
            )
            for f in result.get('files', []):
                if f['id'] not in processed_ids:
                    f['document_type'] = '01'
                    form01_files.append(f)
        except Exception as e:
            _logger.error("Error scanning Form 01 folder: %s", e)

        # Scan Form 02 folder - try to get up to 4
        try:
            result = drive_service.list_files(
                folder_id=form02_folder,
                query="mimeType='application/pdf'",
                page_size=limit
            )
            for f in result.get('files', []):
                if f['id'] not in processed_ids:
                    f['document_type'] = '02'
                    form02_files.append(f)
        except Exception as e:
            _logger.error("Error scanning Form 02 folder: %s", e)

        # Balanced selection strategy
        files_to_process = []

        # Try to get 2 from each folder first
        form01_target = min(2, len(form01_files))
        form02_target = min(2, len(form02_files))

        # Take from Form 01
        files_to_process.extend(form01_files[:form01_target])

        # Take from Form 02
        files_to_process.extend(form02_files[:form02_target])

        # If we have less than 4 files, try to fill up from remaining files
        remaining_slots = limit - len(files_to_process)

        if remaining_slots > 0:
            # Take more from Form 01 if available
            form01_remaining = form01_files[form01_target:]
            files_to_process.extend(form01_remaining[:remaining_slots])
            remaining_slots = limit - len(files_to_process)

            if remaining_slots > 0:
                # Take more from Form 02 if still needed
                form02_remaining = form02_files[form02_target:]
                files_to_process.extend(form02_remaining[:remaining_slots])

        _logger.info(
            "Scan result: Form 01: %d files, Form 02: %d files. Selected: %d files total",
            len(form01_files), len(form02_files), len(files_to_process)
        )

        return files_to_process[:limit]  # Safety cap at 4

    def _process_single_file(self, file_data, processed_folder):
        """Process a single file: download, extract, create record, move"""
        file_id = file_data['id']
        file_name = file_data['name']
        document_type = file_data['document_type']

        # Create log record
        log = self.env['google.drive.extraction.log'].create({
            'drive_file_id': file_id,
            'file_name': file_name,
            'document_type': document_type,
            'status': 'processing',
        })

        try:
            _logger.info(f"Processing {file_name} (type: {document_type})")

            # 1. Download PDF from Drive
            drive_service = self.env['google.drive.service']
            pdf_binary = drive_service.download_file(file_id)

            # 2. Extract data using AI
            extraction_service = self.env['document.extraction.service']
            extracted_data = extraction_service.extract_pdf(
                pdf_binary=pdf_binary,
                document_type=document_type,
            )

            # 3. Create ir.attachment
            attachment = self.env['ir.attachment'].create({
                'name': file_name,
                'type': 'binary',
                'datas': base64.b64encode(pdf_binary),
                'res_model': 'document.extraction',
                'res_id': 0,
                'public': False,
                'mimetype': 'application/pdf',
                'google_drive_id': file_id,
            })

            # 4. Build record values using helper
            helper = self.env['extraction.helper']
            vals = helper.build_extraction_values(
                extracted_data=extracted_data,
                attachment=attachment,
                document_type=document_type,
                file_id=file_id,
                log_id=log.id
            )

            # 5. Create document.extraction record
            record = self.env['document.extraction'].create(vals)

            # 6. Link attachment to record
            attachment.write({'res_id': record.id})

            # 7. Move file to Processed folder
            drive_service.move_file(file_id, processed_folder)

            # 8. Update log - SUCCESS
            log.write({
                'status': 'success',
                'extraction_record_id': record.id,
                'ai_response_json': json.dumps(extracted_data, ensure_ascii=False, indent=2),
            })

            self.env.cr.commit()
            _logger.info(f"Successfully processed {file_name} -> Record ID: {record.id}")

        except Exception as e:
            # Update log - ERROR
            log.write({
                'status': 'error',
                'error_message': f"{str(e)}\n\n{traceback.format_exc()}",
            })
            self.env.cr.rollback()
            _logger.error(f"Failed to process {file_name}: {e}")
