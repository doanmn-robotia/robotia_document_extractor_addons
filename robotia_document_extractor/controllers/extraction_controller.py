# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request
import base64
import logging

_logger = logging.getLogger(__name__)


class ExtractionController(http.Controller):
    """
    JSON-RPC Controller for document extraction

    IMPORTANT: This controller does NOT create records immediately.
    It extracts data and returns an action to open form in CREATE mode.
    """

    @http.route('/document_extractor/extract', type='json', auth='user', methods=['POST'])
    def extract_document(self, pdf_data, filename, document_type):
        """
        Extract data from PDF using AI

        Args:
            pdf_data (str): Base64 encoded PDF file
            filename (str): Original filename
            document_type (str): '01' for Registration, '02' for Report

        Returns:
            dict: Action dictionary to open form in CREATE mode with extracted data
        """
        # Constants
        MAX_PDF_SIZE_MB = 50
        MAX_PDF_SIZE_BYTES = MAX_PDF_SIZE_MB * 1024 * 1024
        EXTRACTION_RATE_LIMIT_SECONDS = 5

        try:
            _logger.info(f"Starting extraction for {filename} (Type: {document_type})")

            # Validate file extension
            if not filename.lower().endswith('.pdf'):
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Invalid File Type',
                        'message': 'Only PDF files are allowed',
                        'type': 'danger',
                        'sticky': False,
                    }
                }

            # Decode PDF binary
            try:
                pdf_binary = base64.b64decode(pdf_data)
            except Exception as e:
                _logger.error(f"Failed to decode PDF: {e}")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Error',
                        'message': 'Failed to decode PDF file',
                        'type': 'danger',
                        'sticky': False,
                    }
                }

            # Validate file size
            pdf_size_bytes = len(pdf_binary)
            if pdf_size_bytes > MAX_PDF_SIZE_BYTES:
                pdf_size_mb = pdf_size_bytes / 1024 / 1024
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'File Too Large',
                        'message': f'File size ({pdf_size_mb:.1f}MB) exceeds maximum allowed size ({MAX_PDF_SIZE_MB}MB)',
                        'type': 'danger',
                        'sticky': False,
                    }
                }

            # Validate PDF magic bytes
            if not pdf_binary.startswith(b'%PDF'):
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Invalid PDF',
                        'message': 'The uploaded file does not appear to be a valid PDF',
                        'type': 'danger',
                        'sticky': False,
                    }
                }

            # Simple rate limiting
            import time
            last_extract_time = request.session.get('last_extract_time', 0)
            current_time = time.time()
            if current_time - last_extract_time < EXTRACTION_RATE_LIMIT_SECONDS:
                wait_seconds = int(EXTRACTION_RATE_LIMIT_SECONDS - (current_time - last_extract_time))
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Please Wait',
                        'message': f'Please wait {wait_seconds} seconds before extracting another document',
                        'type': 'warning',
                        'sticky': False,
                    }
                }
            request.session['last_extract_time'] = current_time

            # Call extraction service
            extraction_service = request.env['document.extraction.service']

            try:
                extracted_data = extraction_service.extract_pdf(pdf_binary, document_type, filename)
            except Exception as e:
                _logger.error(f"Extraction failed: {e}")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Extraction Failed',
                        'message': str(e),
                        'type': 'danger',
                        'sticky': True,
                    }
                }

            # Create public attachment for PDF (without res_id for preview)
            # This allows viewing PDF before saving the record
            attachment = request.env['ir.attachment'].sudo().create({
                'name': filename,
                'type': 'binary',
                'datas': pdf_data,
                'res_model': 'document.extraction',
                'res_id': 0,  # No res_id yet - will be updated on record save
                'public': True,  # Make public so it can be viewed without res_id
                'mimetype': 'application/pdf',
            })
            _logger.info(f"Created public attachment ID {attachment.id} for PDF preview")

            # Helper function to build One2many commands
            def build_o2m_commands(data_list):
                """Convert list of dicts to Odoo One2many commands: [(0, 0, values)]"""
                if not data_list:
                    return []
                return [(0, 0, item) for item in data_list]

            # Prepare context with default values
            context = {
                'default_document_type': document_type,
                'default_pdf_attachment_id': attachment.id,  # Pass attachment ID instead of base64
                'default_pdf_filename': filename,
                'default_year': extracted_data.get('year'),

                # Organization info
                'default_business_license_number': extracted_data.get('business_license_number'),
                'default_business_license_date': extracted_data.get('business_license_date'),
                'default_business_license_place': extracted_data.get('business_license_place'),
                'default_legal_representative_name': extracted_data.get('legal_representative_name'),
                'default_legal_representative_position': extracted_data.get('legal_representative_position'),
                'default_contact_person_name': extracted_data.get('contact_person_name'),
                'default_contact_address': extracted_data.get('contact_address'),
                'default_contact_phone': extracted_data.get('contact_phone'),
                'default_contact_fax': extracted_data.get('contact_fax'),
                'default_contact_email': extracted_data.get('contact_email'),
            }

            # Add One2many table data (Form 01)
            if document_type == '01':
                # Registration table flags
                context['default_has_table_1_1'] = extracted_data.get('has_table_1_1', False)
                context['default_has_table_1_2'] = extracted_data.get('has_table_1_2', False)
                context['default_has_table_1_3'] = extracted_data.get('has_table_1_3', False)
                context['default_has_table_1_4'] = extracted_data.get('has_table_1_4', False)

                # Table 1.1 - Substance Usage (already has is_title, sequence, usage_type from AI)
                context['default_substance_usage_ids'] = build_o2m_commands(
                    extracted_data.get('substance_usage', [])
                )

                # Table 1.2 - Equipment/Product
                context['default_equipment_product_ids'] = build_o2m_commands(
                    extracted_data.get('equipment_product', [])
                )

                # Table 1.3 - Equipment Ownership
                context['default_equipment_ownership_ids'] = build_o2m_commands(
                    extracted_data.get('equipment_ownership', [])
                )

                # Table 1.4 - Collection & Recycling (already has is_title, sequence, activity_type from AI)
                context['default_collection_recycling_ids'] = build_o2m_commands(
                    extracted_data.get('collection_recycling', [])
                )

            # Add One2many table data (Form 02)
            elif document_type == '02':
                # Report table flags
                context['default_has_table_2_1'] = extracted_data.get('has_table_2_1', False)
                context['default_has_table_2_2'] = extracted_data.get('has_table_2_2', False)
                context['default_has_table_2_3'] = extracted_data.get('has_table_2_3', False)
                context['default_has_table_2_4'] = extracted_data.get('has_table_2_4', False)

                # Table 2.1 - Quota Usage
                context['default_quota_usage_ids'] = build_o2m_commands(
                    extracted_data.get('quota_usage', [])
                )

                # Table 2.2 - Equipment/Product Report
                context['default_equipment_product_report_ids'] = build_o2m_commands(
                    extracted_data.get('equipment_product_report', [])
                )

                # Table 2.3 - Equipment Ownership Report
                context['default_equipment_ownership_report_ids'] = build_o2m_commands(
                    extracted_data.get('equipment_ownership_report', [])
                )

                # Table 2.4 - Collection & Recycling Report
                context['default_collection_recycling_report_ids'] = build_o2m_commands(
                    extracted_data.get('collection_recycling_report', [])
                )

            # Handle organization_id (search by business_license_number)
            business_license_number = extracted_data.get('business_license_number')
            if business_license_number:
                partner = request.env['res.partner'].search([
                    ('business_license_number', '=', business_license_number)
                ], limit=1)

                if partner:
                    context['default_organization_id'] = partner.id
                # If not found, organization will be created on save with info from extracted data

            # Always include organization_name
            context['default_organization_name'] = extracted_data.get('organization_name')

            # Handle activity_field_ids (map codes to Many2many IDs)
            activity_field_codes = extracted_data.get('activity_field_codes', [])
            if activity_field_codes:
                # Search for activity fields by codes
                activity_fields = request.env['activity.field'].search([
                    ('code', 'in', activity_field_codes)
                ])
                if activity_fields:
                    # Many2many command: [(6, 0, [ids])] = replace all with these IDs
                    context['default_activity_field_ids'] = [(6, 0, activity_fields.ids)]
                    _logger.info(f"Mapped {len(activity_fields)} activity fields: {activity_field_codes}")

            _logger.info(f"Extraction successful for {filename} (Type: {document_type})")

            # Return action to open form in CREATE mode
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'document.extraction',
                'view_mode': 'form',
                'views': [[False, 'form']],
                'target': 'current',
                'context': context,
            }

        except Exception as e:
            _logger.exception(f"Unexpected error in extraction controller: {e}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'System Error',
                    'message': f'An unexpected error occurred: {str(e)}',
                    'type': 'danger',
                    'sticky': True,
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

            # substance.usage has year_1/2/3_quantity_kg and avg_quantity_kg
            # We use avg_quantity_kg if available, otherwise sum year fields
            total_kg = 0
            total_co2e = 0
            for usage in all_substance_usage:
                # Use avg if available (check for None, not falsy), else calculate from years
                if usage.avg_quantity_kg is not None:
                    kg = usage.avg_quantity_kg
                else:
                    kg = (usage.year_1_quantity_kg or 0) + \
                         (usage.year_2_quantity_kg or 0) + \
                         (usage.year_3_quantity_kg or 0)

                if usage.avg_quantity_co2 is not None:
                    co2 = usage.avg_quantity_co2
                else:
                    co2 = (usage.year_1_quantity_co2 or 0) + \
                          (usage.year_2_quantity_co2 or 0) + \
                          (usage.year_3_quantity_co2 or 0)

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

                    # Use avg or sum of years (check for None, not falsy)
                    if usage.avg_quantity_kg is not None:
                        kg = usage.avg_quantity_kg
                    else:
                        kg = (usage.year_1_quantity_kg or 0) + \
                             (usage.year_2_quantity_kg or 0) + \
                             (usage.year_3_quantity_kg or 0)
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
                # Calculate total kg from year fields or avg (check for None, not falsy)
                if usage.avg_quantity_kg is not None:
                    kg = usage.avg_quantity_kg
                else:
                    kg = (usage.year_1_quantity_kg or 0) + \
                         (usage.year_2_quantity_kg or 0) + \
                         (usage.year_3_quantity_kg or 0)

                if usage.avg_quantity_co2 is not None:
                    co2 = usage.avg_quantity_co2
                else:
                    co2 = (usage.year_1_quantity_co2 or 0) + \
                          (usage.year_2_quantity_co2 or 0) + \
                          (usage.year_3_quantity_co2 or 0)

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
