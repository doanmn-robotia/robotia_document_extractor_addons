# -*- coding: utf-8 -*-

import json
import logging
import base64
import uuid
from odoo import models, fields, api, _
from odoo.exceptions import UserError

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

    # ========== STEP TRACKING ==========
    current_step = fields.Selection([
        ('queue_pending', 'Step 0: Queue Pending'),
        ('upload_validate', 'Step 1: Upload & Validate'),
        ('category_mapping', 'Step 2: Category Mapping'),
        ('llama_ocr', 'Step 3: Llama OCR'),
        ('ai_batch_processing', 'Step 4: AI Batch Processing'),
        ('merge_validate', 'Step 5: Merge & Validate'),
        ('completed', 'Completed'),
    ], string='Current Step', default='queue_pending', index=True)

    last_completed_step = fields.Selection([
        ('queue_pending', 'Step 0: Queue Pending'),
        ('upload_validate', 'Step 1: Upload & Validate'),
        ('category_mapping', 'Step 2: Category Mapping'),
        ('llama_ocr', 'Step 3: Llama OCR'),
        ('ai_batch_processing', 'Step 4: AI Batch Processing'),
        ('merge_validate', 'Step 5: Merge & Validate'),
        ('completed', 'Completed'),
    ], string='Last Completed Step', help='Last successfully completed step for retry logic')

    # ========== INTERMEDIATE RESULTS (JSON Text Fields) ==========
    category_mapping_json = fields.Text(
        string='Category Mapping Result',
        help='Step 2 output: {metadata: [1,2], substance_usage: [3,4], ...}'
    )

    llama_ocr_json = fields.Text(
        string='Llama OCR Result',
        help='Step 3 output: [{category, ocr_data, page_count}, ...]'
    )

    ai_extracted_json = fields.Text(
        string='AI Extracted Data',
        help='Step 4 output: {metadata: {...}, substance_usage: [...], ...}'
    )

    final_result_json = fields.Text(
        string='Final Merged Result',
        help='Step 5 output: Complete validated extraction result'
    )

    # ========== GEMINI UPLOADED FILE TRACKING ==========
    gemini_file_name = fields.Char(
        string='Gemini File Name',
        help='Gemini uploaded file name for cleanup (stored after Step 1)'
    )

    # ========== RETRY METADATA ==========
    retry_count = fields.Integer(string='Retry Count', default=0)
    retry_from_step = fields.Selection([
        ('upload_validate', 'Step 1: Upload & Validate'),
        ('category_mapping', 'Step 2: Category Mapping'),
        ('llama_ocr', 'Step 3: Llama OCR'),
        ('ai_batch_processing', 'Step 4: AI Batch Processing'),
        ('merge_validate', 'Step 5: Merge & Validate'),
    ], string='Retry From Step', help='User-requested retry starting point')

    # ========== SMART BUTTON VISIBILITY ==========
    can_retry_from_llama = fields.Boolean(
        compute='_compute_retry_buttons',
        help='Show "Retry from Llama OCR" button'
    )
    can_retry_from_ai = fields.Boolean(
        compute='_compute_retry_buttons',
        help='Show "Retry from AI Processing" button'
    )
    can_retry_from_category = fields.Boolean(
        compute='_compute_retry_buttons',
        help='Show "Retry from Category Mapping" button'
    )
    
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

    uuid = fields.Char(default=uuid.uuid4())

    
    
    # ========== LIFECYCLE ==========
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('extraction.job') or _('New')
        return super().create(vals_list)

    # ========== ASYNC EXTRACTION METHOD ==========
    # Channel và identity_key được cấu hình via XML (data/queue_job_channel.xml)
    def run_extraction_async(self, retry_from_step=None):
        """
        Method to be delayed via queue_job with retry support

        This runs in a background worker and:
        1. Calls service orchestrator (process_pdf_extraction) for full pipeline
        2. Service handles: validation, log creation, attachment, AI extraction
        3. Supports step-based retry (resume from checkpoint)
        4. Builds form action values
        5. Stores complete action dict for frontend

        Args:
            retry_from_step (str, optional): Step to resume from (e.g., 'llama_ocr', 'ai_batch_processing')
        """
        self.ensure_one()

        # Prevent concurrent execution (unless retrying)
        if self.state == 'processing' and not retry_from_step:
            _logger.warning(f'JOB {self.id} is already processing')
            return

        try:
            # Get service
            service = self.env['document.extraction.service']

            # Update state to processing
            self.write({'state': 'processing'})

            # Decode PDF binary (attachment.datas is base64 encoded)
            pdf_binary = base64.b64decode(self.attachment_id.datas)

            # Call service orchestrator with job_id and resume support
            result = service.with_context(notify_channel=self.uuid).process_pdf_extraction(
                pdf_binary=pdf_binary,
                filename=self.attachment_id.name,
                document_type=self.document_type,
                check_rate_limit=False,  # No rate limit for async jobs
                last_extract_time=None,  # Not applicable for async
                job_id=self.id,  # Pass job ID for step tracking
                resume_from_step=retry_from_step  # Resume support
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

                # CRITICAL FIX: Raise exception so queue.job sets state='failed'
                # This ensures queue.job.state reflects the actual failure
                raise Exception(error_msg)


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
                'current_step': 'completed',
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

            # CRITICAL FIX: Re-raise exception so queue.job sets state='failed'
            # This ensures queue.job.state reflects the actual failure
            raise

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

    # ========== COMPUTED METHODS ==========

    @api.depends('state', 'last_completed_step', 'category_mapping_json', 'llama_ocr_json', 'ai_extracted_json')
    def _compute_retry_buttons(self):
        """
        Compute which retry buttons should be visible

        Rules:
        - can_retry_from_category: state=error AND category_mapping_json exists
        - can_retry_from_llama: state=error AND llama_ocr_json exists
        - can_retry_from_ai: state=error AND llama_ocr_json exists (need OCR data for AI)
        """
        for record in self:
            # Show retry buttons when step data is available (regardless of state)
            record.can_retry_from_category = bool(record.category_mapping_json)

            record.can_retry_from_llama = bool(record.llama_ocr_json)

            record.can_retry_from_ai = (
                bool(record.llama_ocr_json) and
                record.last_completed_step in ['llama_ocr', 'ai_batch_processing', 'merge_validate', 'completed']
            )

    # ========== RETRY ACTION METHODS ==========

    def action_retry_from_category_mapping(self):
        """Retry from Step 2: Category Mapping"""
        self.ensure_one()

        if not self.category_mapping_json:
            raise UserError(_('Cannot retry: No category mapping data found'))

        # Reset state and set current_step for UI display
        self.write({
            'state': 'pending',
            'current_step': 'category_mapping',  # Set step so progress view shows correct position
            'error_message': False,
            'retry_count': self.retry_count + 1,
            'retry_from_step': 'category_mapping'
        })

        # Re-enqueue job
        self.with_delay(
            identity_key=f'extraction_retry_{self.id}_{self.retry_count}'
        ).run_extraction_async(retry_from_step='category_mapping')

        # Get merged PDF URL from log
        merged_pdf_url = False
        if self.extraction_log_id and self.extraction_log_id.merged_pdf_url:
            merged_pdf_url = self.extraction_log_id.merged_pdf_url

        # Open progress view with PDF preview
        return {
            'type': 'ir.actions.client',
            'tag': 'robotia_document_extractor.page_selector',
            'params': {
                'mode': 'progress_only',
                'job_id': self.id,
                'job_id': self.uuid,
                'document_type': self.document_type,
                'merged_pdf_url': merged_pdf_url,  # Pass PDF URL for preview
                'retry_from_step': 'category_mapping',  # Pass retry step
            }
        }

    def action_retry_from_llama_ocr(self):
        """Retry from Step 3: Llama OCR (skipping OCR, only AI processing)"""
        self.ensure_one()

        if not self.llama_ocr_json:
            raise UserError(_('Cannot retry: No Llama OCR data found'))

        # Reset state and set current_step for UI display
        self.write({
            'state': 'pending',
            'current_step': 'llama_ocr',  # Set step so progress view shows correct position
            'error_message': False,
            'retry_count': self.retry_count + 1,
            'retry_from_step': 'llama_ocr'
        })

        self.with_delay(
            identity_key=f'extraction_retry_{self.id}_{self.retry_count}'
        ).run_extraction_async(retry_from_step='llama_ocr')

        # Get merged PDF URL from log
        merged_pdf_url = False
        if self.extraction_log_id and self.extraction_log_id.merged_pdf_url:
            merged_pdf_url = self.extraction_log_id.merged_pdf_url

        # Open progress view with PDF preview
        return {
            'type': 'ir.actions.client',
            'tag': 'robotia_document_extractor.page_selector',
            'params': {
                'mode': 'progress_only',
                'job_id': self.uuid,
                'document_type': self.document_type,
                'merged_pdf_url': merged_pdf_url,  # Pass PDF URL for preview
                'retry_from_step': 'llama_ocr',  # Pass retry step
            }
        }

    def action_retry_from_ai_processing(self):
        """Retry from Step 4: AI Batch Processing"""
        self.ensure_one()

        if not self.llama_ocr_json:
            raise UserError(_('Cannot retry: No Llama OCR data found'))

        # Reset state and set current_step for UI display
        self.write({
            'state': 'pending',
            'current_step': 'ai_batch_processing',  # Set step so progress view shows correct position
            'error_message': False,
            'retry_count': self.retry_count + 1,
            'retry_from_step': 'ai_batch_processing'
        })

        self.with_delay(
            identity_key=f'extraction_retry_{self.id}_{self.retry_count}'
        ).run_extraction_async(retry_from_step='ai_batch_processing')

        # Get merged PDF URL from log
        merged_pdf_url = False
        if self.extraction_log_id and self.extraction_log_id.merged_pdf_url:
            merged_pdf_url = self.extraction_log_id.merged_pdf_url

        # Open progress view with PDF preview
        return {
            'type': 'ir.actions.client',
            'tag': 'robotia_document_extractor.page_selector',
            'params': {
                'mode': 'progress_only',
                'job_id': self.uuid,
                'document_type': self.document_type,
                'merged_pdf_url': merged_pdf_url,  # Pass PDF URL for preview
                'retry_from_step': 'ai_batch_processing',  # Pass retry step
            }
        }

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
