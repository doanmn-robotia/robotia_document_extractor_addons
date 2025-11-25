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

    ai_response_json = fields.Text(
        string='AI Response JSON',
        help='Raw JSON response from Gemini AI'
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
