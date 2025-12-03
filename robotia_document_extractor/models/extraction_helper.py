# -*- coding: utf-8 -*-

import logging
from odoo import models, api

_logger = logging.getLogger(__name__)


# ========== VALIDATION CONSTANTS ==========

# Technical fields to skip during validation
TECHNICAL_FIELDS = {
    'id', 'create_uid', 'create_date', 'write_uid', 'write_date',
    '__last_update', 'display_name', 'document_id'
}

# Special field mappings (extracted_key → model_field)
SPECIAL_FIELD_MAPPINGS = {
    'activity_field_codes': 'activity_field_ids',
    'contact_country_code': 'contact_country_id',
    'contact_state_code': 'contact_state_id',
}

# One2many relation field mappings
# Format: {extracted_key: (model_name, field_name_in_main_model)}
RELATION_MAPPINGS = {
    # Form 01
    'substance_usage': ('substance.usage', 'substance_usage_ids'),
    'equipment_product': ('equipment.product', 'equipment_product_ids'),
    'equipment_ownership': ('equipment.ownership', 'equipment_ownership_ids'),
    'collection_recycling': ('collection.recycling', 'collection_recycling_ids'),
    # Form 02
    'quota_usage': ('quota.usage', 'quota_usage_ids'),
    'equipment_product_report': ('equipment.product.report', 'equipment_product_report_ids'),
    'equipment_ownership_report': ('equipment.ownership.report', 'equipment_ownership_report_ids'),
    'collection_recycling_report': ('collection.recycling.report', 'collection_recycling_report_ids'),
}


class ExtractionHelper(models.AbstractModel):
    _name = 'extraction.helper'
    _description = 'Extraction Helper Service'

    # ========== VALIDATION METHODS ==========

    def _validate_integer_field(self, value, field_name):
        """
        Validate and convert value to integer
        
        Args:
            value: Value to validate
            field_name (str): Field name for logging
            
        Returns:
            int: Converted integer value, or 0 if conversion fails
        """
        if value is None:
            return 0
            
        try:
            # Handle float → int (e.g., 1.1 → 1)
            if isinstance(value, float):
                converted = int(value)
                if value != converted:
                    _logger.info(f"Converted float to int for '{field_name}': {value} → {converted}")
                return converted
            
            # Handle string → int (e.g., "5" → 5)
            if isinstance(value, str):
                converted = int(float(value))  # float() first to handle "1.1"
                _logger.info(f"Converted string to int for '{field_name}': '{value}' → {converted}")
                return converted
            
            # Already int
            if isinstance(value, int):
                return value
                
            # Unknown type
            _logger.warning(f"Cannot convert {type(value)} to int for '{field_name}': {value}, using 0")
            return 0
            
        except (ValueError, TypeError) as e:
            _logger.warning(f"Failed to convert '{field_name}' value '{value}' to int: {e}, using 0")
            return 0

    def _validate_many2one_field(self, value, field_name):
        """
        Validate Many2one field value (must be integer ID)
        
        Args:
            value: Value to validate
            field_name (str): Field name for logging
            
        Returns:
            int or False: Valid integer ID, or False if invalid
        """
        if value is None or value is False:
            return False
            
        try:
            # Convert to int
            if isinstance(value, (int, float, str)):
                id_value = int(float(str(value)))
                if id_value <= 0:
                    _logger.warning(f"Invalid Many2one ID for '{field_name}': {value} (must be > 0)")
                    return False
                return id_value
            
            _logger.warning(f"Invalid Many2one value type for '{field_name}': {type(value)}")
            return False
            
        except (ValueError, TypeError) as e:
            _logger.warning(f"Cannot convert '{field_name}' value '{value}' to Many2one ID: {e}")
            return False

    def _validate_selection_field(self, value, field_obj, field_name):
        """
        Validate Selection field value against allowed values
        
        Args:
            value: Value to validate
            field_obj: Odoo field object
            field_name (str): Field name for logging
            
        Returns:
            str or None: Valid selection value, field default, or None
        """
        if value is None:
            # Use field default if available
            return field_obj.default if hasattr(field_obj, 'default') else None
        
        # Get allowed selection values
        selection = field_obj.selection
        if callable(selection):
            # Dynamic selection - cannot validate, return as-is
            _logger.info(f"Selection field '{field_name}' has dynamic values, skipping validation")
            return value
        
        # Static selection - validate
        allowed_values = [sel[0] for sel in selection] if selection else []
        
        if value in allowed_values:
            return value
        
        # Invalid value - use default
        default_value = field_obj.default if hasattr(field_obj, 'default') else None
        _logger.warning(
            f"Invalid selection value '{value}' for '{field_name}'. "
            f"Allowed: {allowed_values}. Using default: {default_value}"
        )
        return default_value

    def _validate_field_value(self, field_name, field_obj, value):
        """
        Validate and convert field value based on field type
        
        Args:
            field_name (str): Field name
            field_obj: Odoo field object
            value: Value to validate
            
        Returns:
            Validated/converted value
        """
        field_type = field_obj.type
        
        if field_type == 'integer':
            return self._validate_integer_field(value, field_name)
        
        elif field_type == 'many2one':
            return self._validate_many2one_field(value, field_name)
        
        elif field_type == 'selection':
            return self._validate_selection_field(value, field_obj, field_name)
        
        # Other types - return as-is
        # TODO: Add validation for float, boolean, date, datetime if needed
        return value

    def _validate_extracted_data_keys(self, extracted_data, document_type):
        """
        Validate that all keys in extracted_data exist in corresponding Odoo models
        and validate field types (Integer, Many2one, Selection)
        
        This method checks:
        1. Main document fields exist in document.extraction model
        2. One2many relation fields exist (substance_usage, equipment_product, etc.)
        3. Nested record fields exist in their respective models
        4. Field values match expected types (Integer, Many2one, Selection)
        
        Args:
            extracted_data (dict): Extracted data from AI
            document_type (str): '01' or '02'
            
        Returns:
            dict: Validated extracted_data with invalid keys removed and types validated
        """
        _logger.info(f"Validating extracted data keys for document type {document_type}")
        
        # Get document.extraction model
        DocumentModel = self.env['document.extraction']
        main_model_fields = DocumentModel._fields
        
        validated_data = {}
        invalid_keys = []
        
        # Validate main-level keys
        for key, value in extracted_data.items():
            # Check if key is a relation field
            if key in RELATION_MAPPINGS:
                validated_value = self._validate_relation_field(
                    key, value, main_model_fields
                )
                if validated_value is not None:
                    validated_data[key] = validated_value
                else:
                    invalid_keys.append(key)
                    
            else:
                # Regular field - validate and apply type checking
                validated_value = self._validate_regular_field(
                    key, value, main_model_fields, DocumentModel
                )
                if validated_value is not None:
                    validated_data[key] = validated_value
                else:
                    invalid_keys.append(key)
        
        # Log summary
        if invalid_keys:
            _logger.warning(
                f"Removed {len(invalid_keys)} invalid top-level keys: {invalid_keys}"
            )
        
        _logger.info(
            f"Validation complete: {len(validated_data)} valid keys, "
            f"{len(invalid_keys)} invalid keys removed"
        )
        
        return validated_data

    def _validate_relation_field(self, key, value, main_model_fields):
        """
        Validate One2many/Many2many relation field
        
        Args:
            key (str): Extracted data key
            value: List of record dicts
            main_model_fields (dict): Main model fields
            
        Returns:
            list or None: Validated records, or None if invalid
        """
        model_name, field_name = RELATION_MAPPINGS[key]
        
        # Validate that the relation field exists in main model
        if field_name not in main_model_fields:
            _logger.warning(f"Invalid relation field '{field_name}' for key '{key}' - skipping")
            return None
        
        # Validate nested records
        if not isinstance(value, list):
            _logger.warning(f"Expected list for relation field '{key}', got {type(value)} - skipping")
            return None
        
        validated_records = []
        RelationModel = self.env[model_name]
        relation_model_fields = RelationModel._fields
        
        for idx, record in enumerate(value):
            if not isinstance(record, dict):
                _logger.warning(f"Invalid record format in '{key}[{idx}]' - expected dict, got {type(record)}")
                continue
            
            validated_record = {}
            invalid_record_keys = []
            
            for record_key, record_value in record.items():
                # Skip technical fields that will be auto-generated
                if record_key in TECHNICAL_FIELDS:
                    continue
                
                # Check if field exists in relation model
                if record_key not in relation_model_fields:
                    _logger.warning(
                        f"Invalid field '{record_key}' in {model_name} "
                        f"(record {idx} of '{key}') - skipping"
                    )
                    invalid_record_keys.append(record_key)
                    continue
                
                # Validate field type
                field_obj = relation_model_fields[record_key]
                validated_value = self._validate_field_value(record_key, field_obj, record_value)
                validated_record[record_key] = validated_value
            
            if invalid_record_keys:
                _logger.info(
                    f"Removed {len(invalid_record_keys)} invalid keys from {model_name} record {idx}: "
                    f"{invalid_record_keys}"
                )
            
            if validated_record:  # Only add if there are valid fields
                validated_records.append(validated_record)
        
        _logger.info(f"Validated '{key}': {len(validated_records)} records")
        return validated_records

    def _validate_regular_field(self, key, value, main_model_fields, DocumentModel):
        """
        Validate regular (non-relation) field
        
        Args:
            key (str): Field key
            value: Field value
            main_model_fields (dict): Main model fields
            DocumentModel: Document extraction model
            
        Returns:
            Validated value or None if invalid
        """
        # Special handling for mapped fields
        if key in SPECIAL_FIELD_MAPPINGS:
            target_field = SPECIAL_FIELD_MAPPINGS[key]
            if target_field in main_model_fields:
                # No type validation for special fields (handled by extraction_helper)
                return value
            else:
                _logger.warning(f"Field '{target_field}' not found in document.extraction model")
                return None
        
        # Check if field exists in main model
        if key not in main_model_fields:
            _logger.warning(f"Invalid field '{key}' in document.extraction model - skipping")
            return None
        
        # Validate field type
        field_obj = main_model_fields[key]
        validated_value = self._validate_field_value(key, field_obj, value)
        return validated_value

    # ========== MAIN HELPER METHOD ==========

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

        # Validate extracted data first (type checking + field validation)
        # This ensures ALL extraction flows are validated (manual, page selector, log, cron)
        extracted_data = self._validate_extracted_data_keys(extracted_data, document_type)

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
