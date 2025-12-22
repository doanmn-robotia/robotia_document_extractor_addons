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

    def _scan_single_folder(self, folder_id, limit, additional_vals=None):
        """
        Scan a single Google Drive folder for PDF files
        
        Args:
            folder_id (str): Google Drive folder ID
            limit (int): Maximum number of files to fetch
            additional_vals (dict): Additional metadata to add to each file (e.g., {'document_type': '01'})
            
        Returns:
            list: List of file metadata dicts
        """
        drive_service = self.env['google.drive.service']
        files = []
        
        try:
            result = drive_service.list_files(
                folder_id=folder_id,
                query="mimeType='application/pdf'",
                page_size=limit
            )
            
            for f in result.get('files', []):
                # Update file metadata with additional values
                if additional_vals:
                    f.update(additional_vals)
                
                files.append(f)
                
        except Exception as e:
            doc_type = additional_vals.get('document_type', 'Unknown') if additional_vals else 'Unknown'
            _logger.error(f"Error scanning Form {doc_type} folder: {e}")
        
        return files

    def _ensure_too_large_folder(self, processed_folder_id):
        """
        Ensure 'TooLarge' subfolder exists in processed folder
        Creates it if it doesn't exist

        Args:
            processed_folder_id (str): Parent processed folder ID

        Returns:
            str: Too large folder ID
        """
        drive_service = self.env['google.drive.service']

        # Search for existing 'TooLarge' subfolder
        existing_folders = drive_service.search_files(
            search_term='TooLarge',
            folder_id=processed_folder_id,
            mime_type='application/vnd.google-apps.folder',
            page_size=1
        )

        if existing_folders and len(existing_folders) > 0:
            folder_id = existing_folders[0]['id']
            _logger.info(f"Found existing TooLarge folder: {folder_id}")
            return folder_id

        # Create new folder
        result = drive_service.create_folder(
            folder_name='TooLarge',
            parent_folder_id=processed_folder_id
        )

        folder_id = result['id']
        _logger.info(f"Created TooLarge folder: {folder_id}")
        return folder_id

    def _handle_oversized_file(self, file_data, log, processed_folder):
        """
        Check if file exceeds size limit and handle it if so

        Args:
            file_data (dict): File metadata from Drive API (must contain 'size' field)
            log (recordset): google.drive.extraction.log record (status='processing')
            processed_folder (str): Processed folder ID (parent for TooLarge subfolder)

        Returns:
            bool: True if file was oversized and handled successfully, False if file size is OK
        """
        try:
            # Read max file size config
            ICP = self.env['ir.config_parameter'].sudo()
            max_size_mb = int(ICP.get_param('google_drive_max_file_size_mb', 30))
            max_size_bytes = max_size_mb * 1024 * 1024

            # Get file size from metadata
            file_size = int(file_data.get('size', 0))

            # Check if file exceeds limit
            if file_size <= max_size_bytes:
                return False  # File size is OK, continue normal processing

            # File is oversized - handle it
            file_name = file_data.get('name', 'Unknown')
            file_id = file_data['id']
            size_mb = round(file_size / (1024 * 1024), 2)

            _logger.info(
                f"File '{file_name}' ({size_mb}MB) exceeds limit ({max_size_mb}MB) - handling as oversized"
            )

            # Ensure TooLarge folder exists
            drive_service = self.env['google.drive.service']
            too_large_folder_id = self._ensure_too_large_folder(processed_folder)

            # Move file to TooLarge folder
            drive_service.move_file(file_id, too_large_folder_id)

            # Update log record
            log.write({
                'status': 'skipped_too_large',
                'error_message': f'File size ({size_mb}MB) exceeds configured limit ({max_size_mb}MB)'
            })

            self.env.cr.commit()
            _logger.info(f"Moved oversized file '{file_name}' to TooLarge folder")

            return True  # File was oversized and handled

        except Exception as e:
            file_name = file_data.get('name', 'Unknown')
            _logger.error(f"Error checking/handling file size for '{file_name}': {e}")
            return False  # On error, allow normal processing to continue

    def _handle_already_processed_file(self, file_data, processed_folder):
        """
        Check if file was already processed and move it to processed folder if needed

        Args:
            file_data (dict): File metadata from Drive API
            processed_folder (str): Processed folder ID

        Returns:
            bool: True if file was already processed, False if this is a new file
        """
        try:
            file_id = file_data['id']
            file_name = file_data.get('name', 'Unknown')

            # Check if file already has a log record
            log_model = self.env['google.drive.extraction.log']
            existing_log = log_model.search([
                ('drive_file_id', '=', file_id),
                ('status', 'in', ['success', 'processing', 'skipped_too_large'])
            ], limit=1)

            if not existing_log:
                return False  # File not processed yet, continue normal flow

            # File was already processed - move to processed folder if needed
            _logger.info(
                f"File '{file_name}' already processed (status: {existing_log.status}) - "
                f"ensuring it's in correct folder"
            )

            drive_service = self.env['google.drive.service']

            # Determine destination folder based on log status
            if existing_log.status == 'skipped_too_large':
                # Move to TooLarge subfolder
                destination_folder = self._ensure_too_large_folder(processed_folder)
                destination_name = 'TooLarge'
            else:
                # Move to Processed folder
                destination_folder = processed_folder
                destination_name = 'Processed'

            # Move file to destination folder
            drive_service.move_file(file_id, destination_folder)

            _logger.info(f"Moved already-processed file '{file_name}' to {destination_name} folder")

            return True  # File was already processed

        except Exception as e:
            file_name = file_data.get('name', 'Unknown')
            _logger.error(f"Error checking/handling already-processed file '{file_name}': {e}")
            return False  # On error, allow normal processing to continue

    def _scan_folders(self, form01_folder, form02_folder, limit=4):
        """
        Scan both folders with balanced strategy
        - Try to get 2 files from each folder (if available)
        - If one folder has fewer files, take more from the other
        - Maximum 4 files per run
        """
        # Scan both folders using helper method
        form01_files = self._scan_single_folder(
            folder_id=form01_folder,
            limit=limit * 2,
            additional_vals={'document_type': '01'}
        )

        form02_files = self._scan_single_folder(
            folder_id=form02_folder,
            limit=limit * 2,
            additional_vals={'document_type': '02'}
        )

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

        return files_to_process[:limit]  # Safety cap at 4  # Safety cap at 4  # Safety cap at 4  # Safety cap at 4  # Safety cap at 4  # Safety cap at 4

    def _process_single_file(self, file_data, processed_folder):
        """Process a single file: download, extract, create record, move"""
        file_id = file_data['id']
        file_name = file_data['name']
        document_type = file_data['document_type']

        # Check if file was already processed
        if self._handle_already_processed_file(file_data, processed_folder):
            return  # File was already processed and moved, skip

        # Create log record
        log = self.env['google.drive.extraction.log'].create({
            'drive_file_id': file_id,
            'file_name': file_name,
            'document_type': document_type,
            'status': 'processing',
        })

        # Check and handle oversized files
        if self._handle_oversized_file(file_data, log, processed_folder):
            return  # File was oversized and handled, skip normal processing

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
                log_id=log
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
