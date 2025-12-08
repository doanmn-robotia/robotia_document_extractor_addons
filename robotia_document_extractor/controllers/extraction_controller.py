# -*- coding: utf-8 -*-

from odoo import http, _
from odoo.http import request
import base64
import logging
import json
import traceback

_logger = logging.getLogger(__name__)


class ExtractionController(http.Controller):
    """
    JSON-RPC Controller for document extraction

    IMPORTANT: This controller does NOT create records immediately.
    It extracts data and returns an action to open form in CREATE mode.
    """

    @staticmethod
    def _calculate_avg_quantity(usage_record):
        """
        Calculate correct average quantity from 3-year data

        FIX: Divide by count of non-null years, not always 3

        Args:
            usage_record: substance.usage record with year_1/2/3 fields

        Returns:
            tuple: (avg_kg, avg_co2)
        """
        # If avg fields already computed, use them
        if usage_record.avg_quantity_kg is not None and usage_record.avg_quantity_co2 is not None:
            return (usage_record.avg_quantity_kg, usage_record.avg_quantity_co2)

        # Count non-null years for kg
        kg_values = [
            usage_record.year_1_quantity_kg,
            usage_record.year_2_quantity_kg,
            usage_record.year_3_quantity_kg
        ]
        co2_values = [
            usage_record.year_1_quantity_co2,
            usage_record.year_2_quantity_co2,
            usage_record.year_3_quantity_co2
        ]

        kg_count = sum(1 for v in kg_values if v is not None)
        co2_count = sum(1 for v in co2_values if v is not None)

        # Calculate average (divide by actual count, not 3)
        avg_kg = sum(v for v in kg_values if v is not None) / kg_count if kg_count > 0 else 0
        avg_co2 = sum(v for v in co2_values if v is not None) / co2_count if co2_count > 0 else 0

        return (avg_kg, avg_co2)

    def _process_pdf_extraction(self, pdf_binary, filename, document_type, run_ocr=False):
        """
        SHARED HELPER: Process PDF extraction with transaction-safe logging

        This method ensures EVERY AI call is logged accurately with:
        - Input file (attachment) ALWAYS created before AI call
        - AI response JSON (if extraction succeeds)
        - Exact status (success/error) reflecting actual result
        - Detailed error messages for all failure scenarios

        CRITICAL LOGGING GUARANTEE:
        - Log created FIRST with 'processing' status
        - Attachment created IMMEDIATELY (before AI call)
        - Log updated to 'success' ONLY when entire pipeline succeeds
        - Log updated to 'error' with details for ANY failure
        - Exception handling catches ALL possible errors

        Args:
            pdf_binary (bytes): PDF binary data
            filename (str): Original filename
            document_type (str): '01' or '02'
            run_ocr (bool): Whether to run OCR extraction (default: False)

        Returns:
            dict: {
                'success': True/False,
                'extracted_data': {...},  # AI extracted data (None if failed)
                'raw_ocr_data': {...},    # OCR data with bbox (None if run_ocr=False or OCR fails)
                'attachment': ir.attachment record (always present if validation passed),
                'log': google.drive.extraction.log record (always present),
                'error': None or dict with error notification params
            }
        """
        # Constants
        MAX_PDF_SIZE_MB = 50
        MAX_PDF_SIZE_BYTES = MAX_PDF_SIZE_MB * 1024 * 1024
        EXTRACTION_RATE_LIMIT_SECONDS = 5

        # Variables to track cleanup
        log = None
        attachment = None
        extracted_data = None
        raw_ocr_data = None

        try:
            # ===== STEP 1: Create log FIRST (with 'processing' status) =====
            log = request.env['google.drive.extraction.log'].sudo().create({
                'drive_file_id': False,  # No Drive ID for manual uploads
                'file_name': filename,
                'document_type': document_type,
                'status': 'processing',
            })
            _logger.info(f"[Log {log.id}] Created log for {filename} (Type: {document_type}, OCR: {run_ocr})")

            # ===== STEP 2: Validation (before creating attachment) =====

            # 2.1 Validate file extension
            if not filename.lower().endswith('.pdf'):
                error_msg = 'Invalid file type: Only PDF files are allowed'
                log.write({'status': 'error', 'error_message': error_msg})
                _logger.warning(f"[Log {log.id}] {error_msg}")
                return {
                    'success': False,
                    'extracted_data': None,
                    'raw_ocr_data': None,
                    'attachment': None,
                    'log': log,
                    'error': {
                        'title': _('Invalid File Type'),
                        'message': _('Only PDF files are allowed'),
                        'type': 'danger',
                    }
                }

            # 2.2 Validate file size
            pdf_size_bytes = len(pdf_binary)
            if pdf_size_bytes > MAX_PDF_SIZE_BYTES:
                pdf_size_mb = pdf_size_bytes / 1024 / 1024
                error_msg = f'File too large: {pdf_size_mb:.1f}MB (max {MAX_PDF_SIZE_MB}MB)'
                log.write({'status': 'error', 'error_message': error_msg})
                _logger.warning(f"[Log {log.id}] {error_msg}")
                return {
                    'success': False,
                    'extracted_data': None,
                    'raw_ocr_data': None,
                    'attachment': None,
                    'log': log,
                    'error': {
                        'title': _('File Too Large'),
                        'message': _('File size (%(size).1fMB) exceeds %(max)dMB') % {'size': pdf_size_mb, 'max': MAX_PDF_SIZE_MB},
                        'type': 'danger',
                    }
                }

            # 2.3 Validate PDF magic bytes
            if not pdf_binary.startswith(b'%PDF'):
                error_msg = 'Invalid PDF format: File does not start with PDF signature'
                log.write({'status': 'error', 'error_message': error_msg})
                _logger.warning(f"[Log {log.id}] {error_msg}")
                return {
                    'success': False,
                    'extracted_data': None,
                    'raw_ocr_data': None,
                    'attachment': None,
                    'log': log,
                    'error': {
                        'title': _('Invalid PDF'),
                        'message': _('The uploaded file does not appear to be a valid PDF'),
                        'type': 'danger',
                    }
                }

            # 2.4 Rate limiting (session-based)
            import time
            last_extract_time = request.session.get('last_extract_time', 0)
            current_time = time.time()
            if current_time - last_extract_time < EXTRACTION_RATE_LIMIT_SECONDS:
                wait_seconds = int(EXTRACTION_RATE_LIMIT_SECONDS - (current_time - last_extract_time))
                error_msg = f'Rate limit exceeded: Please wait {wait_seconds}s'
                log.write({'status': 'error', 'error_message': error_msg})
                _logger.warning(f"[Log {log.id}] {error_msg}")
                return {
                    'success': False,
                    'extracted_data': None,
                    'raw_ocr_data': None,
                    'attachment': None,
                    'log': log,
                    'error': {
                        'title': _('Please Wait'),
                        'message': _('Please wait %(seconds)d seconds before extracting another document') % {'seconds': wait_seconds},
                        'type': 'warning',
                    }
                }
            request.session['last_extract_time'] = current_time

            # ===== STEP 3: Create attachment BEFORE AI call (CRITICAL for logging) =====
            try:
                attachment = request.env['ir.attachment'].sudo().create({
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
                    'raw_ocr_data': None,
                    'attachment': None,
                    'log': log,
                    'error': {
                        'title': _('Upload Failed'),
                        'message': _('Failed to upload PDF file to server'),
                        'type': 'danger',
                    }
                }

            # ===== STEP 4: Run OCR if requested (optional, non-critical) =====
            if run_ocr:
                try:
                    _logger.info(f"[Log {log.id}] Running OCR extraction...")
                    OCRService = request.env['document.ocr.raw.service'].sudo()
                    raw_ocr_data = OCRService.extract_ocr_with_bbox(pdf_binary, filename)

                    if raw_ocr_data:
                        total_regions = sum(len(p.get('text_regions', [])) for p in raw_ocr_data.get('pages', []))
                        _logger.info(f"[Log {log.id}] OCR completed: {len(raw_ocr_data.get('pages', []))} pages, {total_regions} text regions")
                    else:
                        _logger.warning(f"[Log {log.id}] OCR returned no data - continuing with AI only")
                except Exception as e:
                    _logger.warning(f"[Log {log.id}] OCR failed (continuing with AI only): {e}")
                    raw_ocr_data = None
                    # Continue without OCR - graceful degradation

            # ===== STEP 5: Run AI extraction (CRITICAL - must catch all errors) =====
            try:
                _logger.info(f"[Log {log.id}] Starting AI extraction...")
                extraction_service = request.env['document.extraction.service']
                extracted_data = extraction_service.extract_pdf(pdf_binary, document_type, filename)
                _logger.info(f"[Log {log.id}] AI extraction completed successfully")
            except Exception as e:
                error_msg = f'AI extraction failed: {str(e)}'
                error_traceback = traceback.format_exc()

                # Update log with detailed error
                log.write({
                    'status': 'error',
                    'error_message': error_traceback,
                    'ai_response_json': extracted_data,  # Store full traceback for debugging
                })
                _logger.error(f"[Log {log.id}] {error_msg}", exc_info=True)

                return {
                    'success': False,
                    'extracted_data': None,
                    'raw_ocr_data': raw_ocr_data,
                    'attachment': attachment,
                    'log': log,
                    'error': {
                        'title': _('AI Extraction Failed'),
                        'message': str(e),
                        'type': 'danger',
                    }
                }

            # ===== STEP 6: Post-processing (auto-calculate years) =====
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

            # ===== STEP 7: Update log to SUCCESS (ONLY if everything succeeded) =====
            try:
                log_data = {
                    'status': 'success',
                    'ai_response_json': json.dumps(extracted_data, ensure_ascii=False, indent=2),
                }
                # Add OCR data if available
                if raw_ocr_data:
                    log_data['ocr_response_json'] = json.dumps(raw_ocr_data, ensure_ascii=False, indent=2)

                log.write(log_data)
                _logger.info(f"[Log {log.id}] Extraction pipeline completed successfully")
            except Exception as e:
                # Critical: Failed to save log data
                error_msg = f'Failed to save extraction results to log: {str(e)}'
                _logger.error(f"[Log {log.id}] {error_msg}", exc_info=True)
                # Try to update log status
                try:
                    log.write({'status': 'error', 'error_message': error_msg, 'ai_response_json': extracted_data})
                except:
                    pass

                return {
                    'success': False,
                    'extracted_data': extracted_data,
                    'raw_ocr_data': raw_ocr_data,
                    'attachment': attachment,
                    'log': log,
                    'error': {
                        'title': _('Save Failed'),
                        'message': _('Extraction succeeded but failed to save results'),
                        'type': 'danger',
                    }
                }

            # ===== SUCCESS: Return complete result =====
            return {
                'success': True,
                'extracted_data': extracted_data,
                'raw_ocr_data': raw_ocr_data,
                'attachment': attachment,
                'log': log,
                'error': None,
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
                        'ai_response_json': extracted_data,  # Store full traceback
                    })
                except Exception as log_error:
                    _logger.error(f"Failed to update log: {log_error}")

            return {
                'success': False,
                'extracted_data': None,
                'raw_ocr_data': None,
                'attachment': attachment,  # May be None if error before attachment creation
                'log': log,  # May be None if error before log creation
                'error': {
                    'title': _('Unexpected Error'),
                    'message': str(e),
                    'type': 'danger',
                }
            }

    @http.route('/document_extractor/extract', type='json', auth='user', methods=['POST'])
    def extract_document(self, pdf_data, filename, document_type):
        """
        Extract data from PDF using AI only (no OCR)

        Args:
            pdf_data (str): Base64 encoded PDF file
            filename (str): Original filename
            document_type (str): '01' for Registration, '02' for Report

        Returns:
            dict: Action to open form OR error notification
        """
        # Decode PDF
        try:
            pdf_binary = base64.b64decode(pdf_data)
        except Exception as e:
            _logger.error(f"Failed to decode PDF: {e}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('Failed to decode PDF file'),
                    'type': 'danger',
                    'sticky': False,
                }
            }

        # Call shared helper (NO OCR for direct upload route)
        result = self._process_pdf_extraction(
            pdf_binary=pdf_binary,
            filename=filename,
            document_type=document_type,
            run_ocr=False  # AI-only extraction
        )

        # Handle error
        if not result['success']:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    **result['error'],
                    'sticky': result['error']['type'] == 'danger',
                }
            }

        # Build form values using extraction helper
        helper = request.env['extraction.helper']
        vals = helper.build_extraction_values(
            extracted_data=result['extracted_data'],
            attachment=result['attachment'],
            document_type=document_type
        )

        # Add raw_ocr_data (will be None for this route)
        vals['raw_ocr_data'] = json.dumps(result['raw_ocr_data']) if result['raw_ocr_data'] else None

        # Convert to context
        context = {f'default_{key}': value for key, value in vals.items()}
        context['default_extraction_log_id'] = result['log'].id
        context['default_source'] = 'from_user_upload'

        _logger.info(f"Returning form action for {filename}")

        # Return form action
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'document.extraction',
            'view_mode': 'form',
            'views': [[False, 'form']],
            'target': 'current',
            'context': context,
        }

    @http.route('/robotia/pdf_to_images', type='json', auth='user', methods=['POST'])
    def pdf_to_images(self, pdf_file):
        """
        Convert PDF to images and store as public attachments

        Args:
            pdf_file (str): Base64 encoded PDF

        Returns:
            dict: {
                'status': 'success',
                'pages': [
                    {
                        'attachment_id': 123,
                        'url': '/web/content/123',
                        'page_num': 0,
                        'filename': 'page_0.png'
                    },
                    ...
                ]
            }
        """
        try:
            # Decode PDF
            pdf_binary = base64.b64decode(pdf_file)

            # Convert to images
            ExtractionService = request.env['document.extraction.service'].sudo()
            image_paths = ExtractionService._pdf_to_images(pdf_binary, "temp_upload.pdf")

            # Create attachments for each image
            Attachment = request.env['ir.attachment'].sudo()
            pages_metadata = []

            for idx, path in enumerate(image_paths):
                try:
                    # Read image file
                    with open(path, "rb") as image_file:
                        image_binary = image_file.read()

                    # Create public attachment
                    filename = f"page_{idx}.png"
                    attachment = Attachment.create({
                        'name': filename,
                        'type': 'binary',
                        'datas': base64.b64encode(image_binary).decode('utf-8'),
                        'res_model': 'document.extraction',
                        'res_id': 0,  # Temporary attachment
                        'public': True,  # Makes accessible via URL
                        'mimetype': 'image/png',
                        'description': f'PDF page preview {idx}',
                    })

                    # Build metadata
                    pages_metadata.append({
                        'attachment_id': attachment.id,
                        'url': f'/web/content/{attachment.id}',
                        'page_num': idx,
                        'filename': filename,
                    })

                    _logger.info(f"Created attachment {attachment.id} for page {idx}")

                finally:
                    # Clean up temp file
                    try:
                        import os
                        os.remove(path)
                    except Exception as cleanup_error:
                        _logger.warning(f"Failed to cleanup {path}: {cleanup_error}")

            return {
                'status': 'success',
                'pages': pages_metadata
            }

        except Exception as e:
            _logger.exception("Error converting PDF to images")
            return {'status': 'error', 'message': str(e)}

    @http.route('/robotia/extract_pages', type='json', auth='user', methods=['POST'])
    def extract_pages(self, pdf_file, attachment_ids, document_type='01', filename=None):
        """
        Extract specific pages from PDF with OCR + AI

        Args:
            pdf_file (str): Base64 encoded PDF (original full PDF)
            attachment_ids (list): List of attachment IDs representing selected pages
            document_type (str): '01' or '02'
            filename (str): Original filename from user upload

        Returns:
            dict: Action to open document.extraction form
        """
        try:
            import fitz  # PyMuPDF
            import io

            # 1. Get page numbers from attachments
            Attachment = request.env['ir.attachment'].sudo()
            attachments = Attachment.browse(attachment_ids)

            if not attachments:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Invalid Selection'),
                        'message': _('No valid pages selected'),
                        'type': 'danger',
                    }
                }

            # Extract page numbers from attachment names
            # Assuming attachment.name = "page_0.png", "page_1.png", etc.
            page_indices = []
            for att in attachments:
                try:
                    # Extract number from "page_0.png" → 0
                    page_num = int(att.name.replace('page_', '').replace('.png', ''))
                    page_indices.append(page_num)
                except ValueError:
                    _logger.warning(f"Could not parse page number from {att.name}")

            if not page_indices:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Invalid Selection'),
                        'message': _('Could not determine page numbers'),
                        'type': 'danger',
                    }
                }

            # Sort to maintain order
            page_indices.sort()
            _logger.info(f"Extracting pages: {page_indices}")

            # 2. Create PDF with selected pages
            pdf_binary = base64.b64decode(pdf_file)
            doc = fitz.open(stream=pdf_binary, filetype="pdf")

            new_doc = fitz.open()
            for index in page_indices:
                if 0 <= index < len(doc):
                    new_doc.insert_pdf(doc, from_page=index, to_page=index)

            output_stream = io.BytesIO()
            new_doc.save(output_stream)
            new_pdf_binary = output_stream.getvalue()
            doc.close()
            new_doc.close()

            # Use original filename if provided, otherwise generate one
            if not filename:
                filename = f"extracted_pages_{document_type}.pdf"

            # 3. Call shared helper (WITH OCR if configured)
            run_ocr = request.env['ir.config_parameter'].sudo().get_param(
                'robotia_document_extractor.extract_pages_run_ocr', 'False'
            ).lower() == 'true'

            result = self._process_pdf_extraction(
                pdf_binary=new_pdf_binary,
                filename=filename,
                document_type=document_type,
                run_ocr=run_ocr
            )

            # Handle error
            if not result['success']:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Extraction Failed'),
                        'message': result['error']['message'],
                        'type': 'danger',
                    }
                }

            # Build form values using extraction helper
            helper = request.env['extraction.helper']
            vals = helper.build_extraction_values(
                extracted_data=result['extracted_data'],
                attachment=result['attachment'],
                document_type=document_type
            )

            # Add raw_ocr_data (will have data from OCR)
            vals['raw_ocr_data'] = json.dumps(result['raw_ocr_data']) if result['raw_ocr_data'] else None

            # Convert to context
            context = {f'default_{key}': value for key, value in vals.items()}
            context['default_extraction_log_id'] = result['log'].id
            context['default_source'] = 'from_user_upload'  # Page selector is user upload with selected pages

            # 4. Clean up temporary page attachments
            try:
                Attachment.browse(attachment_ids).unlink()
                _logger.info(f"Cleaned up {len(attachment_ids)} temporary attachments")
            except Exception as e:
                _logger.warning(f"Could not cleanup temp attachments: {e}")

            _logger.info(f"Returning form action for selected pages")

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
            _logger.exception("Extract pages failed")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Extraction Failed'),
                    'message': str(e),
                    'type': 'danger',
                }
            }
    @http.route('/document_extractor/substance_dashboard_data', type='json', auth='user', methods=['POST'])
    def get_substance_dashboard_data(self, substance_id=None, organization_id=None, year_from=None, year_to=None):
        """
        Get aggregated data for substance dashboard

        Args:
            substance_id (int): Controlled substance ID
            organization_id (int, optional): Filter by organization
            year_from (int, optional): Start year
            year_to (int, optional): End year

        Returns:
            dict: Dashboard data with KPIs, charts, and details
        """
        try:
            # Validate substance_id
            if not substance_id:
                return {
                    'error': True,
                    'message': 'Substance ID is required'
                }

            # Call substance.aggregate model method
            SubstanceAggregate = request.env['substance.aggregate'].sudo()
            dashboard_data = SubstanceAggregate.get_dashboard_data(
                substance_id=substance_id,
                organization_id=organization_id,
                year_from=year_from,
                year_to=year_to
            )

            return dashboard_data

        except Exception as e:
            _logger.error(f'Error fetching substance dashboard data: {str(e)}', exc_info=True)
            return {
                'error': True,
                'message': str(e)
            }

    @http.route('/document_extractor/company_dashboard_data', type='json', auth='user', methods=['POST'])
    def get_company_dashboard_data(self, organization_id=None, year_from=None, year_to=None):
        """
        Get aggregated data for company dashboard

        Args:
            organization_id (int): Organization/Partner ID (required)
            year_from (int, optional): Start year filter
            year_to (int, optional): End year filter

        Returns:
            dict: Dashboard data with company info, KPIs, charts, and tab data
        """
        try:
            if not organization_id:
                return {'error': True, 'message': 'Organization ID is required'}

            Partner = request.env['res.partner'].sudo()
            Document = request.env['document.extraction'].sudo()

            # Get organization info
            organization = Partner.browse(organization_id)
            if not organization.exists():
                return {'error': True, 'message': 'Organization not found'}

            # Build domain for documents
            domain = [('organization_id', '=', organization_id)]
            if year_from:
                domain.append(('year', '>=', year_from))
            if year_to:
                domain.append(('year', '<=', year_to))

            documents = Document.search(domain)

            # Eager load all related One2many fields to prevent N+1 queries
            # Force ORM to fetch all relations in batch
            documents.mapped('substance_usage_ids.substance_id')
            documents.mapped('substance_usage_ids.substance_name')
            documents.mapped('substance_usage_ids.usage_type')
            documents.mapped('substance_usage_ids.avg_quantity_kg')
            documents.mapped('substance_usage_ids.avg_quantity_co2')
            documents.mapped('substance_usage_ids.year_1_quantity_kg')
            documents.mapped('substance_usage_ids.year_2_quantity_kg')
            documents.mapped('substance_usage_ids.year_3_quantity_kg')
            documents.mapped('substance_usage_ids.year_1_quantity_co2')
            documents.mapped('substance_usage_ids.year_2_quantity_co2')
            documents.mapped('substance_usage_ids.year_3_quantity_co2')
            documents.mapped('quota_usage_ids.substance_name')
            documents.mapped('quota_usage_ids.total_quota_kg')
            documents.mapped('equipment_product_ids.product_type')
            documents.mapped('equipment_product_ids.equipment_type_id')
            documents.mapped('equipment_ownership_ids.equipment_type_id')
            documents.mapped('collection_recycling_ids.activity_type')
            documents.mapped('collection_recycling_ids.quantity_kg')
            documents.mapped('collection_recycling_report_ids.collection_quantity_kg')
            documents.mapped('equipment_product_report_ids')
            documents.mapped('equipment_ownership_report_ids')

            # Aggregate KPIs
            all_substance_usage = documents.mapped('substance_usage_ids').filtered(lambda r: not r.is_title)
            all_quota_usage = documents.mapped('quota_usage_ids')

            total_substances = len(set(
                list(all_substance_usage.mapped('substance_name')) +
                list(all_quota_usage.mapped('substance_name'))
            ))

            # Calculate total kg and CO2e from substance usage
            # FIX: Use correct average calculation (divide by count of non-null years)
            total_kg = 0
            total_co2e = 0
            for usage in all_substance_usage:
                kg, co2 = self._calculate_avg_quantity(usage)
                total_kg += kg
                total_co2e += co2

            # Recovery rate calculation
            # Form 01: collection.recycling with activity_type='collection'
            total_collected_form01 = 0
            for doc in documents.filtered(lambda d: d.document_type == '01'):
                collection_recs = doc.collection_recycling_ids.filtered(lambda r: r.activity_type == 'collection')
                total_collected_form01 += sum(collection_recs.mapped('quantity_kg'))

            # Form 02: collection.recycling.report (field: collection_quantity_kg)
            total_collected_form02 = sum(
                documents.filtered(lambda d: d.document_type == '02')
                .mapped('collection_recycling_report_ids.collection_quantity_kg')
            )
            total_collected = total_collected_form01 + total_collected_form02
            recovery_rate = (total_collected / total_kg * 100) if total_kg > 0 else 0

            # Trend data by year and substance
            trend_data = {}
            for doc in documents:
                year = doc.year
                if year not in trend_data:
                    trend_data[year] = {}

                # Aggregate by substance
                for usage in doc.substance_usage_ids.filtered(lambda r: not r.is_title):
                    substance = usage.substance_name
                    if substance not in trend_data[year]:
                        trend_data[year][substance] = 0

                    # FIX: Use correct average calculation
                    kg, _ = self._calculate_avg_quantity(usage)
                    trend_data[year][substance] += kg

            # Quota allocated vs used
            quota_data = []
            for doc in documents.filtered(lambda d: d.document_type == '02'):
                for quota in doc.quota_usage_ids.filtered(lambda q: not q.is_title):
                    quota_data.append({
                        'year': doc.year,
                        'quota_allocated': quota.allocated_quota_kg or 0,
                        'quota_used': quota.total_quota_kg or 0,
                        'substance_name': quota.substance_name
                    })

            # Get unique activity fields
            all_activity_fields = set()
            for doc in documents:
                all_activity_fields.update(doc.activity_field_ids.mapped('name'))

            return {
                'error': False,
                'company_info': {
                    'name': organization.name,
                    'business_license_number': organization.business_license_number or '',
                    'street': organization.street or '',
                    'city': organization.city or '',
                    'country': organization.country_id.name if organization.country_id else '',
                    'activity_fields': ', '.join(list(all_activity_fields)) if all_activity_fields else 'N/A',
                },
                'kpis': {
                    'total_substances': total_substances or 0,
                    'total_kg': total_kg or 0,
                    'total_co2e': total_co2e or 0,
                    'recovery_rate': recovery_rate or 0,
                },
                'charts': {
                    'trend_by_year': trend_data or {},
                    'quota_data': quota_data or [],
                },
                'tabs': {
                    'table_1_1': self._get_table_1_1_data(documents),
                    'table_1_2': self._get_table_1_2_data(documents),
                    'table_1_3': self._get_table_1_3_data(documents),
                    'table_2_1': self._get_table_2_1_data(documents),
                    'table_2_4': self._get_table_2_4_data(documents),
                    'ocr_history': self._get_ocr_history_data(documents),
                }
            }

        except Exception as e:
            _logger.error(f'Error fetching company dashboard data: {str(e)}', exc_info=True)
            return {'error': True, 'message': str(e)}

    def _get_table_1_1_data(self, documents):
        """Get Table 1.1 data (Production/Import/Export)"""
        records = []
        for doc in documents.filtered(lambda d: d.has_table_1_1):
            for usage in doc.substance_usage_ids.filtered(lambda r: not r.is_title):
                # FIX: Calculate correct average
                kg, co2 = self._calculate_avg_quantity(usage)

                records.append({
                    'year': doc.year,
                    'activity': dict(usage._fields['usage_type'].selection).get(usage.usage_type, ''),
                    'substance_name': usage.substance_name,
                    'quantity_kg': kg,
                    'co2e': co2,
                })
        return records

    def _get_table_1_2_data(self, documents):
        """Get Table 1.2 data (Equipment containing substances)"""
        records = []
        for doc in documents.filtered(lambda d: d.has_table_1_2):
            for equipment in doc.equipment_product_ids:
                records.append({
                    'year': doc.year,
                    'equipment_type': equipment.equipment_type,
                    'substance_name': equipment.substance_name,
                    'quantity': equipment.quantity or 0,
                    'capacity': equipment.capacity or 0,
                })
        return records

    def _get_table_1_3_data(self, documents):
        """Get Table 1.3 data (Equipment ownership)"""
        records = []
        for doc in documents.filtered(lambda d: d.has_table_1_3):
            for equipment in doc.equipment_ownership_ids:
                records.append({
                    'year': doc.year,
                    'equipment_type': equipment.equipment_type,
                    'year_start': equipment.start_year or '',
                    'capacity': equipment.capacity or '',
                    'quantity': equipment.equipment_quantity or 0,
                    'substance_name': equipment.substance_name,
                    'refill_amount': equipment.substance_quantity_per_refill or 0,
                    'refill_frequency': equipment.refill_frequency or 0,
                })
        return records

    def _get_table_2_1_data(self, documents):
        """Get Table 2.1 data (Quota usage)"""
        records = []
        for doc in documents.filtered(lambda d: d.document_type == '02' and d.has_table_2_1):
            for quota in doc.quota_usage_ids.filtered(lambda q: not q.is_title):
                records.append({
                    'year': doc.year,
                    'substance_name': quota.substance_name,
                    'quota_allocated_kg': quota.allocated_quota_kg or 0,
                    'quota_used_kg': quota.total_quota_kg or 0,
                    'hs_code': quota.hs_code or '',
                })
        return records

    def _get_table_2_4_data(self, documents):
        """Get Table 2.4 data (Collection & Recycling)"""
        records = []
        # Form 01 - collection.recycling uses activity_type field
        for doc in documents.filtered(lambda d: d.document_type == '01' and d.has_table_1_4):
            # Group by substance
            substance_data = {}
            for record in doc.collection_recycling_ids:
                substance = record.substance_name
                if substance not in substance_data:
                    substance_data[substance] = {
                        'year': doc.year,
                        'substance_name': substance,
                        'collected': 0,
                        'reused': 0,
                        'recycled': 0,
                        'destroyed': 0,
                    }
                # Add based on activity_type
                if record.activity_type == 'collection':
                    substance_data[substance]['collected'] += record.quantity_kg or 0
                elif record.activity_type == 'reuse':
                    substance_data[substance]['reused'] += record.quantity_kg or 0
                elif record.activity_type == 'recycle':
                    substance_data[substance]['recycled'] += record.quantity_kg or 0
                elif record.activity_type == 'disposal':
                    substance_data[substance]['destroyed'] += record.quantity_kg or 0
            records.extend(substance_data.values())

        # Form 02 - collection.recycling.report has separate fields
        for doc in documents.filtered(lambda d: d.document_type == '02' and d.has_table_2_4):
            for report in doc.collection_recycling_report_ids:
                records.append({
                    'year': doc.year,
                    'substance_name': report.substance_name,
                    'collected': report.collection_quantity_kg or 0,
                    'reused': report.reuse_quantity_kg or 0,
                    'recycled': report.recycle_quantity_kg or 0,
                    'destroyed': report.disposal_quantity_kg or 0,
                })
        return records

    def _get_ocr_history_data(self, documents):
        """Get OCR extraction history"""
        records = []
        for doc in documents:
            records.append({
                'year': doc.year,
                'document_type': 'Mẫu 01' if doc.document_type == '01' else 'Mẫu 02',
                'pdf_filename': doc.pdf_filename,
                'create_date': doc.create_date.strftime('%Y-%m-%d %H:%M') if doc.create_date else '',
                'create_uid': doc.create_uid.name if doc.create_uid else '',
            })
        return records

    @http.route('/document_extractor/equipment_dashboard_data', type='json', auth='user', methods=['POST'])
    def get_equipment_dashboard_data(self, equipment_type_id=None, year_from=None, year_to=None):
        """
        Get aggregated data for equipment type dashboard

        Args:
            equipment_type_id (int): Equipment type ID (required)
            year_from (int, optional): Start year filter
            year_to (int, optional): End year filter

        Returns:
            dict: Dashboard data with equipment info, KPIs, and charts
        """
        try:
            if not equipment_type_id:
                return {'error': True, 'message': 'Equipment type ID is required'}

            EquipmentType = request.env['equipment.type'].sudo()
            EquipmentProduct = request.env['equipment.product'].sudo()
            EquipmentOwnership = request.env['equipment.ownership'].sudo()

            # Get equipment type info
            equipment_type = EquipmentType.browse(equipment_type_id)
            if not equipment_type.exists():
                return {'error': True, 'message': 'Equipment type not found'}

            # Build domain - use equipment_type_id (Many2one to equipment.type)
            domain = [('equipment_type_id', '=', equipment_type_id)]
            if year_from:
                domain.append(('document_id.year', '>=', year_from))
            if year_to:
                domain.append(('document_id.year', '<=', year_to))

            # Get equipment records from both models
            equipment_products = EquipmentProduct.search(domain)
            equipment_ownerships = EquipmentOwnership.search(domain)

            # Eager load relations to prevent N+1 queries
            equipment_products.mapped('document_id.year')
            equipment_products.mapped('document_id.organization_id')
            equipment_products.mapped('substance_id.name')
            equipment_products.mapped('substance_id.gwp')
            equipment_ownerships.mapped('document_id.year')
            equipment_ownerships.mapped('document_id.organization_id')
            equipment_ownerships.mapped('substance_name')

            # Aggregate KPIs
            total_count = len(equipment_products) + len(equipment_ownerships)

            # equipment.product: substance_quantity_per_unit * quantity
            # equipment.ownership: substance_quantity_per_refill * equipment_quantity * refill_frequency
            total_kg = 0
            for eq in equipment_products:
                total_kg += (eq.substance_quantity_per_unit or 0) * (eq.quantity or 0)
            for eq in equipment_ownerships:
                total_kg += (eq.substance_quantity_per_refill or 0) * (eq.equipment_quantity or 0) * (eq.refill_frequency or 1)

            # Capacity is Char field, try to parse or skip
            total_capacity = 0  # Skip for now as it's Char type
            avg_refill_freq = sum(equipment_ownerships.mapped('refill_frequency')) / len(equipment_ownerships) if equipment_ownerships else 0

            # Pre-fetch all substances to avoid N+1 queries
            all_substance_names = set()
            all_substance_names.update(equipment_products.mapped('substance_name'))
            all_substance_names.update(equipment_ownerships.mapped('substance_name'))
            # Remove None/empty strings
            all_substance_names = {name for name in all_substance_names if name}

            substances = request.env['controlled.substance'].sudo().search([
                ('name', 'in', list(all_substance_names))
            ])
            # Build lookup dictionary
            gwp_by_name = {s.name: s.gwp for s in substances}

            # GWP calculation
            total_co2e = 0
            for eq in equipment_products:
                gwp = gwp_by_name.get(eq.substance_name, 0)
                kg = (eq.substance_quantity_per_unit or 0) * (eq.quantity or 0)
                total_co2e += kg * gwp / 1000  # Convert to tons
            for eq in equipment_ownerships:
                gwp = gwp_by_name.get(eq.substance_name, 0)
                kg = (eq.substance_quantity_per_refill or 0) * (eq.equipment_quantity or 0) * (eq.refill_frequency or 1)
                total_co2e += kg * gwp / 1000  # Convert to tons

            # Charts data
            # Trend by year
            trend_by_year = {}
            for eq in equipment_products:
                year = eq.document_id.year
                if year not in trend_by_year:
                    trend_by_year[year] = 0
                trend_by_year[year] += 1
            for eq in equipment_ownerships:
                year = eq.document_id.year
                if year not in trend_by_year:
                    trend_by_year[year] = 0
                trend_by_year[year] += 1

            # By substance
            by_substance = {}
            for eq in equipment_products:
                substance = eq.substance_name
                if substance not in by_substance:
                    by_substance[substance] = 0
                kg = (eq.substance_quantity_per_unit or 0) * (eq.quantity or 0)
                by_substance[substance] += kg
            for eq in equipment_ownerships:
                substance = eq.substance_name
                if substance not in by_substance:
                    by_substance[substance] = 0
                kg = (eq.substance_quantity_per_refill or 0) * (eq.equipment_quantity or 0)
                by_substance[substance] += kg

            # By company
            by_company = {}
            for eq in equipment_products:
                org = eq.document_id.organization_id.name
                if org not in by_company:
                    by_company[org] = {'capacity': 0, 'count': 0}
                by_company[org]['count'] += 1
            for eq in equipment_ownerships:
                org = eq.document_id.organization_id.name
                if org not in by_company:
                    by_company[org] = {'capacity': 0, 'count': 0}
                by_company[org]['count'] += 1

            # Equipment details
            details = []
            for eq in equipment_ownerships:
                details.append({
                    'organization_name': eq.document_id.organization_id.name,
                    'year_start': eq.start_year or '',
                    'capacity': eq.capacity or '',
                    'quantity': eq.equipment_quantity or 0,
                    'substance_name': eq.substance_name,
                    'refill_amount': eq.substance_quantity_per_refill or 0,
                    'refill_frequency': eq.refill_frequency or 0,
                })

            # Get unique companies and substances
            unique_companies = set()
            unique_substances = set()
            for eq in equipment_products:
                if eq.document_id.organization_id:
                    unique_companies.add(eq.document_id.organization_id.id)
                if eq.substance_name:
                    unique_substances.add(eq.substance_name)
            for eq in equipment_ownerships:
                if eq.document_id.organization_id:
                    unique_companies.add(eq.document_id.organization_id.id)
                if eq.substance_name:
                    unique_substances.add(eq.substance_name)

            return {
                'error': False,
                'equipment_info': {
                    'name': equipment_type.name,
                    'description': equipment_type.description or '',
                    'capacity_range': f"{equipment_type.min_capacity or 0} - {equipment_type.max_capacity or 0} kW",
                    'total_companies': len(unique_companies),
                    'common_substances': ', '.join(list(unique_substances)[:5]) if unique_substances else 'N/A',
                    'total_capacity': total_capacity,
                },
                'kpis': {
                    'total_count': total_count or 0,
                    'total_kg': total_kg or 0,
                    'total_co2e': total_co2e or 0,
                    'avg_refill_frequency': round(avg_refill_freq, 2) if avg_refill_freq else 0,
                },
                'charts': {
                    'trend_by_year': [{'year': k, 'count': v} for k, v in sorted(trend_by_year.items())],
                    'by_substance': [{'substance': k, 'total_kg': v} for k, v in by_substance.items()],
                    'by_company': [{'company': k, 'capacity': v['capacity'], 'count': v['count']} for k, v in by_company.items()],
                },
                'details': details[:100],  # Limit to 100 records
            }

        except Exception as e:
            _logger.error(f'Error fetching equipment dashboard data: {str(e)}', exc_info=True)
            return {'error': True, 'message': str(e)}

    @http.route('/document_extractor/hfc_dashboard_data', type='json', auth='user', methods=['POST'])
    def get_hfc_dashboard_data(self, filters=None):
        """
        Get aggregated data for HFC dashboard (all substances overview)

        Args:
            filters (dict): Filter criteria with keys:
                - organization_search (str): Search by organization name
                - organization_code (str): Search by business license number
                - province (str): Filter by province/state
                - substance_name (str): Filter by substance name
                - hs_code (str): Filter by HS code
                - substance_group_id (int): Filter by substance group ID
                - activity_field_ids (list): Filter by activity field IDs
                - year_from (int): Start year
                - year_to (int): End year
                - quantity_min (float): Minimum quantity
                - quantity_max (float): Maximum quantity
                - status (list): Document states ['draft', 'validated', 'completed']

        Returns:
            dict: Dashboard data with KPIs, charts, and tables
        """
        try:
            filters = filters or {}
            _logger.info(f"HFC Dashboard request with filters: {filters}")

            # ===== PHASE 1: Pre-filter documents by state & activity_fields =====
            Document = request.env['document.extraction'].sudo()
            doc_domain = []

            # Filter by status
            if filters.get('status'):
                doc_domain.append(('state', 'in', filters['status']))

            # Filter by activity fields (already IDs from frontend)
            if filters.get('activity_field_ids'):
                activity_field_ids = filters['activity_field_ids']
                if activity_field_ids:
                    doc_domain.append(('activity_field_ids', 'in', activity_field_ids))

            filtered_docs = Document.search(doc_domain)
            filtered_org_ids = filtered_docs.mapped('organization_id').ids if filtered_docs else []

            _logger.info(f"Phase 1: Filtered {len(filtered_docs)} documents, {len(filtered_org_ids)} organizations")

            # ===== PHASE 2: Filter organizations by province, license, name =====
            Partner = request.env['res.partner'].sudo()
            org_domain = [('id', 'in', filtered_org_ids)] if filtered_org_ids else []

            if filters.get('organization_search'):
                org_domain.append(('name', 'ilike', filters['organization_search']))

            if filters.get('organization_code'):
                org_domain.append(('business_license_number', 'ilike', filters['organization_code']))

            if filters.get('province'):
                State = request.env['res.country.state'].sudo()
                state_ids = State.search([('name', 'ilike', filters['province'])]).ids
                if state_ids:
                    org_domain.append(('state_id', 'in', state_ids))

            if org_domain:
                final_org_ids = Partner.search(org_domain).ids
            else:
                # No org filters applied, use all
                final_org_ids = None

            _logger.info(f"Phase 2: Final organization count: {len(final_org_ids) if final_org_ids else 'all'}")

            # ===== PHASE 3: Filter substances by name, group, HS code =====
            Substance = request.env['controlled.substance'].sudo()
            substance_domain = []

            if filters.get('substance_name'):
                substance_domain.append(('name', 'ilike', filters['substance_name']))

            if filters.get('substance_group_id'):
                substance_domain.append(('substance_group_id', '=', filters['substance_group_id']))

            if filters.get('hs_code'):
                substance_domain.append(('hs_code', 'ilike', filters['hs_code']))

            if substance_domain:
                substance_ids = Substance.search(substance_domain).ids
            else:
                substance_ids = None

            _logger.info(f"Phase 3: Substance filter: {len(substance_ids) if substance_ids else 'all'}")

            # ===== PHASE 4: Query substance.aggregate =====
            SubstanceAggregate = request.env['substance.aggregate'].sudo()
            agg_domain = []

            if final_org_ids is not None:
                agg_domain.append(('organization_id', 'in', final_org_ids))

            if substance_ids is not None:
                agg_domain.append(('substance_id', 'in', substance_ids))

            if filters.get('year_from'):
                agg_domain.append(('year', '>=', filters['year_from']))

            if filters.get('year_to'):
                agg_domain.append(('year', '<=', filters['year_to']))

            aggregates = SubstanceAggregate.search(agg_domain)

            _logger.info(f"Phase 4: Found {len(aggregates)} aggregate records")

            # ===== PHASE 5: Apply quantity filters =====
            if filters.get('quantity_min') is not None:
                aggregates = aggregates.filtered(lambda r: r.total_usage_kg >= filters['quantity_min'])

            if filters.get('quantity_max') is not None:
                aggregates = aggregates.filtered(lambda r: r.total_usage_kg <= filters['quantity_max'])

            _logger.info(f"Phase 5: After quantity filters: {len(aggregates)} records")

            # ===== PHASE 6: Calculate KPIs =====
            total_kg = sum(aggregates.mapped('total_usage_kg'))
            total_co2e = sum(aggregates.mapped('total_co2e'))
            org_count = len(set(aggregates.mapped('organization_id').ids))

            # Document count by unique (year, org, doc_type)
            unique_docs = set()
            for agg in aggregates:
                if agg.organization_id:
                    doc_key = (agg.year, agg.organization_id.id, agg.document_type)
                    unique_docs.add(doc_key)
            doc_count = len(unique_docs)

            # Verified percentage (from filtered docs)
            if filtered_docs:
                verified_docs = filtered_docs.filtered(lambda d: d.state == 'validated')
                verified_pct = (len(verified_docs) / len(filtered_docs) * 100)
            else:
                verified_pct = 0

            _logger.info(f"Phase 6: KPIs - Orgs: {org_count}, Docs: {doc_count}, kg: {total_kg:.2f}, CO2e: {total_co2e:.2f}")

            # ===== PHASE 7: Prepare chart data =====

            # Chart 1: Trend by year & substance (for bar chart)
            trend_data = {}
            for agg in aggregates:
                key = (agg.year, agg.substance_id.id, agg.substance_id.name)
                if key not in trend_data:
                    trend_data[key] = {
                        'year': agg.year,
                        'substance_id': agg.substance_id.id,
                        'substance_name': agg.substance_id.name,
                        'total_kg': 0,
                        'co2e': 0
                    }
                trend_data[key]['total_kg'] += agg.total_usage_kg
                trend_data[key]['co2e'] += agg.total_co2e

            trend_list = sorted(trend_data.values(), key=lambda x: (x['year'], x['substance_name']))

            # Chart 2: By activity type (for pie chart)
            activity_labels = {
                'production': 'Sản xuất',
                'import': 'Nhập khẩu',
                'export': 'Xuất khẩu',
                'equipment_manufacturing': 'SX/NK Thiết bị',
                'equipment_operation': 'Vận hành thiết bị',
                'collection': 'Thu gom',
                'reuse': 'Tái sử dụng',
                'recycle': 'Tái chế',
                'disposal': 'Tiêu hủy'
            }

            activity_data = {}
            for agg in aggregates:
                if agg.usage_type:
                    usage = agg.usage_type
                    if usage not in activity_data:
                        activity_data[usage] = {
                            'activity_type': usage,
                            'activity_label': activity_labels.get(usage, usage.title()),
                            'total_kg': 0,
                            'co2e': 0
                        }
                    activity_data[usage]['total_kg'] += agg.total_usage_kg
                    activity_data[usage]['co2e'] += agg.total_co2e

            activity_list = sorted(activity_data.values(), key=lambda x: x['total_kg'], reverse=True)

            # Table 1: Top 10 records by (org, year, substance)
            top_records = {}
            for agg in aggregates:
                if not agg.organization_id:
                    continue

                key = (agg.organization_id.id, agg.year, agg.substance_id.id)
                if key not in top_records:
                    # Get activity tags from document
                    doc = Document.search([
                        ('organization_id', '=', agg.organization_id.id),
                        ('year', '=', agg.year),
                        ('document_type', '=', agg.document_type)
                    ], limit=1)

                    activity_tags = []
                    if doc and doc.activity_field_ids:
                        activity_tags = doc.activity_field_ids.mapped('name')

                    top_records[key] = {
                        'organization_id': agg.organization_id.id,
                        'organization_name': agg.organization_id.name,
                        'substance_id': agg.substance_id.id,
                        'substance_name': agg.substance_id.name,
                        'year': agg.year,
                        'total_kg': 0,
                        'co2e': 0,
                        'activity_tags': activity_tags,
                        'status': doc.state if doc else 'draft'
                    }
                top_records[key]['total_kg'] += agg.total_usage_kg
                top_records[key]['co2e'] += agg.total_co2e

            top_10 = sorted(top_records.values(), key=lambda x: x['total_kg'], reverse=True)[:10]

            # Table 2: Pivot data (DN × Chất, columns: Years)
            pivot_data = {}
            for agg in aggregates:
                if not agg.organization_id:
                    continue

                key = (agg.organization_id.id, agg.substance_id.id)
                if key not in pivot_data:
                    pivot_data[key] = {
                        'organization_id': agg.organization_id.id,
                        'organization_name': agg.organization_id.name,
                        'substance_id': agg.substance_id.id,
                        'substance_name': agg.substance_id.name,
                        'year_2021_kg': 0,
                        'year_2022_kg': 0,
                        'year_2023_kg': 0,
                        'year_2024_kg': 0,
                        'total_co2e': 0
                    }

                year_key = f'year_{agg.year}_kg'
                if year_key in pivot_data[key]:
                    pivot_data[key][year_key] += agg.total_usage_kg
                pivot_data[key]['total_co2e'] += agg.total_co2e

            pivot_list = sorted(pivot_data.values(),
                               key=lambda x: (x['organization_name'], x['substance_name']))[:50]

            _logger.info(f"Phase 7: Charts prepared - Trend: {len(trend_list)}, Activity: {len(activity_list)}, Top10: {len(top_10)}, Pivot: {len(pivot_list)}")

            # ===== PHASE 8: Return response =====
            return {
                'error': False,
                'kpis': {
                    'total_organizations': org_count,
                    'total_kg': total_kg,
                    'total_co2e': total_co2e,
                    'verified_percentage': verified_pct
                },
                'charts': {
                    'trend_by_year_substance': trend_list,
                    'by_activity_type': activity_list,
                    'top_10_records': top_10,
                    'pivot_data': pivot_list
                },
                'filter_metadata': {
                    'available_years': sorted(set(aggregates.mapped('year')), reverse=True) if aggregates else []
                }
            }

        except Exception as e:
            _logger.error(f'Error fetching HFC dashboard data: {str(e)}', exc_info=True)
            return {
                'error': True,
                'message': str(e)
            }

    @http.route('/document_extractor/recovery_dashboard_data', type='json', auth='user', methods=['POST'])
    def get_recovery_dashboard_data(self, substance_id=None, organization_id=None, year_from=None, year_to=None):
        """
        Get aggregated data for recovery dashboard

        Args:
            substance_id (int, optional): Filter by substance
            organization_id (int, optional): Filter by organization
            year_from (int, optional): Start year filter
            year_to (int, optional): End year filter

        Returns:
            dict: Dashboard data with recovery KPIs and charts
        """
        try:
            Document = request.env['document.extraction'].sudo()

            # Build domain
            domain = []
            if substance_id:
                substance_name = request.env['controlled.substance'].sudo().browse(substance_id).name
                domain.append('|')
                domain.append(('collection_recycling_ids.substance_name', '=', substance_name))
                domain.append(('collection_recycling_report_ids.substance_name', '=', substance_name))
            if organization_id:
                domain.append(('organization_id', '=', organization_id))
            if year_from:
                domain.append(('year', '>=', year_from))
            if year_to:
                domain.append(('year', '<=', year_to))

            documents = Document.search(domain)

            # Eager load relations to prevent N+1 queries
            documents.mapped('collection_recycling_ids.activity_type')
            documents.mapped('collection_recycling_ids.quantity_kg')
            documents.mapped('collection_recycling_ids.substance_name')
            documents.mapped('collection_recycling_report_ids.collection_quantity_kg')
            documents.mapped('collection_recycling_report_ids.reuse_quantity_kg')
            documents.mapped('collection_recycling_report_ids.recycle_quantity_kg')
            documents.mapped('collection_recycling_report_ids.disposal_quantity_kg')
            documents.mapped('organization_id.name')

            # Aggregate KPIs
            # Form 01: collection.recycling with activity_type
            total_collected = 0
            total_reused = 0
            total_recycled = 0
            total_destroyed = 0

            for doc in documents.filtered(lambda d: d.document_type == '01'):
                for record in doc.collection_recycling_ids:
                    if record.activity_type == 'collection':
                        total_collected += record.quantity_kg or 0
                    elif record.activity_type == 'reuse':
                        total_reused += record.quantity_kg or 0
                    elif record.activity_type == 'recycle':
                        total_recycled += record.quantity_kg or 0
                    elif record.activity_type == 'disposal':
                        total_destroyed += record.quantity_kg or 0

            # Form 02: collection.recycling.report has separate fields
            for doc in documents.filtered(lambda d: d.document_type == '02'):
                for report in doc.collection_recycling_report_ids:
                    total_collected += report.collection_quantity_kg or 0
                    total_reused += report.reuse_quantity_kg or 0
                    total_recycled += report.recycle_quantity_kg or 0
                    total_destroyed += report.disposal_quantity_kg or 0

            # Charts
            # Trend by year
            trend_by_year = {}
            for doc in documents:
                year = doc.year
                if year not in trend_by_year:
                    trend_by_year[year] = 0

                # Form 01
                if doc.document_type == '01':
                    collected = sum(doc.collection_recycling_ids.filtered(lambda r: r.activity_type == 'collection').mapped('quantity_kg'))
                    trend_by_year[year] += collected
                # Form 02
                else:
                    collected = sum(doc.collection_recycling_report_ids.mapped('collection_quantity_kg'))
                    trend_by_year[year] += collected

            # By substance (reuse)
            reuse_by_substance = {}
            for doc in documents:
                # Form 01
                if doc.document_type == '01':
                    for record in doc.collection_recycling_ids.filtered(lambda r: r.activity_type == 'reuse'):
                        substance = record.substance_name
                        if substance not in reuse_by_substance:
                            reuse_by_substance[substance] = 0
                        reuse_by_substance[substance] += record.quantity_kg or 0
                # Form 02
                else:
                    for report in doc.collection_recycling_report_ids:
                        substance = report.substance_name
                        if substance not in reuse_by_substance:
                            reuse_by_substance[substance] = 0
                        reuse_by_substance[substance] += report.reuse_quantity_kg or 0

            # By technology (recycle)
            recycle_by_technology = {}
            for doc in documents:
                # Form 01 - no technology field in collection.recycling
                # Form 02 - collection.recycling.report has recycle_technology
                if doc.document_type == '02':
                    for report in doc.collection_recycling_report_ids:
                        tech = report.recycle_technology or 'Unknown'
                        if tech not in recycle_by_technology:
                            recycle_by_technology[tech] = 0
                        recycle_by_technology[tech] += report.recycle_quantity_kg or 0

            # Details
            details = []
            for doc in documents:
                # Form 01 - group by substance
                if doc.document_type == '01':
                    substance_details = {}
                    for record in doc.collection_recycling_ids:
                        substance = record.substance_name
                        if substance not in substance_details:
                            substance_details[substance] = {
                                'organization_name': doc.organization_id.name,
                                'substance_name': substance,
                                'collected': 0,
                                'reused': 0,
                                'recycled': 0,
                                'destroyed': 0,
                                'technology': '',
                                'location': '',
                            }
                        if record.activity_type == 'collection':
                            substance_details[substance]['collected'] += record.quantity_kg or 0
                        elif record.activity_type == 'reuse':
                            substance_details[substance]['reused'] += record.quantity_kg or 0
                        elif record.activity_type == 'recycle':
                            substance_details[substance]['recycled'] += record.quantity_kg or 0
                        elif record.activity_type == 'disposal':
                            substance_details[substance]['destroyed'] += record.quantity_kg or 0
                    details.extend(substance_details.values())

                # Form 02
                else:
                    for report in doc.collection_recycling_report_ids:
                        details.append({
                            'organization_name': doc.organization_id.name,
                            'substance_name': report.substance_name,
                            'collected': report.collection_quantity_kg or 0,
                            'reused': report.reuse_quantity_kg or 0,
                            'recycled': report.recycle_quantity_kg or 0,
                            'destroyed': report.disposal_quantity_kg or 0,
                            'technology': report.recycle_technology or '',
                            'location': report.collection_location or '',
                        })

            # Get main substances from both Form 01 and Form 02
            all_substances = set()
            for doc in documents:
                if doc.document_type == '01':
                    all_substances.update(list(doc.collection_recycling_ids.mapped('substance_name')))
                else:
                    all_substances.update(list(doc.collection_recycling_report_ids.mapped('substance_name')))

            # Remove empty strings and take first 5
            main_substances_list = [s for s in all_substances if s][:5]
            main_substances = ', '.join(main_substances_list) if main_substances_list else 'N/A'

            years = documents.mapped('year')
            year_range = f"{min(years)} - {max(years)}" if years else 'N/A'

            return {
                'error': False,
                'info': {
                    'total_companies': len(set(documents.mapped('organization_id'))),
                    'main_substances': main_substances,
                    'year_range': year_range,
                },
                'kpis': {
                    'total_collected': total_collected or 0,
                    'total_reused': total_reused or 0,
                    'total_recycled': total_recycled or 0,
                    'total_destroyed': total_destroyed or 0,
                },
                'charts': {
                    'trend_by_year': [{'year': k, 'collected': v} for k, v in sorted(trend_by_year.items())],
                    'reuse_by_substance': [{'substance': k, 'reused': v} for k, v in reuse_by_substance.items()],
                    'recycle_by_technology': [{'technology': k, 'recycled': v} for k, v in recycle_by_technology.items()],
                },
                'details': details[:100],
            }

        except Exception as e:
            _logger.error(f'Error fetching recovery dashboard data: {str(e)}', exc_info=True)
            return {'error': True, 'message': str(e)}

    @http.route('/document_extractor/export_hfc_report', type='http', auth='user', methods=['POST'], csrf=False)
    def export_hfc_report(self, filters='{}', **kwargs):
        """
        Export HFC dashboard data to Excel using template

        Args:
            filters (str): JSON string of filter criteria (same as get_hfc_dashboard_data)

        Returns:
            HTTP response with Excel file attachment
        """
        import json
        import openpyxl
        from io import BytesIO
        from datetime import datetime
        import os

        try:
            # Parse filters
            filters_dict = json.loads(filters) if isinstance(filters, str) else filters
            _logger.info(f"Export HFC report with filters: {filters_dict}")

            # Get template path
            module_path = os.path.dirname(os.path.dirname(__file__))
            template_path = os.path.join(module_path, 'static', 'templates', 'HFC_REPORT.xlsx')

            if not os.path.exists(template_path):
                _logger.error(f"Template not found at: {template_path}")
                return request.make_response(
                    json.dumps({'error': True, 'message': 'Template file not found'}),
                    headers=[('Content-Type', 'application/json')]
                )

            # Load template
            wb = openpyxl.load_workbook(template_path)

            # Query data using same logic as dashboard
            data = self._get_export_data(filters_dict)

            # Fill each sheet
            self._fill_sheet1_company(wb, data['companies'])
            self._fill_sheet2_equipment_ownership(wb, data['equipment_ownership'])
            self._fill_sheet3_equipment_production(wb, data['equipment_production'])
            self._fill_sheet4_eol_substances(wb, data['eol_substances'])
            self._fill_sheet5_bulk_substances(wb, data['bulk_substances'])

            # Save to BytesIO
            output = BytesIO()
            wb.save(output)
            output.seek(0)

            # Generate filename with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'HFC_Report_{timestamp}.xlsx'

            # Return as HTTP response
            return request.make_response(
                output.read(),
                headers=[
                    ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                    ('Content-Disposition', f'attachment; filename="{filename}"'),
                ]
            )

        except Exception as e:
            _logger.error(f'Error exporting HFC report: {str(e)}', exc_info=True)
            return request.make_response(
                json.dumps({'error': True, 'message': str(e)}),
                headers=[('Content-Type', 'application/json')]
            )

    def _get_export_data(self, filters):
        """
        Query all data needed for export based on filters
        Similar to get_hfc_dashboard_data but returns raw records
        """
        # Phase 1: Filter documents
        Document = request.env['document.extraction'].sudo()
        doc_domain = []

        if filters.get('status'):
            doc_domain.append(('state', 'in', filters['status']))

        if filters.get('activity_field_ids'):
            activity_field_ids = filters['activity_field_ids']
            if activity_field_ids:
                doc_domain.append(('activity_field_ids', 'in', activity_field_ids))

        filtered_docs = Document.search(doc_domain)
        filtered_org_ids = filtered_docs.mapped('organization_id').ids if filtered_docs else []

        # Phase 2: Filter organizations
        Partner = request.env['res.partner'].sudo()
        org_domain = [('id', 'in', filtered_org_ids)] if filtered_org_ids else []

        if filters.get('organization_search'):
            org_domain.append(('name', 'ilike', filters['organization_search']))

        if filters.get('organization_code'):
            org_domain.append(('business_license_number', 'ilike', filters['organization_code']))

        if filters.get('province'):
            State = request.env['res.country.state'].sudo()
            state_ids = State.search([('name', 'ilike', filters['province'])]).ids
            if state_ids:
                org_domain.append(('state_id', 'in', state_ids))

        if org_domain:
            final_orgs = Partner.search(org_domain)
            final_org_ids = final_orgs.ids
        else:
            final_orgs = Partner.browse([])
            final_org_ids = None

        # Phase 3: Filter by substance
        Substance = request.env['controlled.substance'].sudo()
        substance_domain = []

        if filters.get('substance_name'):
            substance_domain.append(('name', 'ilike', filters['substance_name']))

        if filters.get('substance_group_id'):
            substance_domain.append(('substance_group_id', '=', filters['substance_group_id']))

        if filters.get('hs_code'):
            substance_domain.append(('hs_code', 'ilike', filters['hs_code']))

        if substance_domain:
            substance_ids = Substance.search(substance_domain).ids
        else:
            substance_ids = None

        # Phase 4: Get documents in scope
        final_doc_domain = []
        if final_org_ids is not None:
            final_doc_domain.append(('organization_id', 'in', final_org_ids))

        if filters.get('year_from'):
            final_doc_domain.append(('year', '>=', filters['year_from']))

        if filters.get('year_to'):
            final_doc_domain.append(('year', '<=', filters['year_to']))

        documents = Document.search(final_doc_domain, limit=10000)  # Limit to prevent huge exports

        # Phase 5: Extract data for each sheet
        companies_data = []
        equipment_ownership_data = []
        equipment_production_data = []
        eol_substances_data = []
        bulk_substances_data = []

        for doc in documents:
            org = doc.organization_id
            if not org:
                continue

            # Sheet 1: Company info (one row per company)
            if org.id not in [c['org_id'] for c in companies_data]:
                companies_data.append({
                    'org_id': org.id,
                    'name': org.name or '',
                    'license_number': org.business_license_number or '',
                    'legal_representative': org.legal_representative_name or '',
                    'legal_representative_position': org.legal_representative_position or '',
                    'contact_person': org.contact_person_name or '',
                    'address': doc.contact_address,
                    'phone': org.phone or '',
                    'fax': org.fax or '',
                    'email': org.email or '',
                    'activity_fields': doc.activity_field_ids.mapped('code'),
                })

            # Sheet 2: Equipment ownership (Form 01)
            if doc.document_type == '01':
                for eq in doc.equipment_ownership_ids:
                    # Apply substance filter
                    if substance_ids and eq.substance_id.id not in substance_ids:
                        continue

                    equipment_ownership_data.append({
                        'license_number': org.business_license_number or '',
                        'year': doc.year,
                        'data_source': 'Mẫu 01',
                        'equipment_category': '',  # Field doesn't exist in model
                        'equipment_type': eq.equipment_type_id.name if eq.equipment_type_id else '',
                        'substance_name': eq.substance_id.name if eq.substance_id else '',
                        'capacity': eq.capacity or 0,
                        'year_in_use': eq.start_year or 0,
                        'quantity': eq.equipment_quantity or 0,
                        'refill_frequency': eq.refill_frequency or 0,
                        'refill_quantity_kg': eq.substance_quantity_per_refill or 0,
                        'note': '',  # Field doesn't exist in model
                    })

            # Sheet 2: Equipment ownership report (Form 02)
            if doc.document_type == '02':
                for eq in doc.equipment_ownership_report_ids:
                    if substance_ids and eq.substance_id.id not in substance_ids:
                        continue

                    equipment_ownership_data.append({
                        'license_number': org.business_license_number or '',
                        'year': doc.year,
                        'data_source': 'Mẫu 02',
                        'equipment_category': '',  # Field doesn't exist in model
                        'equipment_type': eq.equipment_type_id.name if eq.equipment_type_id else '',
                        'substance_name': eq.substance_id.name if eq.substance_id else '',
                        'capacity': eq.capacity or 0,
                        'year_in_use': eq.start_year or 0,
                        'quantity': eq.equipment_quantity or 0,
                        'refill_frequency': eq.refill_frequency or 0,
                        'refill_quantity_kg': eq.substance_quantity_per_refill or 0,
                        'note': eq.notes or '',
                    })

            # Sheet 3: Equipment production/import (Form 01)
            if doc.document_type == '01':
                for eq in doc.equipment_product_ids:
                    if substance_ids and eq.substance_id.id not in substance_ids:
                        continue

                    equipment_production_data.append({
                        'license_number': org.business_license_number or '',
                        'year': doc.year,
                        'data_source': 'Mẫu 01',
                        'activity': '',  # Field doesn't exist in equipment.product
                        'product_type': eq.product_type or '',
                        'hs_code': eq.hs_code_id.code if eq.hs_code_id else '',
                        'capacity': eq.capacity or 0,
                        'quantity': eq.quantity or 0,
                        'substance_name': eq.substance_id.name if eq.substance_id else '',
                        'substance_quantity_kg': eq.substance_quantity_per_unit or 0,
                    })

            # Sheet 3: Equipment production report (Form 02)
            if doc.document_type == '02':
                for eq in doc.equipment_product_report_ids:
                    if substance_ids and eq.substance_id.id not in substance_ids:
                        continue

                    equipment_production_data.append({
                        'license_number': org.business_license_number or '',
                        'year': doc.year,
                        'data_source': 'Mẫu 02',
                        'activity': eq.production_type,
                        'product_type': eq.product_type or '',
                        'hs_code': eq.hs_code_id.code if eq.hs_code_id else '',
                        'capacity': eq.capacity or 0,
                        'quantity': eq.quantity or 0,
                        'substance_name': eq.substance_id.name if eq.substance_id else '',
                        'substance_quantity_kg': eq.substance_quantity_per_unit or 0,
                    })

            # Sheet 4: EoL substances (collection/recycling)
            if doc.document_type == '01':
                for rec in doc.collection_recycling_ids:
                    if substance_ids and rec.substance_id.id not in substance_ids:
                        continue

                    eol_substances_data.append({
                        'license_number': org.business_license_number or '',
                        'year': doc.year,
                        'substance_name': rec.substance_id.name if rec.substance_id else rec.substance_name or '',
                        'activity': rec.activity_type,
                        'quantity_kg': rec.quantity_kg or 0,
                        'detail_1': '',  # Field doesn't exist in collection.recycling
                        'detail_2': '',  # Field doesn't exist in collection.recycling
                    })

            if doc.document_type == '02':
                for rep in doc.collection_recycling_report_ids:
                    if substance_ids and rep.substance_id.id not in substance_ids:
                        continue

                    # Create separate rows for each activity type
                    substance_name = rep.substance_id.name if rep.substance_id else rep.substance_name or ''

                    if rep.collection_quantity_kg:
                        eol_substances_data.append({
                            'license_number': org.business_license_number or '',
                            'year': doc.year,
                            'substance_name': substance_name,
                            'activity': 'collection',
                            'quantity_kg': rep.collection_quantity_kg or 0,
                            'detail_1': rep.collection_location or '',
                            'detail_2': '',
                        })

                    if rep.reuse_quantity_kg:
                        eol_substances_data.append({
                            'license_number': org.business_license_number or '',
                            'year': doc.year,
                            'substance_name': substance_name,
                            'activity': 'reuse',
                            'quantity_kg': rep.reuse_quantity_kg or 0,
                            'detail_1': '',
                            'detail_2': '',
                        })

                    if rep.recycle_quantity_kg:
                        eol_substances_data.append({
                            'license_number': org.business_license_number or '',
                            'year': doc.year,
                            'substance_name': substance_name,
                            'activity': 'recycling',
                            'quantity_kg': rep.recycle_quantity_kg or 0,
                            'detail_1': rep.recycle_technology or '',
                            'detail_2': rep.recycle_facility_id.name if rep.recycle_facility_id else '',
                        })

                    if rep.disposal_quantity_kg:
                        eol_substances_data.append({
                            'license_number': org.business_license_number or '',
                            'year': doc.year,
                            'substance_name': substance_name,
                            'activity': 'disposal',
                            'quantity_kg': rep.disposal_quantity_kg or 0,
                            'detail_1': rep.disposal_technology or '',
                            'detail_2': rep.disposal_facility or '',
                        })

            # Sheet 5: Bulk substances (production/import/export)
            if doc.document_type == '01':
                for usage in doc.substance_usage_ids:
                    if substance_ids and usage.substance_id.id not in substance_ids:
                        continue

                    # Determine activity type from usage_type field
                    activity = usage.usage_type

                    bulk_substances_data.append({
                        'license_number': org.business_license_number or '',
                        'data_source': 'Mẫu 01',
                        'activity': activity,
                        'substance_name': usage.substance_id.name if usage.substance_id else usage.substance_name or '',
                        'year': doc.year,
                        'quantity_kg': usage.year_2_quantity_kg or 0,  # Use year 2 as requested
                        'co2e_tons': usage.year_2_quantity_co2 or 0,
                        'hs_code': '',  # substance.usage doesn't have hs_code field
                    })

            if doc.document_type == '02':
                for quota in doc.quota_usage_ids:
                    if substance_ids and quota.substance_id.id not in substance_ids:
                        continue

                    bulk_substances_data.append({
                        'license_number': org.business_license_number or '',
                        'data_source': 'Mẫu 02',
                        'activity': quota.usage_type,
                        'substance_name': quota.substance_id.name if quota.substance_id else quota.substance_name or '',
                        'year': doc.year,
                        'quantity_kg': quota.total_quota_kg or 0,
                        'co2e_tons': quota.total_quota_co2 or 0,  # Now using correct field
                        'hs_code': quota.hs_code or '',
                    })

        return {
            'companies': companies_data,
            'equipment_ownership': equipment_ownership_data,
            'equipment_production': equipment_production_data,
            'eol_substances': eol_substances_data,
            'bulk_substances': bulk_substances_data,
        }

    def _fill_sheet1_company(self, wb, companies_data):
        """Fill Sheet 1: Company/Document info"""
        ws = wb['1_Hoso_DoanhNhiep']

        # Activity field column mapping
        activity_field_cols = {
            'production': 'K',
            'import': 'L',
            'export': 'M',
            'equipment_production': 'N',
            'equipment_import': 'O',
            'ac_ownership': 'P',
            'refrigeration_ownership': 'Q',
            'collection_recycling': 'R',
        }

        row_idx = 2  # Start after header
        for idx, company in enumerate(companies_data, start=1):
            ws[f'A{row_idx}'] = idx
            ws[f'B{row_idx}'] = company['name']
            ws[f'C{row_idx}'] = company['license_number']
            ws[f'D{row_idx}'] = company['legal_representative']
            ws[f'E{row_idx}'] = company['legal_representative_position']
            ws[f'F{row_idx}'] = company['contact_person']
            ws[f'G{row_idx}'] = company['address']
            ws[f'H{row_idx}'] = company['phone']
            ws[f'I{row_idx}'] = company['fax']
            ws[f'J{row_idx}'] = company['email']

            # Activity fields - mark with 'X' if present
            for field_code, col in activity_field_cols.items():
                if field_code in company['activity_fields']:
                    ws[f'{col}{row_idx}'] = 'X'

            row_idx += 1

    def _fill_sheet2_equipment_ownership(self, wb, equipment_ownership_data):
        """Fill Sheet 2: Equipment Ownership"""
        ws = wb['2_DL_ThietBi_SoHuu']

        row_idx = 2  # Start after header
        for eq in equipment_ownership_data:
            ws[f'A{row_idx}'] = eq['license_number']
            ws[f'B{row_idx}'] = eq['year']
            ws[f'C{row_idx}'] = eq['data_source']
            ws[f'D{row_idx}'] = eq['equipment_category']
            ws[f'E{row_idx}'] = eq['equipment_type']
            ws[f'F{row_idx}'] = eq['substance_name']
            ws[f'G{row_idx}'] = eq['capacity']
            ws[f'H{row_idx}'] = eq['year_in_use']
            ws[f'I{row_idx}'] = eq['quantity']
            ws[f'J{row_idx}'] = eq['refill_frequency']
            ws[f'K{row_idx}'] = eq['refill_quantity_kg']
            ws[f'L{row_idx}'] = eq['note']
            row_idx += 1

    def _fill_sheet3_equipment_production(self, wb, equipment_production_data):
        """Fill Sheet 3: Equipment Production/Import"""
        ws = wb['3_DL_ThietBi_SX_NK']

        row_idx = 2  # Start after header
        for eq in equipment_production_data:
            ws[f'A{row_idx}'] = eq['license_number']
            ws[f'B{row_idx}'] = eq['year']
            ws[f'C{row_idx}'] = eq['data_source']
            ws[f'D{row_idx}'] = eq['activity']
            ws[f'E{row_idx}'] = eq['product_type']
            ws[f'F{row_idx}'] = eq['hs_code']
            ws[f'G{row_idx}'] = eq['capacity']
            ws[f'H{row_idx}'] = eq['quantity']
            ws[f'I{row_idx}'] = eq['substance_name']
            ws[f'J{row_idx}'] = eq['substance_quantity_kg']
            row_idx += 1

    def _fill_sheet4_eol_substances(self, wb, eol_substances_data):
        """Fill Sheet 4: EoL Substances (Collection/Recycling)"""
        ws = wb['4_DL_MoiChat_EoL']

        row_idx = 2  # Start after header
        for rec in eol_substances_data:
            ws[f'A{row_idx}'] = rec['license_number']
            ws[f'B{row_idx}'] = rec['year']
            ws[f'C{row_idx}'] = rec['substance_name']
            activity_map = {
                'collection': 'Thu gom',
                'reuse': 'Tái sử dụng',
                'recycling': 'Tái chế',
                'disposal': 'Tiêu hủy'
            }
            ws[f'D{row_idx}'] = activity_map.get(rec['activity'], rec['activity'])
            ws[f'E{row_idx}'] = rec['quantity_kg']
            ws[f'F{row_idx}'] = rec['detail_1']
            ws[f'G{row_idx}'] = rec['detail_2']
            row_idx += 1

    def _fill_sheet5_bulk_substances(self, wb, bulk_substances_data):
        """Fill Sheet 5: Bulk Substances (Production/Import/Export)"""
        ws = wb['5. DL_MoiChat_Bulk']

        row_idx = 2  # Start after header
        for usage in bulk_substances_data:
            ws[f'A{row_idx}'] = usage['license_number']
            ws[f'B{row_idx}'] = usage['data_source']
            activity_map = {
                'production': 'Sản xuất',
                'import': 'Nhập khẩu',
                'export': 'Xuất khẩu',
                'collection': 'Thu gom',
            }
            ws[f'C{row_idx}'] = activity_map.get(usage['activity'], usage['activity'])
            ws[f'D{row_idx}'] = usage['substance_name']
            ws[f'E{row_idx}'] = usage['year']
            ws[f'F{row_idx}'] = usage['quantity_kg']
            ws[f'G{row_idx}'] = usage['co2e_tons']
            ws[f'H{row_idx}'] = usage['hs_code']
            row_idx += 1

    @http.route('/document_extractor/overview_dashboard_data', type='json', auth='user', methods=['POST'])
    def get_overview_dashboard_data(self):
        """
        Get aggregated data for overview dashboard

        Returns:
            dict: Dashboard data with KPIs, charts, and recent activity
        """
        try:
            env = request.env

            # 1. Get data from substance.aggregate (ALREADY EXISTS!)
            SubstanceAggregate = env['substance.aggregate'].sudo()
            aggregate_data = SubstanceAggregate.get_dashboard_data()
            # Returns: {kpis: {...}, charts: {...}, details: {...}}

            # 2. Add document counts
            Document = env['document.extraction'].sudo()
            total_docs = Document.search_count([])
            form01_count = Document.search_count([('document_type', '=', '01')])
            form02_count = Document.search_count([('document_type', '=', '02')])

            # 3. Add status counts (simplified - 3 statuses)
            draft_count = Document.search_count([('state', '=', 'draft')])
            validated_count = Document.search_count([('state', '=', 'validated')])
            completed_count = Document.search_count([('state', '=', 'completed')])

            # 4. Get recent activity from logs
            Log = env['google.drive.extraction.log'].sudo()
            logs = Log.search([], order='create_date desc', limit=5)

            recent_activity = []
            for log in logs:
                # Format relative time
                from odoo.fields import Datetime

                create_date = log.create_date
                if create_date:
                    now = Datetime.now()
                    diff = now - create_date

                    if diff.days > 0:
                        time_str = _("%d days ago") % diff.days
                    elif diff.seconds >= 3600:
                        hours = diff.seconds // 3600
                        time_str = _("%d hours ago") % hours
                    elif diff.seconds >= 60:
                        minutes = diff.seconds // 60
                        time_str = _("%d mins ago") % minutes
                    else:
                        time_str = _("just now")
                else:
                    time_str = _("Unknown")

                # Get document info if extraction record exists
                document_id = False
                display_name = log.file_name

                if log.extraction_record_id:
                    # Has document: use document name
                    document_id = log.extraction_record_id.id
                    display_name = log.extraction_record_id.name or log.file_name

                recent_activity.append({
                    'id': log.id,
                    'log_id': log.id,  # Always available for clicking log record
                    'document_id': document_id,  # Document ID if exists, False otherwise
                    'action': _("Processed %s") % display_name,
                    'user': log.create_uid.name if log.create_uid else _('System'),
                    'time': time_str,
                    'type': 'upload' if log.status == 'success' else 'processing',
                    'display_name': display_name  # For tooltip
                })

            # 5. Calculate Top Substances (optimized SQL query)
            # Use direct SQL query to aggregate and sort in database
            env.cr.execute("""
                SELECT
                    cs.id,
                    cs.name,
                    SUM(COALESCE(sa.total_co2e, 0)) as total_co2e
                FROM substance_aggregate sa
                INNER JOIN controlled_substance cs ON sa.substance_id = cs.id
                WHERE sa.substance_id IS NOT NULL
                GROUP BY cs.id, cs.name
                ORDER BY total_co2e DESC
                LIMIT 5
            """)

            top_substances_raw = env.cr.fetchall()
            top_substances = [
                {
                    'name': row[1],
                    'value': row[2]
                }
                for row in top_substances_raw
            ]

            # 6. Merge data and return
            return {
                'error': False,
                'kpis': {
                    # From substance.aggregate
                    'total_usage_kg': aggregate_data['kpis']['total_usage_kg'],
                    'total_co2e': aggregate_data['kpis']['total_co2e'],
                    'organization_count': aggregate_data['kpis']['organization_count'],
                    'document_count': aggregate_data['kpis']['document_count'],
                    # Additional counts
                    'total_docs': total_docs,
                    'form01_count': form01_count,
                    'form02_count': form02_count,
                    'status_counts': {
                        'draft': draft_count,
                        'validated': validated_count,
                        'completed': completed_count
                    }
                },
                'charts': {
                    'trend_by_year': aggregate_data['charts']['trend_by_year'],
                    'top_substances': top_substances,  # Changed from top_companies
                    'by_activity_type': aggregate_data['charts']['by_activity_type'],
                },
                'recent_activity': recent_activity
            }

        except Exception as e:
            _logger.error(f'Error fetching overview dashboard data: {str(e)}', exc_info=True)
            return {
                'error': True,
                'message': str(e)
            }
