# -*- coding: utf-8 -*-

from odoo import models, api
from odoo.tools.translate import _
import json
import logging
import tempfile
import os
import time
import base64
import io
import fitz  # PyMuPDF
from google import genai
from google.genai import types

# Import prompt modules
from odoo.addons.robotia_document_extractor.prompts import context_prompts, strategy_prompts

_logger = logging.getLogger(__name__)

        # Constants
GEMINI_POLL_INTERVAL_SECONDS = 2
GEMINI_MAX_POLL_RETRIES = 30  # 30 * 2s = 60s timeout

# Shared keyword mappings for activity codes
SUBSTANCE_KEYWORDS = {
    'Sản xuất': 'production',
    'Nhập khẩu': 'import',
    'Xuất khẩu': 'export'
}

EQUIPMENT_KEYWORDS = {
    'Sản xuất thiết bị': 'equipment_production',
    'Nhập khẩu thiết bị': 'equipment_import'
}

OWNERSHIP_KEYWORDS = {
    'Máy điều hòa': 'ac_ownership',
    'Thiết bị lạnh': 'refrigeration_ownership'
}

COLLECTION_KEYWORDS = {
    'Thu gom': 'collection_recycling',
    'Tái sử dụng': 'collection_recycling',
    'Tái chế': 'collection_recycling',
    'Xử lý': 'collection_recycling'
}

# Table-to-field mapping
TABLE_ACTIVITY_MAPPINGS = {
    'substance_usage': {'field_name': 'substance_name', 'keywords': SUBSTANCE_KEYWORDS},
    'quota_usage': {'field_name': 'substance_name', 'keywords': SUBSTANCE_KEYWORDS},
    'equipment_product': {'field_name': 'product_type', 'keywords': EQUIPMENT_KEYWORDS},
    'equipment_product_report': {'field_name': 'product_type', 'keywords': EQUIPMENT_KEYWORDS},
    'equipment_ownership': {'field_name': 'equipment_type', 'keywords': OWNERSHIP_KEYWORDS},
    'equipment_ownership_report': {'field_name': 'equipment_type', 'keywords': OWNERSHIP_KEYWORDS},
    'collection_recycling': {'field_name': 'activity_type', 'keywords': COLLECTION_KEYWORDS},
    'collection_recycling_report': {'field_name': 'substance_name', 'keywords': COLLECTION_KEYWORDS}
}


class DocumentExtractionService(models.AbstractModel):
    """
    AI-powered document extraction service using Google Gemini API

    This service extracts structured data from PDF documents
    using Google's Gemini with PDF understanding capability.
    """
    _name = 'document.extraction.service'
    _description = 'Document Extraction Service'

    def make_temp_file(self, data):
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf', prefix="hfc_ai_extraction") as tmp_file:
                tmp_file.write(data)
                tmp_file_path = tmp_file.name

        return tmp_file_path

    def upload_file_to_gemini(self, client, path):
        uploaded_file = client.files.upload(file=path)
        _logger.info(f"File uploaded to Gemini: {uploaded_file.name}")

        # Wait for file to be processed
        poll_count = 0
        while uploaded_file.state.name == "PROCESSING":
            if poll_count >= GEMINI_MAX_POLL_RETRIES:
                raise TimeoutError(f"Gemini file processing timeout after {GEMINI_MAX_POLL_RETRIES * GEMINI_POLL_INTERVAL_SECONDS}s")

            time.sleep(GEMINI_POLL_INTERVAL_SECONDS)
            uploaded_file = client.files.get(name=uploaded_file.name)
            poll_count += 1

        if uploaded_file.state.name == "FAILED":
            raise ValueError("File processing failed in Gemini")

        _logger.info(f"File processing completed: {uploaded_file.state.name}")

        return uploaded_file

    def generate_content(self, client, content):
        # Get max output tokens from config (default: 65536 for Gemini 2.0 Flash)
        # User can adjust this in Settings if needed
        GEMINI_MAX_TOKENS = int(
            self.env['ir.config_parameter'].sudo().get_param(
                'robotia_document_extractor.gemini_max_output_tokens',
                default='65536'
            )
        )

        # Get Gemini model from config (default: gemini-2.0-flash-exp)
        GEMINI_MODEL = self.env['ir.config_parameter'].sudo().get_param(
            'robotia_document_extractor.gemini_model',
            default='gemini-2.5-pro'
        )

        # Get Gemini generation parameters from config
        ICP = self.env['ir.config_parameter'].sudo()
        GEMINI_TEMPERATURE = float(ICP.get_param(
            'robotia_document_extractor.gemini_temperature',
            default='0.0'
        ))
        GEMINI_TOP_P = float(ICP.get_param(
            'robotia_document_extractor.gemini_top_p',
            default='0.95'
        ))
        GEMINI_TOP_K = int(ICP.get_param(
            'robotia_document_extractor.gemini_top_k',
            default='0'
        ))
        # Convert top_k=0 to None (no limit)
        GEMINI_TOP_K = None if GEMINI_TOP_K == 0 else GEMINI_TOP_K

        return client.models.generate_content(
            model=GEMINI_MODEL,
            contents=content,
            config=types.GenerateContentConfig(
                temperature=GEMINI_TEMPERATURE,
                max_output_tokens=GEMINI_MAX_TOKENS,
                response_mime_type='application/json',  # Force JSON output
                top_p=GEMINI_TOP_P,
                top_k=GEMINI_TOP_K
            )
        )

    def create_chat_session(self, client, system_instruction):
        """
        Create a Gemini chat session with system instruction
        
        Similar to generate_content but returns a chat session for multi-turn conversation.
        Uses same configuration parameters (temperature, top_p, top_k, max_tokens).
        
        Args:
            client: Gemini client instance
            system_instruction (str): System instruction for the chat
            
        Returns:
            Chat session object
        """
        # Get configuration (same as generate_content)
        ICP = self.env['ir.config_parameter'].sudo()
        
        GEMINI_MODEL = ICP.get_param(
            'robotia_document_extractor.gemini_model',
            default='gemini-2.5-pro'
        )
        
        GEMINI_MAX_TOKENS = int(ICP.get_param(
            'robotia_document_extractor.gemini_max_output_tokens',
            default='65536'
        ))
        
        GEMINI_TEMPERATURE = float(ICP.get_param(
            'robotia_document_extractor.gemini_temperature',
            default='0.0'
        ))
        
        GEMINI_TOP_P = float(ICP.get_param(
            'robotia_document_extractor.gemini_top_p',
            default='0.95'
        ))
        
        GEMINI_TOP_K = int(ICP.get_param(
            'robotia_document_extractor.gemini_top_k',
            default='0'
        ))
        GEMINI_TOP_K = None if GEMINI_TOP_K == 0 else GEMINI_TOP_K
        
        # Create chat session
        chat = client.chats.create(
            model=GEMINI_MODEL,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=GEMINI_TEMPERATURE,
                max_output_tokens=GEMINI_MAX_TOKENS,
                response_mime_type='application/json',
                top_p=GEMINI_TOP_P,
                top_k=GEMINI_TOP_K
            )
        )
        
        _logger.info(f"Created chat session with model {GEMINI_MODEL}")
        
        return chat

    def cleanup_temp_extraction_files(self):
        """
        Clean up all temporary extraction files with prefix 'hfc_ai_extraction'
        
        Removes stale temporary files from previous extraction attempts
        to prevent disk space issues. Should be called at the start of extraction.
        """
        import tempfile
        import glob
        
        temp_dir = tempfile.gettempdir()
        pattern = os.path.join(temp_dir, 'hfc_ai_extraction*')
        
        cleaned_count = 0
        for file_path in glob.glob(pattern):
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
                    cleaned_count += 1
                    _logger.debug(f"Cleaned up temp file: {file_path}")
            except Exception as e:
                _logger.warning(f"Failed to cleanup temp file {file_path}: {e}")
        
        if cleaned_count > 0:
            _logger.info(f"Cleaned up {cleaned_count} temporary extraction files")

    def merge_page_attachments_to_pdf(self, attachment_ids):
        """
        Merge selected page attachments (PNG images) into a single PDF

        This helper takes page attachments created by /robotia/pdf_to_images,
        parses page numbers from filenames (page_0.png, page_1.png, ...),
        sorts them in ascending order, and merges them into a single PDF document.

        Args:
            attachment_ids (list): List of ir.attachment IDs (page_X.png images)

        Returns:
            bytes: PDF binary data containing merged pages

        Raises:
            ValueError: If no valid page attachments found or parsing fails
        """
        # Get attachments
        Attachment = self.env['ir.attachment'].sudo()
        attachments = Attachment.browse(attachment_ids)

        if not attachments:
            raise ValueError(_('No valid page attachments found'))

        # Parse page numbers and collect data
        pages_data = []
        for att in attachments:
            try:
                # Extract page number from "page_0.png" → 0
                page_num = int(att.name.replace('page_', '').replace('.png', ''))
                pages_data.append({
                    'page_num': page_num,
                    'attachment': att,
                })
            except (ValueError, AttributeError) as e:
                _logger.warning(f"Could not parse page number from {att.name}: {e}")

        if not pages_data:
            raise ValueError(_('Could not parse page numbers from attachment names'))

        # Sort by page number (ascending order)
        pages_data.sort(key=lambda x: x['page_num'])
        _logger.info(f"Merging {len(pages_data)} pages: {[p['page_num'] for p in pages_data]}")

        # Create new PDF from images
        new_doc = fitz.open()  # New empty PDF

        for page_data in pages_data:
            att = page_data['attachment']

            try:
                # Decode image binary
                img_binary = base64.b64decode(att.datas)

                # Open image as document
                img_doc = fitz.open(stream=img_binary, filetype="png")

                # Insert image page into new PDF
                pdf_bytes = img_doc.convert_to_pdf()  # Convert image page to PDF
                img_pdf = fitz.open("pdf", pdf_bytes)
                new_doc.insert_pdf(img_pdf)

                img_pdf.close()
                img_doc.close()

            except Exception as e:
                _logger.error(f"Failed to merge page {page_data['page_num']}: {e}")
                new_doc.close()
                raise ValueError(f"Failed to merge page {page_data['page_num']}: {e}")

        # Save to bytes
        output_stream = io.BytesIO()
        new_doc.save(output_stream)
        pdf_binary = output_stream.getvalue()
        new_doc.close()

        _logger.info(f"Successfully merged {len(pages_data)} pages into PDF ({len(pdf_binary)} bytes)")
        return pdf_binary

    def update_progress(self, new_env, progress, message, job_id=None, 
                         detected_categories=None, current_sub_step=None):
        """
        Update progress notification for frontend (via bus.bus only)

        IMPORTANT: This method ONLY sends bus notifications.
        Job record updates (current_step, progress, checkpoints) must be done
        in the main transaction by the caller.

        Args:
            new_env: Separate environment with own cursor (for bus.bus commit only)
            progress: Can be int (0-100) for legacy, or str (step_key) for step-based
            message: Human-readable Vietnamese message
            job_id: Not used (kept for backward compatibility)
            detected_categories: List of detected category keys (for category_mapping step)
            current_sub_step: Current category being processed (for llama_ocr/ai_batch_processing)
        """
        # Convert step_key to progress percentage if needed
        if isinstance(progress, str):
            step_key = progress
            progress_percent = self._calculate_progress_from_step(step_key)
        else:
            step_key = None
            progress_percent = progress

        # Send real-time notification via bus.bus (ONLY purpose of new_env)
        if self.env.context.get('notify_channel'):
            notification_data = {
                "progress": progress_percent,
                "message": message
            }
            if step_key:
                notification_data["step"] = step_key
            
            # Add sub-step info if provided
            if detected_categories:
                notification_data["detected_categories"] = detected_categories
            if current_sub_step:
                notification_data["current_sub_step"] = current_sub_step

            new_env['bus.bus']._sendone(
                self.env.context.get('notify_channel'),
                'update_progress',
                notification_data
            )
            new_env.cr.commit()

    def _calculate_progress_from_step(self, step_key):
        """Map step to percentage for backward compatibility"""
        step_progress = {
            'queue_pending': 0,
            'upload_validate': 10,
            'category_mapping': 20,
            'llama_ocr': 40,
            'ai_batch_processing': 80,
            'merge_validate': 95,
            'completed': 100,
        }
        return step_progress.get(step_key, 0)

    def process_pdf_extraction(self, pdf_binary, filename, document_type,
                               check_rate_limit=True, last_extract_time=None,
                               job_id=None, resume_from_step=None):
        """
        MAIN ORCHESTRATOR: Process PDF extraction with transaction-safe logging

        This method orchestrates the full extraction pipeline:
        1. Type validation (pdf_binary must be bytes)
        2. Rate limiting check (optional, BEFORE log creation)
        3. Create extraction log (processing status)
        4. Validate file (extension, size, PDF magic bytes)
        5. Create ir.attachment (BEFORE AI call)
        6. Call extract_pdf() for AI extraction
        7. Update log (success/error status)

        Args:
            pdf_binary (bytes): PDF binary data (must be bytes, not string)
            filename (str): Original filename
            document_type (str): '01' or '02'
            check_rate_limit (bool): Whether to check rate limiting (default: True)
            last_extract_time (float): Unix timestamp of last extraction (for rate limit)
            job_id (int): Optional extraction.job ID for step checkpointing (llama_split only)
            resume_from_step (str): Optional step to resume from (llama_split only)

        Returns:
            dict: {
                'success': True/False,
                'extracted_data': {...} or None,
                'attachment': ir.attachment record or None,
                'log': google.drive.extraction.log record (None if rate limited),
                'error': None or dict with notification params,
                'rate_limit_exceeded': bool (True if rate limited)
            }
        """
        import traceback

        # Constants
        MAX_PDF_SIZE_MB = 50
        MAX_PDF_SIZE_BYTES = MAX_PDF_SIZE_MB * 1024 * 1024
        EXTRACTION_RATE_LIMIT_SECONDS = 5

        # Variables to track cleanup
        log = None
        attachment = None
        extracted_data = None

        try:    
            # ===== STEP 0: Type validation (FIRST - cheapest check) =====
            if not isinstance(pdf_binary, bytes):
                raise TypeError(
                    f"pdf_binary must be bytes, got {type(pdf_binary).__name__}. "
                    f"If you have base64 string, decode it first with base64.b64decode()"
                )

            if len(pdf_binary) == 0:
                raise ValueError("pdf_binary is empty - cannot extract from empty file")

            # ===== STEP 1: Rate limiting (BEFORE log creation to prevent DB pollution) =====
            if check_rate_limit and last_extract_time is not None:
                current_time = time.time()
                if current_time - last_extract_time < EXTRACTION_RATE_LIMIT_SECONDS:
                    wait_seconds = int(EXTRACTION_RATE_LIMIT_SECONDS - (current_time - last_extract_time)) + 1
                    _logger.warning(f"Rate limit exceeded for {filename}: Please wait {wait_seconds}s")
                    return {
                        'success': False,
                        'extracted_data': None,
                        'attachment': None,
                        'log': None,  # No log created when rate limited
                        'error': {
                            'title': _('Too Many Requests'),
                            'message': _('Please wait %(seconds)d seconds before extracting again') % {'seconds': wait_seconds},
                            'type': 'warning',
                        },
                        'rate_limit_exceeded': True
                    }

            # ===== STEP 2: Create log (AFTER rate limiting check) =====
            log = self.env['google.drive.extraction.log'].sudo().create({
                'drive_file_id': False,  # No Drive ID for manual uploads
                'file_name': filename,
                'document_type': document_type,
                'status': 'processing',
            })
            _logger.info(f"[Log {log.id}] Created log for {filename} (Type: {document_type})")

            # ===== STEP 3: File validations =====

            # 3.1 Validate file extension
            if not filename.lower().endswith('.pdf'):
                error_msg = 'Invalid file type: Only PDF files are allowed'
                log.write({'status': 'error', 'error_message': error_msg})
                _logger.warning(f"[Log {log.id}] {error_msg}")
                return {
                    'success': False,
                    'extracted_data': None,
                    'attachment': None,
                    'log': log,
                    'error': {
                        'title': _('Invalid File Type'),
                        'message': _('Only PDF files are allowed'),
                        'type': 'danger',
                    },
                    'rate_limit_exceeded': False
                }

            # 3.2 Validate file size
            pdf_size_bytes = len(pdf_binary)
            if pdf_size_bytes > MAX_PDF_SIZE_BYTES:
                pdf_size_mb = pdf_size_bytes / 1024 / 1024
                error_msg = f'File too large: {pdf_size_mb:.1f}MB (max {MAX_PDF_SIZE_MB}MB)'
                log.write({'status': 'error', 'error_message': error_msg})
                _logger.warning(f"[Log {log.id}] {error_msg}")
                return {
                    'success': False,
                    'extracted_data': None,
                    'attachment': None,
                    'log': log,
                    'error': {
                        'title': _('File Too Large'),
                        'message': _('File size (%(size).1fMB) exceeds %(max)dMB') % {'size': pdf_size_mb, 'max': MAX_PDF_SIZE_MB},
                        'type': 'danger',
                    },
                    'rate_limit_exceeded': False
                }

            # 3.3 Validate PDF magic bytes
            if not pdf_binary.startswith(b'%PDF'):
                error_msg = 'Invalid PDF format: File does not start with PDF signature'
                log.write({'status': 'error', 'error_message': error_msg})
                _logger.warning(f"[Log {log.id}] {error_msg}")
                return {
                    'success': False,
                    'extracted_data': None,
                    'attachment': None,
                    'log': log,
                    'error': {
                        'title': _('Invalid PDF'),
                        'message': _('The uploaded file does not appear to be a valid PDF'),
                        'type': 'danger',
                    },
                    'rate_limit_exceeded': False
                }

            # ===== STEP 3: Create attachment BEFORE AI call (CRITICAL for logging) =====
            try:
                attachment = self.env['ir.attachment'].sudo().create({
                    'name': filename,
                    'type': 'binary',
                    'datas': base64.b64encode(pdf_binary).decode('utf-8'),
                    'res_model': 'document.extraction',
                    'res_id': 0,  # Public for preview
                    'public': True,
                    'mimetype': 'application/pdf',
                })
                # Link attachment to log IMMEDIATELY
                log.write({'attachment_id': attachment.id})
                _logger.info(f"[Log {log.id}] Created attachment {attachment.id}")
            except Exception as e:
                error_msg = f'Failed to create attachment: {str(e)}'
                log.write({'status': 'error', 'error_message': error_msg})
                _logger.error(f"[Log {log.id}] {error_msg}", exc_info=True)
                return {
                    'success': False,
                    'extracted_data': None,
                    'attachment': None,
                    'log': log,
                    'error': {
                        'title': _('Upload Failed'),
                        'message': _('Failed to upload PDF file to server'),
                        'type': 'danger',
                    },
                    'rate_limit_exceeded': False
                }

            # ===== STEP 4: AI Extraction =====
            try:
                _logger.info(f"[Log {log.id}] Starting AI extraction...")
                extracted_data = self.extract_pdf(
                    pdf_binary,
                    document_type,
                    log_id=log,
                    job_id=job_id,
                    resume_from_step=resume_from_step
                )
                _logger.info(f"[Log {log.id}] AI extraction completed successfully")
            except Exception as e:
                error_msg = f'AI extraction failed: {str(e)}'
                error_traceback = traceback.format_exc()

                # Update log with detailed error
                log.write({
                    'status': 'error',
                    'error_message': error_traceback,
                })
                _logger.error(f"[Log {log.id}] {error_msg}", exc_info=True)

                return {
                    'success': False,
                    'extracted_data': None,
                    'attachment': attachment,
                    'log': log,
                    'error': {
                        'title': _('AI Extraction Failed'),
                        'message': str(e),
                        'type': 'danger',
                    },
                    'rate_limit_exceeded': False
                }

            # ===== STEP 5: Post-processing (auto-calculate years) =====
            try:
                year = extracted_data.get('year')
                if year:
                    if not extracted_data.get('year_1'):
                        extracted_data['year_1'] = year - 1
                    if not extracted_data.get('year_2'):
                        extracted_data['year_2'] = year
                    if not extracted_data.get('year_3'):
                        extracted_data['year_3'] = year + 1
            except Exception as e:
                # Non-critical error, just log warning
                _logger.warning(f"[Log {log.id}] Failed to auto-calculate years: {e}")

            # ===== STEP 6: Update log to SUCCESS (ONLY if everything succeeded) =====
            try:
                log_data = {
                    'status': 'success',
                    'ai_response_json': json.dumps(extracted_data, ensure_ascii=False, indent=2),
                }
                log.write(log_data)
                _logger.info(f"[Log {log.id}] Extraction pipeline completed successfully")
            except Exception as e:
                # Critical: Failed to save log data
                error_msg = f'Failed to save extraction results to log: {str(e)}'
                _logger.error(f"[Log {log.id}] {error_msg}", exc_info=True)
                # Try to update log status
                try:
                    log.write({'status': 'error', 'error_message': error_msg})
                except:
                    pass

                return {
                    'success': False,
                    'extracted_data': extracted_data,
                    'attachment': attachment,
                    'log': log,
                    'error': {
                        'title': _('Save Failed'),
                        'message': _('Extraction succeeded but failed to save results'),
                        'type': 'danger',
                    },
                    'rate_limit_exceeded': False
                }

            # ===== SUCCESS: Return complete result =====
            return {
                'success': True,
                'extracted_data': extracted_data,
                'attachment': attachment,
                'log': log,
                'error': None,
                'rate_limit_exceeded': False
            }

        except Exception as e:
            # ===== CATCH-ALL: Handle ANY unexpected error =====
            error_msg = f'Unexpected error in extraction pipeline: {str(e)}'
            error_traceback = traceback.format_exc()
            _logger.error(f"[Log {log.id if log else 'N/A'}] {error_msg}", exc_info=True)

            # Try to update log if it exists
            if log:
                try:
                    log.write({
                        'status': 'error',
                        'error_message': error_traceback,
                    })
                except Exception as log_error:
                    _logger.error(f"Failed to update log: {log_error}")

            return {
                'success': False,
                'extracted_data': None,
                'attachment': attachment,  # May be None if error before attachment creation
                'log': log,  # May be None if error before log creation
                'error': {
                    'title': _('Unexpected Error'),
                    'message': str(e),
                    'type': 'danger',
                },
                'rate_limit_exceeded': False
            }

    def _build_pdf_from_pages(self, pdf_binary, page_indexes):
        """
        Build a new PDF from selected pages of original PDF
        
        Args:
            pdf_binary (bytes): Original PDF binary
            page_indexes (list): List of 1-based page indexes to extract (e.g., [1, 2, 3])
            
        Returns:
            str: Path to temporary PDF file containing only selected pages
            
        Raises:
            ImportError: If PyMuPDF is not installed
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise ImportError(
                "PyMuPDF is not installed. Please install it with: pip install PyMuPDF"
            )
        
        # Open original PDF
        doc = fitz.open(stream=pdf_binary, filetype="pdf")
        new_doc = fitz.open()  # Create new empty PDF
        
        # Insert selected pages (convert 1-indexed to 0-indexed)
        for page_num in page_indexes:
            page_idx = page_num - 1
            if 0 <= page_idx < len(doc):
                new_doc.insert_pdf(doc, from_page=page_idx, to_page=page_idx)
            else:
                _logger.warning(f"Page {page_num} out of range, skipping")
        
        # Save to temp file with hfc_ai_extraction prefix
        tmp_file = tempfile.NamedTemporaryFile(
            delete=False, 
            suffix='.pdf', 
            prefix='hfc_ai_extraction_category_'
        )
        new_doc.save(tmp_file.name)
        
        doc.close()
        new_doc.close()
        tmp_file.close()
        
        _logger.info(f"Created category PDF with {len(page_indexes)} pages: {tmp_file.name}")
        
        return tmp_file.name

    def _build_markdown_from_ocr(self, ocr_data, index_from):
        """
        Build complete markdown from LlamaParse OCR result
        
        Args:
            ocr_data: LlamaParse JSON result (list or dict)
            
        Returns:
            str: Complete markdown text with page separators
        """
        # Handle different OCR data structures
        pages = []
        if isinstance(ocr_data, list) and len(ocr_data) > 0:
            if isinstance(ocr_data[0], dict) and 'pages' in ocr_data[0]:
                pages = ocr_data[0].get('pages', [])
        
        total_page = len(pages)

        if index_from >= total_page:
            return None

        index_end = index_from + 7 if index_from + 7 < total_page else total_page

        markdown_parts = []
        for page in pages[index_from:index_end]:
            page_md = page.get('md', '')
            if page_md:
                markdown_parts.append(page_md)
        
        full_markdown = "\n\n---\n\n".join(markdown_parts)
        
        _logger.debug(f"Built markdown from {len(pages)} pages: {len(full_markdown)} chars")
        
        return full_markdown

    def _build_category_extraction_prompt(self, category, markdown, document_type):
        """
        Build extraction prompt for specific category
        
        Args:
            category (str): Category key (metadata, substance_usage, etc.)
            markdown (str): Markdown content from LlamaParse
            document_type (str): '01' or '02'
            
        Returns:
            str: Extraction prompt for Gemini chat
        """
        # Get schema from schema_prompts
        from odoo.addons.robotia_document_extractor.prompts import schema_prompts
        
        if document_type == '01':
            schema = schema_prompts.get_form_01_schema()
        else:
            schema = schema_prompts.get_form_02_schema()
        
        if category == 'metadata':
            return f"""
NHIỆM VỤ: Trích xuất metadata từ tài liệu

CATEGORY: metadata

⚠️ **LƯU Ý QUAN TRỌNG**: Metadata được extract SAU CÙNG, do đó bạn có thể nhìn lại TOÀN BỘ LỊCH SỬ ĐỘI THOẠI để suy luận các cờ (flags).

MARKDOWN CONTENT:
{markdown}

EXTRACTION RULES:
{schema}

HƯỚNG DẪN TRÍCH XUẤT:

1. **THÔNG TIN CƠ BẢN** (organization_name, business_license, contact info):
   - Trích xuất từ markdown
   - Bảo toàn ký tự tiếng Việt

2. **CỜ HAS_TABLE (Table Presence Flags)**:
   - **XEM LẠI LỊCH SỬ CHAT**: Bạn đã được yêu cầu extract những category nào?

   **MAPPING CATEGORY → FLAG (Form 01):**
   - Nếu đã extract `substance_usage` → `has_table_1_1 = true`
   - Nếu đã extract `equipment_product` → `has_table_1_2 = true`
   - Nếu đã extract `equipment_ownership` → `has_table_1_3 = true`
   - Nếu đã extract `collection_recycling` → `has_table_1_4 = true`

   **MAPPING CATEGORY → FLAG (Form 02):**
   - Nếu đã extract `quota_usage` → `has_table_2_1 = true`
   - Nếu đã extract `equipment_product_report` → `has_table_2_2 = true`
   - Nếu đã extract `equipment_ownership_report` → `has_table_2_3 = true`
   - Nếu đã extract `collection_recycling_report` → `has_table_2_4 = true`

3. **YEAR FIELDS**:
   - `year`: Năm báo cáo (từ header như "Đăng ký năm 2024" hoặc "Báo cáo năm 2024")
   - `year_1, year_2, year_3`: **QUAN TRỌNG** - Lấy từ column headers của Bảng 1.1 (substance_usage) hoặc Bảng 2.1 (quota_usage)
     * Xem lại response của category `substance_usage` hoặc `quota_usage` trong lịch sử chat
     * Tìm 3 cột năm trong bảng đó (thường là năm hiện tại và 2 năm trước)
     * Ví dụ: năm 2024 → year_1=2022, year_2=2023, year_3=2024

4. **IS_CAPACITY_MERGED FLAGS**:
   - Xem lại dữ liệu bảng `equipment_product` hoặc `equipment_product_report` trong lịch sử:
     * Nếu có trường `capacity` (1 cột gộp) → `is_capacity_merged_table_1_2 = true`
     * Nếu có `cooling_capacity` và `power_capacity` riêng (2 cột) → `is_capacity_merged_table_1_2 = false`
   - Tương tự cho `equipment_ownership` → `is_capacity_merged_table_1_3`

5. **ACTIVITY_FIELD_CODES** (Suy luận thông minh):

   **Ưu tiên 1**: Tìm trong markdown checkbox/tick đánh dấu lĩnh vực

   **Ưu tiên 2**: Nếu không tìm thấy, SUY LUẬN từ has_table flags:

   **Form 01 Mapping:**
   - `has_table_1_1 = true` → Xem bảng substance_usage có dòng data (is_title=false) không?
     * Nếu có dòng với usage_type="production" → thêm "production" vào activity_field_codes
     * Nếu có dòng với usage_type="import" → thêm "import"
     * Nếu có dòng với usage_type="export" → thêm "export"
   - `has_table_1_2 = true` → Xem bảng equipment_product có dòng data thực không?
     * Nếu có → thêm "equipment_production" hoặc "equipment_import" tùy product_type
   - `has_table_1_3 = true` → Xem bảng equipment_ownership có dòng data thực không?
     * Nếu có → thêm "ac_ownership" hoặc "refrigeration_ownership" tùy equipment_type
   - `has_table_1_4 = true` → Xem bảng collection_recycling có dòng data thực không?
     * Nếu có → thêm "collection_recycling"

   **Nguyên tắc**: Chỉ coi là "có" nếu bảng có **ÍT NHẤT 1 DÒNG DATA** (is_title=false với giá trị thực tế)

OUTPUT: JSON object với TẤT CẢ metadata fields kể cả flags
"""
        else:
            return f"""
NHIỆM VỤ: Trích xuất bảng dữ liệu từ tài liệu

CATEGORY: {category}

MARKDOWN CONTENT:
{markdown}

EXTRACTION RULES:
{schema}

HƯỚNG DẪN:
- Trích xuất bảng {category} thành JSON array
- Mỗi dòng trong bảng là 1 object trong array
- Bảo toàn tất cả dữ liệu, không bỏ sót
- Giữ nguyên số liệu (kg, CO2e), không làm tròn
- Bảo toàn ký tự tiếng Việt

QUY TẮC XỬ LÝ DÒNG:
1. **DÒNG TIÊU ĐỀ/PHÂN LOẠI (GIỮ LẠI):**
   - Dòng có tên phân loại rõ ràng (VD: "Sản xuất chất được kiểm soát", "Nhập khẩu chất được kiểm soát")
   - Có các dòng dữ liệu con bên dưới
   - Các trường số liệu có thể là null
   - Set is_title=true

2. **DÒNG TRỐNG/PLACEHOLDER (LOẠI BỎ):**
   - Chứa "...", gạch ngang "-", ký tự placeholder
   - Tên chất/mã HS không rõ ràng hoặc không có ý nghĩa
   - Loại bỏ hoàn toàn khỏi kết quả

3. **DÒNG DỮ LIỆU TRÙNG:**
   - Có thể trùng mã chất nhưng khác lĩnh vực/năm/giao dịch
   - Trả về đầy đủ TẤT CẢ các dòng, không gộp

OUTPUT FORMAT: {{"{category}": [...]}}
"""

    def _merge_category_data(self, extracted_datas):
        """
        Merge all category extraction results into single object
        
        Args:
            extracted_datas (list): List of dicts from category extractions
            
        Returns:
            dict: Merged data
        """
        merged = {}
        
        for data in extracted_datas:
            if not data:
                continue
            
            for key, value in data.items():
                if key not in merged:
                    merged[key] = value
                elif isinstance(value, list):
                    # For arrays (tables), extend
                    if isinstance(merged[key], list):
                        merged[key].extend(value)
                    else:
                        merged[key] = value
                else:
                    # For scalars, keep first non-null value
                    if not merged[key] and value:
                        merged[key] = value
        
        _logger.info(f"Merged {len(extracted_datas)} category results into {len(merged)} fields")
        
        return merged

    def _validate_and_fix_metadata_flags(self, extracted_data, document_type):
        """
        Validate and fix metadata flags based on actual extracted data
        
        This method uses regex and data analysis instead of relying on AI inference.
        It analyzes the extracted tables to determine:
        - has_table_x_y flags (based on category presence)
        - year_1, year_2, year_3 (from table column headers)
        - is_capacity_merged flags (from table structure)
        - activity_field_codes (from title rows and data rows)
        
        Args:
            extracted_data (dict): Merged extracted data
            document_type (str): '01' or '02'
            
        Returns:
            dict: Fixed extracted data with correct flags
        """
        _logger.info("Validating and fixing metadata flags...")
        
        # Step 1: Validate has_table flags with AI priority
        # Philosophy: Trust AI when True, validate when False
        _logger.info("Validating has_table_* flags with AI priority logic...")

        if document_type == '01':
            # Get AI values
            ai_has_table_1_1 = extracted_data.get('has_table_1_1', False)
            ai_has_table_1_2 = extracted_data.get('has_table_1_2', False)
            ai_has_table_1_3 = extracted_data.get('has_table_1_3', False)
            ai_has_table_1_4 = extracted_data.get('has_table_1_4', False)

            # Validate with hybrid logic (trust AI=True, verify AI=False)
            extracted_data['has_table_1_1'] = self._validate_has_table_flag(
                ai_has_table_1_1, extracted_data.get('substance_usage', [])
            )
            extracted_data['has_table_1_2'] = self._validate_has_table_flag(
                ai_has_table_1_2, extracted_data.get('equipment_product', [])
            )
            extracted_data['has_table_1_3'] = self._validate_has_table_flag(
                ai_has_table_1_3, extracted_data.get('equipment_ownership', [])
            )
            extracted_data['has_table_1_4'] = self._validate_has_table_flag(
                ai_has_table_1_4, extracted_data.get('collection_recycling', [])
            )

        else:  # document_type == '02'
            # Get AI values
            ai_has_table_2_1 = extracted_data.get('has_table_2_1', False)
            ai_has_table_2_2 = extracted_data.get('has_table_2_2', False)
            ai_has_table_2_3 = extracted_data.get('has_table_2_3', False)
            ai_has_table_2_4 = extracted_data.get('has_table_2_4', False)

            # Validate with hybrid logic
            extracted_data['has_table_2_1'] = self._validate_has_table_flag(
                ai_has_table_2_1, extracted_data.get('quota_usage', [])
            )
            extracted_data['has_table_2_2'] = self._validate_has_table_flag(
                ai_has_table_2_2, extracted_data.get('equipment_product_report', [])
            )
            extracted_data['has_table_2_3'] = self._validate_has_table_flag(
                ai_has_table_2_3, extracted_data.get('equipment_ownership_report', [])
            )
            extracted_data['has_table_2_4'] = self._validate_has_table_flag(
                ai_has_table_2_4, extracted_data.get('collection_recycling_report', [])
            )

        _logger.info("has_table_* flags validation complete")
        
        # try:
        #     # Step 2: Extract year_1, year_2, year_3 from substance_usage or quota_usage
        #     self._extract_years_from_tables(extracted_data, document_type)
        # except Exception as err:
        #     _logger.error("INFER YEAR ERROR --- %s", err)
        # try:
        #     # Step 3: Determine is_capacity_merged flags from table structure
        #     self._determine_capacity_merged_flags(extracted_data, document_type)
        # except Exception as err:
        #     _logger.error("INFER CAPACITY MERGE ERROR --- %s", err)
        
        try:
            # Step 4: Infer activity_field_codes from table data
            self._infer_activity_field_codes(extracted_data)
        except Exception as err:
            _logger.error("INFER ACTIVIY ERROR --- %s", err)
        
        _logger.info("Metadata flags validation completed")
        
        return extracted_data
    
    def _extract_years_from_tables(self, extracted_data, document_type):
        """
        Extract year_1, year_2, year_3 from table headers

        Logic: AI should extract these years directly from table column headers.
        If not extracted, fallback to current_year - 2, -1, 0
        """
        # Check if AI already extracted years from headers
        if extracted_data.get('year_1') and extracted_data.get('year_2') and extracted_data.get('year_3'):
            _logger.info(f"Years already extracted: {extracted_data['year_1']}, {extracted_data['year_2']}, {extracted_data['year_3']}")
            return

        # Fallback: infer from current year (year - 2, year - 1, year)
        current_year = extracted_data.get('year')
        if current_year:
            extracted_data['year_1'] = current_year - 2
            extracted_data['year_2'] = current_year - 1
            extracted_data['year_3'] = current_year
            _logger.info(f"Inferred years from current year: {extracted_data['year_1']}, {extracted_data['year_2']}, {extracted_data['year_3']}")
        else:
            _logger.warning("Cannot extract or infer year_1, year_2, year_3")
    
    def _determine_capacity_merged_flags(self, extracted_data, document_type):
        """
        Determine is_capacity_merged flags by checking table structure
        
        Logic:
        - If table has 'capacity' field (1 merged column) → is_capacity_merged = True
        - If table has 'cooling_capacity' and 'power_capacity' (2 separate) → is_capacity_merged = False
        """
        if document_type == '01':
            # Check table 1.2 (equipment_product)
            equipment_product = extracted_data.get('equipment_product', [])
            if equipment_product:
                first_row = equipment_product[0]
                has_capacity = 'capacity' in first_row
                has_separate = 'cooling_capacity' in first_row or 'power_capacity' in first_row
                extracted_data['is_capacity_merged_table_1_2'] = has_capacity and not has_separate
            
            # Check table 1.3 (equipment_ownership)
            equipment_ownership = extracted_data.get('equipment_ownership', [])
            if equipment_ownership:
                first_row = equipment_ownership[0]
                has_capacity = 'capacity' in first_row
                has_separate = 'cooling_capacity' in first_row or 'power_capacity' in first_row
                extracted_data['is_capacity_merged_table_1_3'] = has_capacity and not has_separate
        
        else:  # '02'
            # Check table 2.2 (equipment_product_report)
            equipment_product_report = extracted_data.get('equipment_product_report', [])
            if equipment_product_report:
                first_row = equipment_product_report[0]
                has_capacity = 'capacity' in first_row
                has_separate = 'cooling_capacity' in first_row or 'power_capacity' in first_row
                extracted_data['is_capacity_merged_table_2_2'] = has_capacity and not has_separate
            
            # Check table 2.3 (equipment_ownership_report)
            equipment_ownership_report = extracted_data.get('equipment_ownership_report', [])
            if equipment_ownership_report:
                first_row = equipment_ownership_report[0]
                has_capacity = 'capacity' in first_row
                has_separate = 'cooling_capacity' in first_row or 'power_capacity' in first_row
                extracted_data['is_capacity_merged_table_2_3'] = has_capacity and not has_separate
    
    def _infer_activity_field_codes(self, extracted_data):
        """
        Infer activity_field_codes by checking all tables in extracted_data

        No need for document_type - just loop through all possible tables
        and use TABLE_ACTIVITY_MAPPINGS to extract codes.
        """
        activity_codes = set()
        
        # Loop through all table mappings
        for table_key, config in TABLE_ACTIVITY_MAPPINGS.items():
            table_data = extracted_data.get(table_key)
            if not table_data:
                continue
            
            # Extract codes from title-data pairs
            codes = self._extract_activity_codes_from_table(
                table_data,
                field_name=config['field_name'],
                mappings=config['keywords']
            )
            activity_codes.update(codes)
        
        # Store result
        extracted_data['activity_field_codes'] = sorted(list(activity_codes)) if activity_codes else extracted_data.get('activity_field_codes', [])
        
        if activity_codes:
            _logger.info(f"Inferred activity_field_codes: {extracted_data['activity_field_codes']}")
    
    def _extract_activity_codes_from_table(self, table_data, field_name, mappings):
        """
        Extract activity codes from a table by tracking title-data relationships

        Logic:
        1. Create dict to track which titles have data after them: {title_index: {'title': text, 'has_data': False}}
        2. Loop through rows:
           - If is_title=True: Add to dict with index, set current_title_idx
           - If is_title=False: Mark current_title_idx as has_data=True
        3. After loop: Check all titles that have data, match keywords (case-insensitive + regex)

        Args:
            table_data (list): Table rows
            field_name (str): Field name to check in title rows
            mappings (dict): Keyword (regex pattern) → activity code mapping

        Returns:
            set: Activity codes found
        """
        import re

        # Track which titles have data after them
        title_data = {}  # {index: {'title': text, 'has_data': False}}
        current_title_idx = None

        for idx, row in enumerate(table_data):
            if row.get('is_title'):
                # Found a title row
                title_text = row.get(field_name) or row.get('substance_name') or row.get('product_type') or row.get('equipment_type') or row.get('activity_type') or ''
                title_data[idx] = {'title': title_text, 'has_data': False}
                current_title_idx = idx
            else:
                # Data row - mark current title as having data
                if current_title_idx is not None:
                    title_data[current_title_idx]['has_data'] = True

        # Extract codes from titles that have data
        codes = set()
        for info in title_data.values():
            if info['has_data']:
                title_lower = info['title'].lower()
                for keyword, code in mappings.items():
                    # Match using both methods for maximum flexibility:
                    # 1. Case-insensitive substring match
                    # 2. Regex match with IGNORECASE (escape keyword to handle special chars)
                    if keyword.lower() in title_lower or re.search(keyword, info['title'], re.IGNORECASE):
                        codes.add(code)

        return codes
    
    def _has_valid_data_rows(self, table_data):
        """
        Check if table has at least one valid data row (not title, not empty)
        
        Args:
            table_data (list): Table rows
            
        Returns:
            bool: True if has valid data rows
        """
        for row in table_data:
            if not row.get('is_title'):
                # Check if row has any meaningful data (not all null)
                has_data = any(
                    v is not None and v != '' and v != 0
                    for k, v in row.items()
                    if k not in ['is_title', 'sequence']
                )
                if has_data:
                    return True
        return False

    def _validate_has_table_flag(self, ai_value, table_data):
        """
        Validate has_table flag with AI priority logic

        Philosophy: Trust AI when it says True, validate when it says False

        Args:
            ai_value (bool): AI-extracted has_table flag value
            table_data (list): Table data rows from extracted_data

        Returns:
            bool: Validated flag value

        Logic:
            - If AI says True → Trust AI (return True)
            - If AI says False → Check actual data using _has_valid_data_rows()
              - If actual data exists → Override to True
              - If no actual data → Keep False
        """
        # Trust AI when it detects a table
        if ai_value:
            return True

        # AI says False - verify with actual data check
        # This catches false negatives (AI missed a table that actually has data)
        has_actual_data = self._has_valid_data_rows(table_data)

        if has_actual_data:
            _logger.info(
                f"AI missed table (AI=False but actual data exists) - overriding to True"
            )

        return has_actual_data


    @api.model
    def _get_vietnamese_provinces_list(self):
        """
        Get Vietnamese provinces/cities list from database

        Returns:
            str: Formatted list of province codes and names
        """
        states = self.env['res.country.state'].search([
            ('country_id.code', '=', 'VN')
        ], order='code')

        provinces = [f"{state.code}: {state.name}" for state in states]
        return "\n".join(provinces)

    def _initialize_default_prompts(self):
        """
        Initialize default extraction prompts in system parameters
        Called during module installation via XML data file
        """
        params = self.env['ir.config_parameter'].sudo()

        # Set Form 01 default prompt if not exists
        if not params.get_param('robotia_document_extractor.extraction_prompt_form_01'):
            params.set_param(
                'robotia_document_extractor.extraction_prompt_form_01',
                self._get_default_prompt_form_01()
            )

        # Set Form 02 default prompt if not exists
        if not params.get_param('robotia_document_extractor.extraction_prompt_form_02'):
            params.set_param(
                'robotia_document_extractor.extraction_prompt_form_02',
                self._get_default_prompt_form_02()
            )

    def extract_pdf(self, pdf_binary, document_type, log_id=None,
                    job_id=None, resume_from_step=None):
        """
        Extract structured data from PDF using configurable extraction strategy

        Available Strategies (configured in Settings):
        - ai_native: 100% AI (Gemini processes PDF directly)
        - llama_split: LlamaParse OCR + Gemini Chat (with step-based checkpointing)
        - text_extract: Text Extraction + AI (PyMuPDF extracts text, then AI structures) [DEPRECATED]

        Args:
            pdf_binary (bytes): Binary PDF data
            document_type (str): '01' for Registration, '02' for Report
            log_id (int, optional): Extraction log ID for saving OCR data
            job_id (int, optional): Extraction job ID for step checkpointing (llama_split only)
            resume_from_step (str, optional): Step to resume from (llama_split only)

        Returns:
            dict: Structured data extracted from PDF

        Raises:
            ValueError: If API key not configured or extraction fails
        """
        _logger.info(f"Starting AI extracting document (Type: {document_type})")

        # Clean up stale temp files first
        self.cleanup_temp_extraction_files()

        # Get configuration
        ICP = self.env['ir.config_parameter'].sudo()
        api_key = ICP.get_param('robotia_document_extractor.gemini_api_key')
        strategy = ICP.get_param('robotia_document_extractor.extraction_strategy', default='ai_native')

        if not api_key:
            raise ValueError(
                "Gemini API key not configured. "
                "Please configure it in Settings > Document Extractor > Configuration"
            )

        # Configure Gemini
        client = genai.Client(api_key=api_key)

        _logger.info(f"Using extraction strategy: {strategy}")

        # Route to appropriate strategy
        if strategy == 'ai_native':
            # Strategy 1: 100% AI (Gemini processes PDF directly)
            return self._extract_with_ai_native(client, pdf_binary, document_type)

        elif strategy == 'llama_split':
            # Strategy 2: LlamaParse OCR + Gemini Chat (with step checkpointing)
            return self._extract_with_llama_extract(
                client,
                pdf_binary,
                document_type,
                log_id,
                job_id=job_id,
                resume_from_step=resume_from_step
            )

        else:
            _logger.warning(f"Unknown strategy '{strategy}', falling back to ai_native")
            return self._extract_with_ai_native(client, pdf_binary, document_type)

    def _extract_with_ai_native(self, client, pdf_binary, document_type):
        """
        Strategy: 100% AI (Gemini processes PDF directly)

        Primary method with automatic fallback to 2-step if needed.
        """
        # Try direct PDF → JSON extraction
        try:
            _logger.info("=" * 70)
            _logger.info("AI NATIVE: Direct PDF → JSON extraction")
            _logger.info("=" * 70)
            extracted_data = self._extract_direct_pdf_to_json(client, pdf_binary, document_type)
            _logger.info("✓ AI Native succeeded")
            return extracted_data

        except Exception as e:
            _logger.error("✗ AI Native extraction failed")
            _logger.error(f"Error: {type(e).__name__}: {str(e)}")
            raise ValueError(f"AI Native extraction failed. Error: {str(e)}")

    def _extract_direct_pdf_to_json(self, client, pdf_binary, document_type):
        """
        Strategy 1: Direct PDF → JSON extraction (original method)

        Args:
            client: Gemini client instance
            pdf_binary (bytes): Binary PDF data
            document_type (str): '01' or '02'

        Returns:
            dict: Extracted and cleaned data

        Raises:
            ValueError: If extraction fails after all retries
        """
        # Build extraction prompt based on document type
        prompt = self._build_extraction_prompt(document_type)

        _logger.info(f"Calling Gemini API for extraction (PDF size: {len(pdf_binary)} bytes)")

        # Upload PDF file to Gemini
        # Note: Gemini requires file upload for large documents

        # Get max retries from config (default: 3)
        GEMINI_MAX_RETRIES = int(
            self.env['ir.config_parameter'].sudo().get_param(
                'robotia_document_extractor.gemini_max_retries',
                default='3'
            )
        )

        tmp_file_path = None
        uploaded_file = None

        try:
            tmp_file_path = self.make_temp_file(pdf_binary)

            _logger.info(f"Created temp file: {tmp_file_path}")

            # Upload file to Gemini
            uploaded_file = self.upload_file_to_gemini(client, tmp_file_path)

            # Build mega prompt context (substances list + mapping rules)
            mega_context = self._build_mega_prompt_context()

            # Generate content with retry logic for incomplete responses
            extracted_text = None
            last_error = None

            for retry_attempt in range(GEMINI_MAX_RETRIES):
                try:
                    _logger.info(f"Gemini API call attempt {retry_attempt + 1}/{GEMINI_MAX_RETRIES}")

                    # Generate content with mega context + uploaded file + prompt
                    response = self.generate_content(client, mega_context + [uploaded_file, prompt])

                    # Get response text
                    extracted_text = response.text

                    # Check finish_reason to detect truncation
                    finish_reason = None
                    if hasattr(response, 'candidates') and response.candidates:
                        candidate = response.candidates[0]
                        finish_reason = candidate.finish_reason if hasattr(candidate, 'finish_reason') else None

                        # Log finish reason for debugging
                        _logger.info(f"Gemini finish_reason: {finish_reason}")

                        # Check if response was cut off due to token limit
                        if finish_reason and str(finish_reason) in ['MAX_TOKENS', 'LENGTH']:
                            _logger.warning(
                                f"Response was truncated due to {finish_reason}. "
                                f"Response length: {len(extracted_text)} chars. "
                                f"This attempt will likely fail validation."
                            )

                    _logger.info(f"Gemini API response received (length: {len(extracted_text)} chars)")

                    # Validate that response is complete (can be parsed as JSON)
                    # This will throw JSONDecodeError if incomplete
                    try:
                        self._parse_json_response(extracted_text)
                        _logger.info(f"Response validation successful on attempt {retry_attempt + 1}")
                        break  # Success - exit retry loop
                    except json.JSONDecodeError:
                        # Re-raise to be caught by outer except block
                        raise

                except json.JSONDecodeError as e:
                    last_error = e
                    _logger.warning(f"Attempt {retry_attempt + 1} returned incomplete JSON: {str(e)}")
                    if retry_attempt < GEMINI_MAX_RETRIES - 1:
                        _logger.info(f"Retrying immediately...")
                    else:
                        # Last attempt failed - will be caught below
                        _logger.error("All retry attempts failed - response still incomplete")
                except Exception as e:
                    last_error = e
                    _logger.warning(f"Attempt {retry_attempt + 1} failed: {type(e).__name__}: {str(e)}")
                    if retry_attempt < GEMINI_MAX_RETRIES - 1:
                        _logger.info(f"Retrying immediately...")
                    else:
                        raise

            # Check if we got a valid response after all retries
            if not extracted_text:
                raise ValueError(f"Failed to get complete response after {GEMINI_MAX_RETRIES} attempts: {last_error}")

        except Exception as e:
            _logger.exception(f"Extraction failed during Gemini API call")
            raise ValueError(f"Extraction failed: {type(e).__name__}: {str(e)}")

        finally:
            # ALWAYS cleanup temporary file
            if tmp_file_path and os.path.exists(tmp_file_path):
                try:
                    os.unlink(tmp_file_path)
                    _logger.info(f"Cleaned up temp file: {tmp_file_path}")
                except Exception as e:
                    _logger.warning(f"Failed to cleanup temp file {tmp_file_path}: {e}")

            # ALWAYS cleanup Gemini uploaded file
            if uploaded_file:
                try:
                    client.files.delete(name=uploaded_file.name)
                    _logger.info(f"Deleted Gemini file: {uploaded_file.name}")
                except Exception as e:
                    _logger.warning(f"Failed to delete Gemini file: {e}")

        # Parse JSON from response using helper method
        try:
            extracted_data = self._parse_json_response(extracted_text)
            _logger.info("Successfully parsed JSON response")

        except json.JSONDecodeError as e:
            _logger.error(f"Failed to parse JSON: {e}\nResponse preview: {extracted_text[:500]}...")
            _logger.error(f"Response tail (last 500 chars): ...{extracted_text[-500:]}")
            raise ValueError(
                f"Failed to parse AI response as JSON. "
                f"Response may be incomplete (length: {len(extracted_text)} chars). "
                f"Error: {e}"
            )

        # Validate and clean extracted data
        cleaned_data = self._clean_extracted_data(extracted_data, document_type)

        return cleaned_data

    def _build_mega_prompt_context(self):
        """
        Build mega prompt context with all controlled substances from database

        Returns a list of types.Part.from_text objects that serve as system context for AI extraction.
        This context includes:
        - List of all controlled substances with names, codes, and GWP values
        - Standardization rules for substance name mapping
        - Examples of common format variations

        Returns:
            list: List containing types.Part.from_text with mega prompt context
                  Can be extended with additional context prompts in the future
        """
        # Query all active controlled substances from database
        substances = self.env['controlled.substance'].search([
            ('active', '=', True)
        ], order='code')

        # Query all active activity fields from database
        activity_fields = self.env['activity.field'].search([
            ('active', '=', True)
        ], order='sequence')

        # Get Vietnamese provinces/cities list
        provinces_list = self._get_vietnamese_provinces_list()

        # Build context prompts using new prompt functions
        substance_prompt = context_prompts.get_substance_mapping_prompt(substances)
        activity_prompt = context_prompts.get_activity_fields_prompt(activity_fields)
        province_prompt = context_prompts.get_province_lookup_prompt(provinces_list)

        # Return as list of types.Part.from_text
        return [
            types.Part.from_text(text=substance_prompt),
            types.Part.from_text(text=activity_prompt),
            types.Part.from_text(text=province_prompt)
        ]

    def _build_extraction_prompt(self, document_type):
        """
        Build structured extraction prompt based on document type

        Reads prompt from system parameters, falls back to default if not configured

        Args:
            document_type (str): '01' or '02'

        Returns:
            str: Extraction prompt for Gemini
        """
        # Read prompt from system parameters
        param_key = f'robotia_document_extractor.extraction_prompt_form_{document_type}'
        custom_prompt = self.env['ir.config_parameter'].sudo().get_param(param_key)

        if custom_prompt:
            return custom_prompt

        # Fallback to default prompts
        if document_type == '01':
            return self._get_default_prompt_form_01()
        else:
            return self._get_default_prompt_form_02()

    def _get_default_prompt_form_01(self):
        """
        Get default extraction prompt for Form 01 (Registration)

        Returns:
            str: Default Form 01 extraction prompt
        """
        return strategy_prompts.get_ai_native_prompt('01')

    def _get_default_prompt_form_02(self):
        """
        Get default extraction prompt for Form 02 (Report)

        Returns:
            str: Default Form 02 extraction prompt
        """
        return strategy_prompts.get_ai_native_prompt('02')

    def _parse_json_response(self, response_text):
        """
        Robust JSON parser that handles multiple response formats from Gemini

        Args:
            response_text (str): Raw response text from Gemini API

        Returns:
            dict: Parsed JSON data

        Raises:
            json.JSONDecodeError: If response cannot be parsed as valid JSON
        """
        if not response_text or not response_text.strip():
            raise json.JSONDecodeError("Empty response", "", 0)

        text = response_text.strip()

        # Strategy 1: Try parsing as-is (when response_mime_type='application/json')
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass  # Try other strategies

        # Strategy 2: Extract from markdown code block ```json ... ```
        if '```json' in text:
            try:
                json_start = text.find('```json') + 7
                json_end = text.find('```', json_start)
                if json_end == -1:
                    # Closing ``` not found - response is incomplete
                    raise json.JSONDecodeError(
                        "Incomplete markdown JSON block - missing closing ```",
                        text,
                        json_start
                    )
                json_str = text[json_start:json_end].strip()
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass  # Try next strategy

        # Strategy 3: Extract from generic code block ``` ... ```
        if '```' in text:
            try:
                json_start = text.find('```') + 3
                # Skip language identifier if present (e.g., ```javascript)
                newline_pos = text.find('\n', json_start)
                if newline_pos != -1 and newline_pos - json_start < 20:
                    json_start = newline_pos + 1

                json_end = text.find('```', json_start)
                if json_end == -1:
                    # Closing ``` not found - response is incomplete
                    raise json.JSONDecodeError(
                        "Incomplete markdown code block - missing closing ```",
                        text,
                        json_start
                    )
                json_str = text[json_start:json_end].strip()
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass  # Try next strategy

        # Strategy 4: Find JSON object boundaries { ... }
        if '{' in text and '}' in text:
            try:
                json_start = text.find('{')
                json_end = text.rfind('}') + 1
                json_str = text[json_start:json_end]
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass

        # All strategies failed - raise detailed error
        preview_len = min(200, len(text))
        raise json.JSONDecodeError(
            f"Could not parse response as JSON. Tried multiple strategies. "
            f"Response preview: {text[:preview_len]}...",
            text,
            0
        )

    def _clean_extracted_data(self, data, document_type):
        """
        Clean and validate extracted data

        Args:
            data (dict): Raw extracted data
            document_type (str): '01' or '02'

        Returns:
            dict: Cleaned and validated data
        """
        # Ensure all expected keys exist with default values
        cleaned = {
            'year': data.get('year'),
            'year_1': data.get('year_1'),
            'year_2': data.get('year_2'),
            'year_3': data.get('year_3'),
            'organization_name': data.get('organization_name', ''),
            'business_id': data.get('business_id', ''),
            'business_license_date': data.get('business_license_date'),
            'business_license_place': data.get('business_license_place', ''),
            'legal_representative_name': data.get('legal_representative_name', ''),
            'legal_representative_position': data.get('legal_representative_position', ''),
            'contact_person_name': data.get('contact_person_name', ''),
            'contact_address': data.get('contact_address', ''),
            'contact_phone': data.get('contact_phone', ''),
            'contact_fax': data.get('contact_fax', ''),
            'contact_email': data.get('contact_email', ''),
            'contact_country_code': data.get('contact_country_code', ''),
            'contact_state_code': data.get('contact_state_code', ''),
            'activity_field_codes': data.get('activity_field_codes', []),
        }

        # Add table data based on document type
        if document_type == '01':
            cleaned.update({
                'has_table_1_1': data.get('has_table_1_1', False),
                'has_table_1_2': data.get('has_table_1_2', False),
                'has_table_1_3': data.get('has_table_1_3', False),
                'has_table_1_4': data.get('has_table_1_4', False),
                'is_capacity_merged_table_1_2': data.get('is_capacity_merged_table_1_2', True),
                'is_capacity_merged_table_1_3': data.get('is_capacity_merged_table_1_3', True),
                'substance_usage': data.get('substance_usage', []),
                'equipment_product': data.get('equipment_product', []),
                'equipment_ownership': data.get('equipment_ownership', []),
                'collection_recycling': data.get('collection_recycling', []),
            })
        else:  # '02'
            cleaned.update({
                'has_table_2_1': data.get('has_table_2_1', False),
                'has_table_2_2': data.get('has_table_2_2', False),
                'has_table_2_3': data.get('has_table_2_3', False),
                'has_table_2_4': data.get('has_table_2_4', False),
                'is_capacity_merged_table_2_2': data.get('is_capacity_merged_table_2_2', True),
                'is_capacity_merged_table_2_3': data.get('is_capacity_merged_table_2_3', True),
                'quota_usage': data.get('quota_usage', []),
                'equipment_product_report': data.get('equipment_product_report', []),
                'equipment_ownership_report': data.get('equipment_ownership_report', []),
                'collection_recycling_report': data.get('collection_recycling_report', []),
            })

        _logger.info(f"Data cleaned successfully (Type: {document_type})")
        return cleaned
