# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class QueueJobInherit(models.Model):
    _inherit = 'queue.job'

    # Computed fields for extraction job data (via records field)
    extraction_last_step = fields.Selection(
        [
            ('upload_validate', 'Step 1: Upload & Validate'),
            ('category_mapping', 'Step 2: Category Mapping'),
            ('llama_ocr', 'Step 3: Llama OCR'),
            ('ai_batch_processing', 'Step 4: AI Batch Processing'),
            ('merge_validate', 'Step 5: Merge & Validate'),
            ('completed', 'Completed'),
        ],
        string='Last Step',
        compute='_compute_extraction_job_fields',
        store=False,
        help='Last step reached in extraction process'
    )

    extraction_error = fields.Text(
        string='Extraction Error',
        compute='_compute_extraction_job_fields',
        store=False,
        help='Error message from extraction.job or queue.job (fallback)'
    )

    @api.depends('records', 'exc_info')
    def _compute_extraction_job_fields(self):
        """Compute extraction job fields from records field"""
        for record in self:
            # Check if records exists and is extraction.job
            if record.records and record.records._name == 'extraction.job':
                extraction_job = record.records

                # Handle multiple records (take first one)
                if len(extraction_job) > 1:
                    _logger.warning(f"Queue job {record.uuid} has multiple extraction.job records, using first")
                    extraction_job = extraction_job[0]

                record.extraction_last_step = extraction_job.current_step or False

                # Fallback: extraction.job.error_message → queue.job.exc_info
                record.extraction_error = extraction_job.error_message or record.exc_info or ''
            else:
                # No extraction job linked - fallback to queue.job error
                record.extraction_last_step = False
                record.extraction_error = record.exc_info or ''
