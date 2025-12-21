# -*- coding: utf-8 -*-

import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class GoogleDriveExtractionLog(models.Model):
    _name = 'google.drive.extraction.log'
    _description = 'Google Drive Extraction Log'
    _order = 'create_date desc'

    # Source Identification
    drive_file_id = fields.Char(
        string='Drive File ID',
        index=True,
        help='Google Drive file ID'
    )

    file_name = fields.Char(
        string='File Name',
        required=True
    )

    document_type = fields.Selection([
        ('01', 'Form 01 - Registration'),
        ('02', 'Form 02 - Report')
    ], string='Document Type', required=True)

    # Processing Status
    status = fields.Selection([
        ('processing', 'Processing'),
        ('success', 'Success'),
        ('error', 'Error')
    ], string='Status', required=True, default='processing', index=True)

    # Results
    extraction_record_id = fields.Many2one(
        'document.extraction',
        string='Extraction Record',
        ondelete='set null',
        index=True
    )

    attachment_id = fields.Many2one(
        'ir.attachment',
        string='Attachment',
        ondelete='set null',
        help='Original PDF file'
    )

    merged_pdf_url = fields.Char(
        string='Merged PDF URL',
        compute='_compute_merged_pdf_url',
        help='Public URL for merged PDF preview'
    )

    ai_response_json = fields.Text(
        string='AI Response JSON',
        help='Raw JSON response from Gemini AI'
    )

    ocr_response_json = fields.Text(
        string='OCR Response JSON',
        help='Raw OCR data with bounding boxes (if OCR was performed)'
    )

    validation_result_json = fields.Text(
        string='Validation Result JSON',
        help='AI validation report comparing OCR output with PDF source (if validation was performed)'
    )

    # Error Handling
    error_message = fields.Text(
        string='Error Message',
        help='Error details if extraction failed'
    )

    # Timestamps
    processed_date = fields.Datetime(
        string='Processed Date',
        default=fields.Datetime.now,
        required=True
    )

    # Computed source type for UI filtering
    source_type = fields.Selection([
        ('manual', 'Manual Upload'),
        ('google_drive', 'Google Drive')
    ], string='Source',
        compute='_compute_source_type',
        store=True,
        help='Extraction source: Manual Upload or Google Drive',
        default="manual"
    )

    @api.depends('drive_file_id')
    def _compute_source_type(self):
        """Compute source type based on drive_file_id"""
        for record in self:
            if record.drive_file_id:
                record.source_type = 'google_drive'
            else:
                record.source_type = 'manual'

    @api.depends('attachment_id')
    def _compute_merged_pdf_url(self):
        """Generate public URL for merged PDF attachment"""
        for record in self:
            record.merged_pdf_url = f'/web/content/{record.attachment_id.id}'

    def _compute_display_name(self):
        for record in self:
            record.display_name = 'Log'

    def action_view_extraction_record(self):
        """Smart button to view linked extraction record"""
        self.ensure_one()
        if not self.extraction_record_id:
            return

        return {
            'type': 'ir.actions.act_window',
            'name': 'Extraction Record',
            'res_model': 'document.extraction',
            'res_id': self.extraction_record_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_create_extraction_from_log(self):
        """Create document.extraction record from log data"""
        self.ensure_one()

        # Check if log has successful data
        if self.status != 'success' or not self.ai_response_json:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Cannot Create',
                    'message': 'Cannot create extraction from failed or incomplete log.',
                    'type': 'danger',
                    'sticky': False,
                }
            }

        try:
            import json

            # Parse extracted data from log
            extracted_data = json.loads(self.ai_response_json)

            # Get or create attachment (if we have file data, otherwise skip)
            # Note: For logs from Google Drive, we might not have the PDF binary
            # So we'll create extraction without attachment
            attachment = self.attachment_id

            # Build form values using extraction helper
            helper = self.env['extraction.helper']
            vals = helper.build_extraction_values(
                extracted_data=extracted_data,
                attachment=attachment,
                document_type=self.document_type
            )

            # Add OCR data and status
            if self.ocr_response_json:
                vals['raw_ocr_data'] = self.ocr_response_json
                vals['ocr_status'] = 'completed'
            else:
                vals['raw_ocr_data'] = None

            # Convert to context for form defaults
            context = {f'default_{key}': value for key, value in vals.items()}
            context['default_extraction_log_id'] = self.id
            context['default_source'] = 'from_user_upload'

            _logger.info(f"Creating extraction from log ID {self.id}")

            # Return form action
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'document.extraction',
                'view_mode': 'form',
                'views': [[False, 'form']],
                'target': 'current',
                'context': context,
            }

        except Exception as e:
            _logger.error(f"Failed to create extraction from log: {e}", exc_info=True)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': f'Failed to create extraction: {str(e)}',
                    'type': 'danger',
                    'sticky': True,
                }
            }
