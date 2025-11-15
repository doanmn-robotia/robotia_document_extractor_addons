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
        try:
            _logger.info(f"Starting extraction for {filename} (Type: {document_type})")

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

            # Helper function to build One2many commands
            def build_o2m_commands(data_list):
                """Convert list of dicts to Odoo One2many commands: [(0, 0, values)]"""
                if not data_list:
                    return []
                return [(0, 0, item) for item in data_list]

            # Prepare context with default values
            context = {
                'default_document_type': document_type,
                'default_pdf_file': pdf_data,
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
