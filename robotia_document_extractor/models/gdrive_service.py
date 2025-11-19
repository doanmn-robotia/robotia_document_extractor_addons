# -*- coding: utf-8 -*-

import base64
import json
import logging
from odoo import models, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class GDriveService(models.AbstractModel):
    """Service model for Google Drive integration"""
    _name = 'gdrive.service'
    _description = 'Google Drive Integration Service'

    @api.model
    def _get_drive_service(self):
        """
        Initialize and return Google Drive service.

        Returns:
            googleapiclient.discovery.Resource: Google Drive service instance

        Raises:
            UserError: If credentials are not configured or invalid
        """
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except ImportError:
            raise UserError(_(
                'Google Drive API libraries not installed. '
                'Please install: pip install google-api-python-client google-auth'
            ))

        # Get credentials from settings
        credentials_json = self.env['ir.config_parameter'].sudo().get_param(
            'robotia_document_extractor.gdrive_credentials_json'
        )

        if not credentials_json:
            raise UserError(_(
                'Google Drive credentials not configured. '
                'Please configure Service Account JSON in Settings > Document Extractor.'
            ))

        try:
            credentials_dict = json.loads(credentials_json)
            credentials = service_account.Credentials.from_service_account_info(
                credentials_dict,
                scopes=['https://www.googleapis.com/auth/drive.readonly']
            )
            service = build('drive', 'v3', credentials=credentials)
            return service
        except json.JSONDecodeError:
            raise UserError(_('Invalid Google Drive credentials JSON format.'))
        except Exception as e:
            _logger.error(f"Error initializing Google Drive service: {str(e)}")
            raise UserError(_('Failed to initialize Google Drive service: %s') % str(e))

    @api.model
    def fetch_new_files(self):
        """
        Fetch new PDF files from configured Google Drive folder.
        Creates document.extraction records with status 'pending'.

        Returns:
            int: Number of new files fetched
        """
        # Check if integration is enabled
        enabled = self.env['ir.config_parameter'].sudo().get_param(
            'robotia_document_extractor.gdrive_enabled', default='False'
        )
        if enabled != 'True':
            _logger.info("Google Drive integration is disabled")
            return 0

        folder_id = self.env['ir.config_parameter'].sudo().get_param(
            'robotia_document_extractor.gdrive_folder_id'
        )

        if not folder_id:
            _logger.warning("Google Drive folder ID not configured")
            return 0

        try:
            service = self._get_drive_service()

            # Query for PDF files in the specified folder
            query = f"'{folder_id}' in parents and mimeType='application/pdf' and trashed=false"
            results = service.files().list(
                q=query,
                fields='files(id, name, createdTime, modifiedTime)',
                orderBy='createdTime desc',
                pageSize=100
            ).execute()

            files = results.get('files', [])
            _logger.info(f"Found {len(files)} PDF files in Google Drive folder")

            # Check which files are already in database
            existing_file_ids = self.env['document.extraction'].search([
                ('gdrive_file_id', '!=', False)
            ]).mapped('gdrive_file_id')

            new_files_count = 0
            for file in files:
                if file['id'] in existing_file_ids:
                    continue

                # Download file content
                file_content = service.files().get_media(fileId=file['id']).execute()

                # Create attachment
                attachment = self.env['ir.attachment'].create({
                    'name': file['name'],
                    'type': 'binary',
                    'datas': base64.b64encode(file_content),
                    'res_model': 'document.extraction',
                    'res_id': 0,  # Will be updated when record is created
                    'public': False,
                    'mimetype': 'application/pdf',
                })

                # Create document.extraction record
                self.env['document.extraction'].create({
                    'pdf_filename': file['name'],
                    'pdf_attachment_id': attachment.id,
                    'source': 'from_external_source',
                    'ocr_status': 'pending',
                    'gdrive_file_id': file['id'],
                    'year': 2024,  # Default year, will be updated by OCR
                    'document_type': '01',  # Default type, will be detected by OCR
                })

                # Update attachment res_id
                attachment.write({'res_id': attachment.res_id})

                new_files_count += 1
                _logger.info(f"Created record for Google Drive file: {file['name']}")

            _logger.info(f"Successfully fetched {new_files_count} new files from Google Drive")
            return new_files_count

        except Exception as e:
            _logger.error(f"Error fetching files from Google Drive: {str(e)}")
            return 0

    @api.model
    def process_pending_ocr(self):
        """
        Process pending OCR for documents fetched from Google Drive.
        Processes up to batch_size documents per run.

        Returns:
            dict: Statistics about processed documents
        """
        # Check if integration is enabled
        enabled = self.env['ir.config_parameter'].sudo().get_param(
            'robotia_document_extractor.gdrive_enabled', default='False'
        )
        if enabled != 'True':
            _logger.info("Google Drive integration is disabled")
            return {'processed': 0, 'success': 0, 'error': 0}

        batch_size = int(self.env['ir.config_parameter'].sudo().get_param(
            'robotia_document_extractor.gdrive_ocr_batch_size', default='3'
        ))

        # Find pending documents
        pending_docs = self.env['document.extraction'].search([
            ('source', '=', 'from_external_source'),
            ('ocr_status', 'in', ['pending', 'error'])
        ], limit=batch_size, order='extraction_date asc')

        if not pending_docs:
            _logger.info("No pending documents to process")
            return {'processed': 0, 'success': 0, 'error': 0}

        _logger.info(f"Processing {len(pending_docs)} pending documents for OCR")

        stats = {'processed': 0, 'success': 0, 'error': 0}
        extraction_service = self.env['document.extraction.service']

        for doc in pending_docs:
            try:
                # Mark as processing
                doc.write({
                    'ocr_status': 'processing',
                    'ocr_error_message': False
                })
                self.env.cr.commit()

                # Get PDF binary data
                if not doc.pdf_attachment_id:
                    raise UserError(_('No PDF attachment found'))

                pdf_binary = base64.b64decode(doc.pdf_attachment_id.datas)

                # Try to detect document type from filename or content
                # For now, default to '01', OCR will detect the actual type
                document_type = '01'
                if 'form_02' in doc.pdf_filename.lower() or 'bao_cao' in doc.pdf_filename.lower():
                    document_type = '02'

                # Perform OCR extraction
                _logger.info(f"Extracting data from: {doc.pdf_filename}")
                extracted_data = extraction_service.extract_pdf(
                    pdf_binary=pdf_binary,
                    document_type=document_type,
                    filename=doc.pdf_filename
                )

                # Update document with extracted data
                doc.write({
                    'document_type': extracted_data.get('document_type', document_type),
                    'year': extracted_data.get('year', 2024),
                    'organization_name': extracted_data.get('organization_name'),
                    'business_license_number': extracted_data.get('business_license_number'),
                    'business_license_date': extracted_data.get('business_license_date'),
                    'business_license_place': extracted_data.get('business_license_place'),
                    'legal_representative_name': extracted_data.get('legal_representative_name'),
                    'legal_representative_position': extracted_data.get('legal_representative_position'),
                    'contact_person_name': extracted_data.get('contact_person_name'),
                    'contact_address': extracted_data.get('contact_address'),
                    'contact_phone': extracted_data.get('contact_phone'),
                    'contact_fax': extracted_data.get('contact_fax'),
                    'contact_email': extracted_data.get('contact_email'),
                    'ocr_status': 'completed',
                })

                stats['success'] += 1
                _logger.info(f"Successfully processed: {doc.pdf_filename}")

            except Exception as e:
                error_msg = str(e)
                _logger.error(f"Error processing {doc.pdf_filename}: {error_msg}")
                doc.write({
                    'ocr_status': 'error',
                    'ocr_error_message': error_msg
                })
                stats['error'] += 1

            stats['processed'] += 1
            self.env.cr.commit()

        _logger.info(f"OCR processing complete: {stats}")
        return stats
