# -*- coding: utf-8 -*-

from odoo import models, api
import base64
import json
import logging

try:
    # Import Google Generative AI library
    from google import genai
    from google.genai import types
except ImportError:
    raise ValueError(
        "Google Generative AI library not installed. "
        "Please install it: pip install google-generativeai"
    )

_logger = logging.getLogger(__name__)


class DocumentExtractionService(models.AbstractModel):
    """
    AI-powered document extraction service using Google Gemini API

    This service extracts structured data from PDF documents
    using Google's Gemini with PDF understanding capability.
    """
    _name = 'document.extraction.service'
    _description = 'Document Extraction Service'

    @api.model
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

    def extract_pdf(self, pdf_binary, document_type, filename):
        """
        Extract structured data from PDF using Gemini AI

        Args:
            pdf_binary (bytes): Binary PDF data
            document_type (str): '01' for Registration, '02' for Report
            filename (str): Original filename for logging

        Returns:
            dict: Structured data extracted from PDF

        Raises:
            ValueError: If API key not configured or extraction fails
        """
        _logger.info(f"Starting AI extraction for {filename} (Type: {document_type})")

        # Get Gemini API key from system parameters
        api_key = self.env['ir.config_parameter'].sudo().get_param('robotia_document_extractor.gemini_api_key')

        if not api_key:
            raise ValueError(
                "Gemini API key not configured. "
                "Please configure it in Settings > Document Extractor > Configuration"
            )

        # Configure Gemini
        client = genai.Client(api_key=api_key)

        # Build extraction prompt based on document type
        prompt = self._build_extraction_prompt(document_type)

        _logger.info(f"Calling Gemini API for extraction (PDF size: {len(pdf_binary)} bytes)")

        try:
            # Upload PDF file to Gemini
            # Note: Gemini requires file upload for large documents
            import tempfile
            import os

            # Create temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                tmp_file.write(pdf_binary)
                tmp_file_path = tmp_file.name

            try:
                # Upload file to Gemini
                uploaded_file = client.files.upload(file=tmp_file_path)
                _logger.info(f"File uploaded to Gemini: {uploaded_file.name}")

                # Wait for file to be processed
                import time
                while uploaded_file.state.name == "PROCESSING":
                    _logger.info("Waiting for file processing...")
                    time.sleep(2)
                    uploaded_file = client.files.get(name=uploaded_file.name)

                if uploaded_file.state.name == "FAILED":
                    raise ValueError("File processing failed in Gemini")

                # Generate content with the uploaded file
                response = client.models.generate_content(
                    model='gemini-2.0-flash-exp',
                    contents=[uploaded_file, prompt],
                    config=types.GenerateContentConfig(
                        temperature=0.1,  # Low temperature for consistent structured output
                        max_output_tokens=16000,
                        response_mime_type='application/json',  # Force JSON output
                        top_p=0.8,
                        top_k=40
                    )
                )

                # Get response text
                extracted_text = response.text

                _logger.info(f"Gemini API response received (length: {len(extracted_text)} chars)")

            finally:
                # Clean up temporary file
                if os.path.exists(tmp_file_path):
                    os.unlink(tmp_file_path)

                # Delete uploaded file from Gemini
                try:
                    client.files.delete(name=uploaded_file.name)
                except:
                    pass

            # Parse JSON from response
            try:
                # Find JSON block in response (Gemini may wrap it in markdown)
                if '```json' in extracted_text:
                    json_start = extracted_text.find('```json') + 7
                    json_end = extracted_text.find('```', json_start)
                    json_str = extracted_text[json_start:json_end].strip()
                elif '```' in extracted_text:
                    json_start = extracted_text.find('```') + 3
                    json_end = extracted_text.find('```', json_start)
                    json_str = extracted_text[json_start:json_end].strip()
                else:
                    json_str = extracted_text.strip()

                extracted_data = json.loads(json_str)
                _logger.info("Successfully parsed JSON response")

            except json.JSONDecodeError as e:
                _logger.error(f"Failed to parse JSON: {e}\nResponse: {extracted_text[:500]}")
                raise ValueError(f"Failed to parse AI response as JSON: {e}")

            # Validate and clean extracted data
            cleaned_data = self._clean_extracted_data(extracted_data, document_type)

            return cleaned_data

        except Exception as e:
            _logger.exception(f"Unexpected error during extraction: {e}")
            raise ValueError(f"Extraction failed: {str(e)}")

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
        return """
Analyze this Vietnamese Form 01 (Registration) PDF document for controlled substances and extract ALL data.

⚠️⚠️⚠️ CRITICAL TABLE STRUCTURE RULE ⚠️⚠️⚠️

**HOW TO IDENTIFY TITLE vs DATA ROWS:**

✅ TITLE ROW = Row with MERGED CELLS spanning across multiple columns
   - Contains section names (often bold): "Sản xuất chất được kiểm soát", "Nhập khẩu chất được kiểm soát", etc.
   - Does NOT contain specific substance/equipment names or quantity data
   - Mark as: is_title=true, all numeric fields=null

❌ DATA ROW = Row with SEPARATE CELLS (not merged)
   - Contains specific substance names, equipment models, or actual data values
   - Mark as: is_title=false, fill in actual data

Return a JSON object with this structure (all field names in English):

{
  "year": <integer>,
  "organization_name": "<string>",
  "business_license_number": "<string>",
  "business_license_date": "<YYYY-MM-DD or null>",
  "business_license_place": "<string>",
  "legal_representative_name": "<string>",
  "legal_representative_position": "<string>",
  "contact_person_name": "<string>",
  "contact_address": "<string>",
  "contact_phone": "<string>",
  "contact_fax": "<string>",
  "contact_email": "<string>",

  "activity_field_codes": [<array of codes from section "2. Nội dung đăng ký" - see mapping below>],

  "has_table_1_1": <boolean>,
  "has_table_1_2": <boolean>,
  "has_table_1_3": <boolean>,
  "has_table_1_4": <boolean>,

  "substance_usage": [
    {
      "is_title": <true for merged cell rows, false for data rows>,
      "sequence": <incremental number>,
      "usage_type": "<production|import|export>",
      "substance_name": "<string>",
      "year_1_quantity_kg": <float or null>,
      "year_1_quantity_co2": <float or null>,
      "year_2_quantity_kg": <float or null>,
      "year_2_quantity_co2": <float or null>,
      "year_3_quantity_kg": <float or null>,
      "year_3_quantity_co2": <float or null>,
      "avg_quantity_kg": <float or null>,
      "avg_quantity_co2": <float or null>
    }
  ],

  "equipment_product": [
    {
      "is_title": <true for merged cell rows, false for data rows>,
      "sequence": <incremental number>,
      "product_type": "<string>",
      "hs_code": "<string>",
      "capacity": "<string>",
      "quantity": <float or null>,
      "substance_name": "<string>",
      "substance_quantity_per_unit": <float or null>,
      "notes": "<string>"
    }
  ],

  "equipment_ownership": [
    {
      "is_title": <true for merged cell rows, false for data rows>,
      "sequence": <incremental number>,
      "equipment_type": "<string>",
      "start_year": <integer or null>,
      "capacity": "<string>",
      "equipment_quantity": <integer or null>,
      "substance_name": "<string>",
      "refill_frequency": <float or null>,
      "substance_quantity_per_refill": <float or null>
    }
  ],

  "collection_recycling": [
    {
      "is_title": <true for merged cell rows, false for data rows>,
      "sequence": <incremental number>,
      "activity_type": "<collection|reuse|recycle|disposal>",
      "substance_name": "<string>",
      "quantity_kg": <float or null>,
      "quantity_co2": <float or null>
    }
  ]
}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXTRACTION RULES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STEP 1: EXTRACT ACTIVITY FIELD CODES (Section "2. Nội dung đăng ký")

   Look for checkboxes (☑ or ☐) in section "2.a) Lĩnh vực sử dụng chất được kiểm soát"

   Map Vietnamese labels to codes:
   - "Sản xuất chất được kiểm soát" → "production"
   - "Nhập khẩu chất được kiểm soát" → "import"
   - "Xuất khẩu chất được kiểm soát" → "export"
   - "Sản xuất thiết bị, sản phẩm..." → "equipment_production"
   - "Nhập khẩu thiết bị, sản phẩm..." → "equipment_import"
   - "Sở hữu máy điều hòa không khí..." → "ac_ownership"
   - "Sở hữu thiết bị lạnh công nghiệp..." → "refrigeration_ownership"
   - "Thu gom, tái chế, tái sử dụng..." → "collection_recycling"

   Return array of checked codes, empty array [] if none checked.

STEP 2: DETERMINE TABLE PRESENCE based on activity fields

   **Activity Fields → Tables Mapping:**

   has_table_1_1 = true IF any of these is checked:
     - "production" OR "import" OR "export"

   has_table_1_2 = true IF any of these is checked:
     - "equipment_production" OR "equipment_import"

   has_table_1_3 = true IF any of these is checked:
     - "ac_ownership" OR "refrigeration_ownership"

   has_table_1_4 = true IF this is checked:
     - "collection_recycling"

STEP 3: CONDITIONAL EXTRACTION - Extract ONLY relevant sub-sections

   For Table 1.1 (Bảng 1.1: Substance Usage):
   - IF "production" checked → extract title "Sản xuất chất được kiểm soát" + data rows
   - IF "import" checked → extract title "Nhập khẩu chất được kiểm soát" + data rows
   - IF "export" checked → extract title "Xuất khẩu chất được kiểm soát" + data rows
   - DO NOT create title rows for unchecked activities

   For Table 1.2 (Bảng 1.2: Equipment/Product):
   - IF "equipment_production" checked → extract rows with production data
   - IF "equipment_import" checked → extract rows with import data
   - May have merged title rows "Sản xuất thiết bị..." or "Nhập khẩu thiết bị..."

   For Table 1.3 (Bảng 1.3: Equipment Ownership):
   - IF "ac_ownership" checked → extract title "Máy điều hòa không khí..." + data rows
   - IF "refrigeration_ownership" checked → extract title "Thiết bị lạnh công nghiệp..." + data rows

   For Table 1.4 (Bảng 1.4: Collection & Recycling):
   - Always has 4 sub-sections if table exists: Thu gom, Tái sử dụng, Tái chế, Xử lý
   - Extract all 4 title rows + their data rows

STEP 4: EXTRACT TABLE DATA

   For each table that exists (has_table_1_x = true):
   - Identify MERGED CELL rows → create title entries (is_title=true, numeric fields=null)
   - Identify SEPARATE CELL rows → create data entries (is_title=false, fill actual values)
   - Use sequential numbering for "sequence" field
   - Extract ALL rows completely based on conditional extraction rules above

STEP 5: DATA CONVERSION

   - Convert Vietnamese numbers to float/int (handle commas "," and dots "." correctly)
   - Use null for empty/missing numeric values (NEVER empty string or 0)
   - Preserve Vietnamese text EXACTLY for names, addresses, text fields

STEP 6: OUTPUT FORMAT

   - Return ONLY valid JSON, no explanations or markdown code blocks
   - Use "null" for missing values (not "None", not empty string)
"""

    def _get_default_prompt_form_02(self):
        """
        Get default extraction prompt for Form 02 (Report)

        Returns:
            str: Default Form 02 extraction prompt
        """
        return """
Analyze this Vietnamese Form 02 (Report) PDF document for controlled substances and extract ALL data.

Return a JSON object with this EXACT structure (all field names in English):

{
  "year": <integer>,
  "organization_name": "<string>",
  "business_license_number": "<string>",
  "business_license_date": "<YYYY-MM-DD or null>",
  "business_license_place": "<string>",
  "legal_representative_name": "<string>",
  "legal_representative_position": "<string>",
  "contact_person_name": "<string>",
  "contact_address": "<string>",
  "contact_phone": "<string>",
  "contact_fax": "<string>",
  "contact_email": "<string>",

  "activity_field_codes": [<array of codes from section "b) Thông tin về lĩnh vực hoạt động sử dụng chất được kiểm soát">],

  "quota_usage": [
    {
      "substance_name": "<string>",
      "hs_code": "<string>",
      "allocated_quota_kg": <float or null>,
      "allocated_quota_co2": <float or null>,
      "adjusted_quota_kg": <float or null>,
      "adjusted_quota_co2": <float or null>,
      "total_quota_kg": <float or null>,
      "total_quota_co2": <float or null>,
      "average_price": <float or null>,
      "export_import_location": "<string>",
      "customs_declaration_number": "<string>",
      "next_year_quota_kg": <float or null>,
      "next_year_quota_co2": <float or null>
    }
  ],

  "equipment_product_report": [
    {
      "product_type": "<string>",
      "hs_code": "<string>",
      "capacity": "<string>",
      "quantity": <float or null>,
      "substance_name": "<string>",
      "substance_quantity_per_unit": <float or null>,
      "notes": "<string>"
    }
  ],

  "equipment_ownership_report": [
    {
      "equipment_type": "<string>",
      "equipment_quantity": <integer or null>,
      "substance_name": "<string>",
      "capacity": "<string>",
      "start_year": <integer or null>,
      "refill_frequency": <float or null>,
      "substance_quantity_per_refill": <float or null>,
      "notes": "<string>"
    }
  ],

  "collection_recycling_report": [
    {
      "substance_name": "<string>",
      "collection_quantity_kg": <float or null>,
      "collection_location": "<string>",
      "storage_location": "<string>",
      "reuse_quantity_kg": <float or null>,
      "reuse_technology": "<string>",
      "recycle_quantity_kg": <float or null>,
      "recycle_technology": "<string>",
      "recycle_usage_location": "<string>",
      "disposal_quantity_kg": <float or null>,
      "disposal_technology": "<string>",
      "disposal_facility": "<string>"
    }
  ]
}

CRITICAL INSTRUCTIONS:
1. EXTRACT ACTIVITY FIELD CODES from section "b) Thông tin về lĩnh vực hoạt động sử dụng chất được kiểm soát"
   Map Vietnamese labels to codes (same as Form 01):
   - "Sản xuất chất được kiểm soát" → "production"
   - "Nhập khẩu chất được kiểm soát" → "import"
   - "Xuất khẩu chất được kiểm soát" → "export"
   - "Sản xuất thiết bị, sản phẩm có chứa..." → "equipment_production"
   - "Nhập khẩu thiết bị, sản phẩm có chứa..." → "equipment_import"
   - "Sở hữu máy điều hòa không khí..." → "ac_ownership"
   - "Sở hữu thiết bị lạnh công nghiệp..." → "refrigeration_ownership"
   - "Thu gom, tái chế, tái sử dụng và xử lý..." → "collection_recycling"
   Return as array where checkbox is checked or text is present

2. Extract ALL tables completely - read every single row
3. Table 2.4 has complex structure with multiple columns per substance - read carefully
4. Convert Vietnamese numbers to float/int (handle commas, dots correctly)
5. Use null for empty/missing values in numeric fields, never use empty strings
6. Return ONLY valid JSON, no explanations or markdown formatting
7. Preserve Vietnamese text exactly for names, addresses, and text fields
8. Be very careful with table structure - make sure you're reading the correct columns
"""

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
            'organization_name': data.get('organization_name', ''),
            'business_license_number': data.get('business_license_number', ''),
            'business_license_date': data.get('business_license_date'),
            'business_license_place': data.get('business_license_place', ''),
            'legal_representative_name': data.get('legal_representative_name', ''),
            'legal_representative_position': data.get('legal_representative_position', ''),
            'contact_person_name': data.get('contact_person_name', ''),
            'contact_address': data.get('contact_address', ''),
            'contact_phone': data.get('contact_phone', ''),
            'contact_fax': data.get('contact_fax', ''),
            'contact_email': data.get('contact_email', ''),
            'activity_field_codes': data.get('activity_field_codes', []),
        }

        # Add table data based on document type
        if document_type == '01':
            cleaned.update({
                'has_table_1_1': data.get('has_table_1_1', False),
                'has_table_1_2': data.get('has_table_1_2', False),
                'has_table_1_3': data.get('has_table_1_3', False),
                'has_table_1_4': data.get('has_table_1_4', False),
                'substance_usage': data.get('substance_usage', []),
                'equipment_product': data.get('equipment_product', []),
                'equipment_ownership': data.get('equipment_ownership', []),
                'collection_recycling': data.get('collection_recycling', []),
            })
        else:  # '02'
            cleaned.update({
                'quota_usage': data.get('quota_usage', []),
                'equipment_product_report': data.get('equipment_product_report', []),
                'equipment_ownership_report': data.get('equipment_ownership_report', []),
                'collection_recycling_report': data.get('collection_recycling_report', []),
            })

        _logger.info(f"Data cleaned successfully (Type: {document_type})")
        return cleaned
