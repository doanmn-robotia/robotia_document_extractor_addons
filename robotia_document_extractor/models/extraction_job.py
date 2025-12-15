# -*- coding: utf-8 -*-

import json
import logging
import base64
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class ExtractionJob(models.Model):
    """
    Async Extraction Job for handling long-running PDF extraction
    
    This model tracks the state of background extraction jobs created via queue_job.
    The async flow:
    1. Controller creates extraction.job record + schedules with_delay()
    2. Job runs in background, updates progress
    3. Frontend polls get_job_status() until done/error
    4. On completion, result_action_json contains the form action for doAction()
    """
    _name = 'extraction.job'
    _description = 'Async Extraction Job'
    _order = 'create_date desc'

    name = fields.Char(
        string='Job Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New')
    )
    
    # ========== INPUT ==========
    attachment_id = fields.Many2one(
        'ir.attachment',
        string='Input PDF',
        required=True,
        ondelete='cascade'
    )
    document_type = fields.Selection([
        ('01', 'Registration Form'),
        ('02', 'Report Form')
    ], string='Document Type', required=True)
    
    # ========== STATUS ==========
    state = fields.Selection([
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('done', 'Done'),
        ('error', 'Error'),
    ], string='State', default='pending', required=True, index=True)
    
    progress = fields.Integer(string='Progress %', default=0)
    progress_message = fields.Char(string='Progress Message')
    
    # ========== RESULT ==========
    extraction_log_id = fields.Many2one(
        'google.drive.extraction.log',
        string='Extraction Log',
        ondelete='set null'
    )
    extraction_id = fields.Many2one(
        'document.extraction',
        string='Extraction Result',
        ondelete='set null',
        help='Link to the created document.extraction record'
    )
    result_action_json = fields.Text(
        string='Result Action JSON',
        help='Complete action dict for frontend doAction()'
    )
    error_message = fields.Text(string='Error Message')

    
    
    # ========== LIFECYCLE ==========
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('extraction.job') or _('New')
        return super().create(vals_list)

    # ========== ASYNC EXTRACTION METHOD ==========
    # Channel và identity_key được cấu hình via XML (data/queue_job_channel.xml)
    def run_extraction_async(self):
        """
        Method to be delayed via queue_job

        This runs in a background worker and:
        1. Calls service orchestrator (process_pdf_extraction) for full pipeline
        2. Service handles: validation, log creation, attachment, AI extraction
        3. Builds form action values
        4. Stores complete action dict for frontend
        """
        self.ensure_one()

        if self.state == 'processing':
            _logger.warning("===========================================")
            _logger.warning('JOB %d is requested during processing', self.id)
            return

        try:
            # Update state
            self._update_progress(10, 'Đang chuẩn bị file PDF...')

            # Get service
            service = self.env['document.extraction.service']

            # Decode PDF binary (attachment.datas is base64 encoded)
            pdf_binary = base64.b64decode(self.attachment_id.datas)

            self._update_progress(20, 'Đang trích xuất dữ liệu với AI...')

            # Call service orchestrator (all-in-one: validation + log + attachment + AI)
            result = service.process_pdf_extraction(
                pdf_binary=pdf_binary,
                filename=self.attachment_id.name,
                document_type=self.document_type,
                check_rate_limit=False,  # No rate limit for async jobs
                last_extract_time=None   # Not applicable for async
            )

            # Check result
            if not result['success']:
                error_msg = result['error']['message']
                _logger.error(f"[Job {self.id}] Extraction failed: {error_msg}")

                # Link log to job if exists
                if result.get('log'):
                    self.extraction_log_id = result['log'].id

                # Mark job as error
                self.write({
                    'state': 'error',
                    'progress_message': 'Lỗi trích xuất',
                    'error_message': error_msg,
                })
                return  # Exit early


            # Success - get data from result
            extracted_data = result['extracted_data']
            log = result['log']
            attachment = result['attachment']

            # Link log to job
            self.extraction_log_id = log.id

            self._update_progress(70, 'Đang xử lý dữ liệu trích xuất...')

            # Build form values using extraction helper
            helper = self.env['extraction.helper']
            vals = helper.build_extraction_values(
                extracted_data=extracted_data,
                attachment=attachment,
                document_type=self.document_type
            )

            # Convert to context for form
            context = {f'default_{key}': value for key, value in vals.items()}
            context['default_extraction_log_id'] = log.id
            context['default_source'] = 'from_user_upload'
            context['default_extraction_job_ids'] = [fields.Command.link(self.id)]

            self._update_progress(90, 'Đang xây dựng form...')

            # Build complete action dict (same as controller returns)
            action = {
                'type': 'ir.actions.act_window',
                'res_model': 'document.extraction',
                'view_mode': 'form',
                'views': [[False, 'form']],
                'target': 'current',
                'context': context,
            }

            # Mark job as done with result
            self.write({
                'state': 'done',
                'progress': 100,
                'progress_message': 'Hoàn thành!',
                'result_action_json': json.dumps(action, ensure_ascii=False),
            })

            _logger.info(f"[Job {self.id}] Extraction completed successfully")

        except Exception as e:
            error_msg = str(e)
            _logger.error(f"[Job {self.id}] Extraction failed: {error_msg}", exc_info=True)

            # Update log if exists
            if self.extraction_log_id:
                self.extraction_log_id.write({
                    'status': 'error',
                    'error_message': error_msg,
                })

            # Mark job as error
            self.write({
                'state': 'error',
                'progress_message': 'Lỗi trích xuất',
                'error_message': error_msg,
            })

    def _update_progress(self, progress, message):
        """
        Helper to update progress atomically
        
        Note: We do NOT commit here because:
        1. Committing releases the job lock
        2. Job runner will think the job is dead and re-queue it
        3. Progress updates will be visible after job completes
        """
        self.write({
            'state': 'processing',
            'progress': progress,
            'progress_message': message,
        })

    # ========== STATUS API FOR POLLING ==========
    
    def get_job_status(self):
        """
        Return current job status for frontend polling
        
        Returns:
            dict: {
                'state': 'pending'|'processing'|'done'|'error',
                'progress': 0-100,
                'progress_message': str,
                'error_message': str or None,
                'action': dict (only if state='done')
            }
        """
        self.ensure_one()
        
        result = {
            'state': self.state,
            'progress': self.progress,
            'progress_message': self.progress_message or '',
            'error_message': self.error_message,
        }
        
        # If done, include the action dict for doAction
        if self.state == 'done' and self.result_action_json:
            try:
                result['action'] = json.loads(self.result_action_json)
            except json.JSONDecodeError:
                _logger.error(f"[Job {self.id}] Invalid result_action_json")
                result['error_message'] = 'Invalid result format'
        
        return result
