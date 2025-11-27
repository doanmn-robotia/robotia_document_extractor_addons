# -*- coding: utf-8 -*-

import logging
from odoo import models, api

_logger = logging.getLogger(__name__)


class ExtractionHelper(models.AbstractModel):
    _name = 'extraction.helper'
    _description = 'Extraction Helper Service'

    @api.model
    def build_extraction_values(self, extracted_data, attachment, document_type, file_id=None, log_id=None):
        """
        Build values dict for document.extraction from extracted data

        Returns raw dict without 'default_' prefix - can be used for:
        - Direct create(): use as-is
        - Form context: add 'default_' prefix to keys

        :param extracted_data: Dict from extraction_service.extract_pdf()
        :param attachment: ir.attachment record
        :param document_type: '01' or '02'
        :param file_id: Google Drive file ID (optional, for cron)
        :param log_id: extraction.log ID (optional, for cron)
        :return: Dict of values ready for document.extraction
        """

        # Helper: Build One2many commands
        def build_o2m_commands(data_list):
            """
            Build One2many commands from data list

            Also cleans empty title sections:
            - Title row (is_title=True) without data children (is_title=False) → removed
            """
            if not data_list:
                return []

            # Clean empty sections first
            cleaned_data = []
            i = 0

            while i < len(data_list):
                row = data_list[i]

                # If not a title row, always keep
                if not row.get('is_title'):
                    cleaned_data.append(row)
                    i += 1
                    continue

                # Title row: check if it has children
                # Look ahead to find next title or end of list
                has_children = False
                j = i + 1

                while j < len(data_list):
                    next_row = data_list[j]

                    # If next row is also a title, this section is empty
                    if next_row.get('is_title'):
                        break

                    # Found a data row child
                    has_children = True
                    break

                # Only keep title if it has children
                if has_children:
                    cleaned_data.append(row)
                else:
                    _logger.debug(f"Removing empty section: {row.get('substance_name', 'Unknown')}")

                i += 1

            # Build One2many commands from cleaned data
            return [(0, 0, row) for row in cleaned_data]

        # Helper: Populate substance IDs
        def populate_substance_ids(table_data, substance_lookup):
            for row in table_data:
                substance_name = (row.get('substance_name') or '').strip()
                if substance_name and substance_name in substance_lookup:
                    row['substance_id'] = substance_lookup[substance_name]

        # ========== FUZZY MATCHING FOR SUBSTANCES ==========
        if document_type == '01':
            table_keys = ['substance_usage', 'equipment_product', 'equipment_ownership', 'collection_recycling']
        else:
            table_keys = ['quota_usage', 'equipment_product_report', 'equipment_ownership_report', 'collection_recycling_report']

        # Collect all substance names
        all_substance_info = []
        for table_key in table_keys:
            table_data = extracted_data.get(table_key, [])
            for row in table_data:
                substance_name = (row.get('substance_name') or '').strip()
                hs_code = (row.get('hs_code') or '').strip() or None
                if substance_name:
                    all_substance_info.append((substance_name, hs_code))

        # Build substance lookup
        substance_lookup = {}
        fuzzy_matcher = self.env['fuzzy.matcher']

        _logger.info(f"Looking up {len(all_substance_info)} substance entries with fuzzy matching")

        for substance_name, hs_code in all_substance_info:
            if substance_name in substance_lookup:
                continue

            found_substance = fuzzy_matcher.search_substance_fuzzy(
                search_term=substance_name,
                hs_code_term=hs_code
            )

            if found_substance:
                substance_lookup[substance_name] = found_substance.id
                _logger.info(
                    f"Fuzzy matched: '{substance_name}' (hs_code='{hs_code}') -> "
                    f"{found_substance.name} (id={found_substance.id})"
                )
            else:
                _logger.warning(f"No match found for substance: '{substance_name}' (hs_code='{hs_code}')")

        _logger.info(f"Fuzzy matching complete: Found {len(substance_lookup)} unique substances")

        # Populate substance_id in tables
        for table_key in table_keys:
            table_data = extracted_data.get(table_key, [])
            if table_data:
                populate_substance_ids(table_data, substance_lookup)

        # ========== COUNTRY/STATE LOOKUP ==========
        contact_country_id = False
        contact_state_id = False

        country_code = extracted_data.get('contact_country_code')
        if country_code:
            # Exact search
            country = self.env['res.country'].search([
                ('code', '=', country_code.upper())
            ], limit=1)

            if country:
                contact_country_id = country.id
                _logger.info(f"Exact match country: code='{country_code}' -> {country.name}")
            else:
                # Fuzzy fallback
                country = fuzzy_matcher.search_country_fuzzy(country_code)
                if country:
                    contact_country_id = country.id
                    _logger.info(f"Fuzzy matched country: '{country_code}' -> {country.name} ({country.code})")
                else:
                    _logger.warning(f"Country not found (exact & fuzzy failed): '{country_code}'")

        state_code = extracted_data.get('contact_state_code')
        if state_code and contact_country_id:
            # Exact search
            state = self.env['res.country.state'].search([
                ('code', '=', state_code.upper()),
                ('country_id', '=', contact_country_id)
            ], limit=1)

            if state:
                contact_state_id = state.id
                _logger.info(f"Exact match state: code='{state_code}' -> {state.name}")
            else:
                # Fuzzy fallback
                state = fuzzy_matcher.search_state_fuzzy(
                    search_term=state_code,
                    country_id=contact_country_id
                )
                if state:
                    contact_state_id = state.id
                    _logger.info(f"Fuzzy matched state: '{state_code}' -> {state.name} ({state.code})")
                else:
                    _logger.warning(
                        f"State not found (exact & fuzzy failed): '{state_code}' "
                        f"in country_id={contact_country_id}"
                    )

        # ========== BUILD VALUES DICT ==========
        vals = {
            'document_type': document_type,
            'pdf_attachment_id': attachment.id,
            'pdf_filename': attachment.name,
            'year': extracted_data.get('year'),
            'year_1': extracted_data.get('year_1'),
            'year_2': extracted_data.get('year_2'),
            'year_3': extracted_data.get('year_3'),

            # Organization info
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
            'contact_country_id': contact_country_id,
            'contact_state_id': contact_state_id,
        }

        # Optional fields for cron job
        if file_id:
            vals['gdrive_file_id'] = file_id
            vals['source'] = 'from_external_source'

        if log_id:
            vals['extraction_log_id'] = log_id

        # Activity fields (Many2many)
        activity_codes = extracted_data.get('activity_field_codes', [])
        if activity_codes:
            activity_fields = self.env['activity.field'].search([('code', 'in', activity_codes)])
            vals['activity_field_ids'] = [(6, 0, activity_fields.ids)]

        # Organization lookup by business_license_number
        business_license_number = extracted_data.get('business_license_number')
        if business_license_number:
            partner = self.env['res.partner'].search([
                ('business_license_number', '=', business_license_number)
            ], limit=1)

            if partner:
                vals['organization_id'] = partner.id
                _logger.info(f"Found existing organization: {partner.name} (ID: {partner.id})")
            # If not found, organization will be auto-created on save by document.extraction model

        # Form 01 specific
        if document_type == '01':
            vals['has_table_1_1'] = extracted_data.get('has_table_1_1', False)
            vals['has_table_1_2'] = extracted_data.get('has_table_1_2', False)
            vals['has_table_1_3'] = extracted_data.get('has_table_1_3', False)
            vals['has_table_1_4'] = extracted_data.get('has_table_1_4', False)
            vals['is_capacity_merged_table_1_2'] = extracted_data.get('is_capacity_merged_table_1_2', True)
            vals['is_capacity_merged_table_1_3'] = extracted_data.get('is_capacity_merged_table_1_3', True)

            vals['substance_usage_ids'] = build_o2m_commands(extracted_data.get('substance_usage', []))
            vals['equipment_product_ids'] = build_o2m_commands(extracted_data.get('equipment_product', []))
            vals['equipment_ownership_ids'] = build_o2m_commands(extracted_data.get('equipment_ownership', []))
            vals['collection_recycling_ids'] = build_o2m_commands(extracted_data.get('collection_recycling', []))

        # Form 02 specific
        elif document_type == '02':
            vals['has_table_2_1'] = extracted_data.get('has_table_2_1', False)
            vals['has_table_2_2'] = extracted_data.get('has_table_2_2', False)
            vals['has_table_2_3'] = extracted_data.get('has_table_2_3', False)
            vals['has_table_2_4'] = extracted_data.get('has_table_2_4', False)
            vals['is_capacity_merged_table_2_2'] = extracted_data.get('is_capacity_merged_table_2_2', True)
            vals['is_capacity_merged_table_2_3'] = extracted_data.get('is_capacity_merged_table_2_3', True)

            vals['quota_usage_ids'] = build_o2m_commands(extracted_data.get('quota_usage', []))
            vals['equipment_product_report_ids'] = build_o2m_commands(extracted_data.get('equipment_product_report', []))
            vals['equipment_ownership_report_ids'] = build_o2m_commands(extracted_data.get('equipment_ownership_report', []))
            vals['collection_recycling_report_ids'] = build_o2m_commands(extracted_data.get('collection_recycling_report', []))

        return vals
