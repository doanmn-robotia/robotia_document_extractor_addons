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
        Extract structured data from PDF using Gemini AI with 2-tier fallback strategy

        Strategy 1 (Primary): Direct PDF → JSON extraction
        Strategy 2 (Fallback): 2-step extraction (PDF → Text → JSON) if Strategy 1 fails

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

        # Strategy 1: Try direct PDF → JSON extraction (existing method)
        try:
            _logger.info("=" * 70)
            _logger.info("STRATEGY 1: Direct PDF → JSON extraction")
            _logger.info("=" * 70)
            extracted_data = self._extract_direct_pdf_to_json(client, pdf_binary, document_type, filename)
            _logger.info("✓ Strategy 1 succeeded - Direct extraction successful")
            return extracted_data

        except Exception as e:
            _logger.warning("✗ Strategy 1 failed - Direct extraction unsuccessful")
            _logger.warning(f"Error: {type(e).__name__}: {str(e)}")
            _logger.info("Falling back to Strategy 2...")

            # Strategy 2: Fallback to 2-step extraction (PDF → Text → JSON)
            try:
                _logger.info("=" * 70)
                _logger.info("STRATEGY 2: 2-Step extraction (PDF → Text → JSON)")
                _logger.info("=" * 70)

                # Step 1: Extract PDF to plain text
                _logger.info("Step 1/2: Extracting PDF to plain text...")
                extracted_text = self._extract_pdf_to_text(client, pdf_binary, document_type, filename)
                _logger.info(f"✓ Step 1 complete - Extracted {len(extracted_text)} chars of text")

                # Step 2: Convert text to structured JSON
                _logger.info("Step 2/2: Converting text to structured JSON...")
                extracted_data = self._convert_text_to_json(client, extracted_text, document_type)
                _logger.info("✓ Step 2 complete - JSON conversion successful")

                _logger.info("✓ Strategy 2 succeeded - 2-step extraction successful")
                return extracted_data

            except Exception as e2:
                _logger.error("✗ Strategy 2 also failed - All extraction strategies exhausted")
                _logger.exception(f"Final error: {type(e2).__name__}: {str(e2)}")
                raise ValueError(
                    f"All extraction strategies failed. "
                    f"Strategy 1 error: {str(e)}. "
                    f"Strategy 2 error: {str(e2)}"
                )

    def _extract_direct_pdf_to_json(self, client, pdf_binary, document_type, filename):
        """
        Strategy 1: Direct PDF → JSON extraction (original method)

        Args:
            client: Gemini client instance
            pdf_binary (bytes): Binary PDF data
            document_type (str): '01' or '02'
            filename (str): Original filename for logging

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
        import tempfile
        import os
        import time

        # Constants
        GEMINI_POLL_INTERVAL_SECONDS = 2
        GEMINI_MAX_POLL_RETRIES = 30  # 30 * 2s = 60s timeout
        GEMINI_MAX_RETRIES = 3  # Retry on incomplete responses

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

        tmp_file_path = None
        uploaded_file = None

        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                tmp_file.write(pdf_binary)
                tmp_file_path = tmp_file.name

            _logger.info(f"Created temp file: {tmp_file_path}")

            # Upload file to Gemini
            uploaded_file = client.files.upload(file=tmp_file_path)
            _logger.info(f"File uploaded to Gemini: {uploaded_file.name}")

            # Wait for file to be processed with timeout
            poll_count = 0
            while uploaded_file.state.name == "PROCESSING":
                if poll_count >= GEMINI_MAX_POLL_RETRIES:
                    raise TimeoutError(f"Gemini file processing timeout after {GEMINI_MAX_POLL_RETRIES * GEMINI_POLL_INTERVAL_SECONDS}s")

                _logger.info(f"Waiting for file processing... (attempt {poll_count + 1}/{GEMINI_MAX_POLL_RETRIES})")
                time.sleep(GEMINI_POLL_INTERVAL_SECONDS)
                uploaded_file = client.files.get(name=uploaded_file.name)
                poll_count += 1

            if uploaded_file.state.name == "FAILED":
                raise ValueError("File processing failed in Gemini")

            _logger.info(f"File processing completed: {uploaded_file.state.name}")

            # Build mega prompt context (substances list + mapping rules)
            mega_context = self._build_mega_prompt_context()

            # Generate content with retry logic for incomplete responses
            extracted_text = None
            last_error = None

            for retry_attempt in range(GEMINI_MAX_RETRIES):
                try:
                    _logger.info(f"Gemini API call attempt {retry_attempt + 1}/{GEMINI_MAX_RETRIES}")

                    # Generate content with mega context + uploaded file + prompt
                    response = client.models.generate_content(
                        model=GEMINI_MODEL,
                        contents=mega_context + [uploaded_file, prompt],
                        config=types.GenerateContentConfig(
                            temperature=0.1,  # Low temperature for consistent structured output
                            max_output_tokens=GEMINI_MAX_TOKENS,
                            response_mime_type='application/json',  # Force JSON output
                            top_p=0.8,
                            top_k=40
                        )
                    )

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
                        # Wait before retry (exponential backoff)
                        wait_time = 2 ** retry_attempt  # 1s, 2s, 4s
                        _logger.info(f"Retrying in {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        # Last attempt failed - will be caught below
                        _logger.error("All retry attempts failed - response still incomplete")
                except Exception as e:
                    last_error = e
                    _logger.warning(f"Attempt {retry_attempt + 1} failed: {type(e).__name__}: {str(e)}")
                    if retry_attempt < GEMINI_MAX_RETRIES - 1:
                        wait_time = 2 ** retry_attempt
                        _logger.info(f"Retrying in {wait_time}s...")
                        time.sleep(wait_time)
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

        # Group substances by type for better organization
        hfc_singles = []
        hfc_blends = []
        hcfc_list = []

        for substance in substances:
            line = f"  - {substance.name:20s} | Code: {substance.code:15s} | GWP: {substance.gwp}"

            # Categorize by name/code pattern
            if substance.code.startswith('R-') and not substance.code.startswith('R-1') and not substance.code.startswith('R-2'):
                hfc_blends.append(line)
            elif substance.name.startswith('HCFC'):
                hcfc_list.append(line)
            elif substance.name.startswith('HFC'):
                hfc_singles.append(line)
            else:
                hfc_blends.append(line)

        # Build mega prompt text
        mega_prompt_text = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔬 REFRIGERANT STANDARDIZATION CONTEXT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ CRITICAL: SUBSTANCE NAME STANDARDIZATION REQUIRED ⚠️

You have access to the OFFICIAL LIST of {len(substances)} controlled substances below.

When you extract a substance name from the document, you MUST:
1. Compare it against the official list (both "Name" and "Code" columns)
2. Find the BEST MATCH using intelligent fuzzy matching
3. Return the EXACT standardized name from the official list
4. If no reasonable match exists, prefix with "[UNKNOWN] "

⚠️ HS CODE LOGIC - IMPORTANT:
- If substance name is empty, generic (e.g., "HFC"), or unclear
- AND an HS code is provided in the document
- Extract the HS code accurately - the system will use it to lookup the substance
- Common HS codes for refrigerants: 2903.39, 2903.41, 3824.78, etc.
- HS code can help identify the exact substance when name is ambiguous

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🧠 INTELLIGENT MATCHING STRATEGY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

You should be flexible and intelligent when matching substance names. Consider:

Common Variations:
  - Missing hyphens: "HFC134a" matches "HFC-134a"
  - Extra spaces: "HFC - 134a" matches "HFC-134a"
  - Case differences: "hfc-134a" matches "HFC-134a"
  - Code vs Name: "R-22" (code) matches "HCFC-22" (name)
  - Partial matches: "R410" might match "R-410A"

Vietnamese Documents May Use:
  - Alternative notations
  - Abbreviated forms
  - Mixed nomenclature (switching between name and code)
  - Non-standard punctuation

Your Task:
  → Use your intelligence to find the closest match in the official list
  → Consider both semantic meaning and pattern similarity
  → Don't be limited by specific rules - think flexibly!
  → When in doubt, match to the most similar substance

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📚 OFFICIAL CONTROLLED SUBSTANCES LIST ({len(substances)} substances)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

HFC - Hydrofluorocarbons (Single Components):
{chr(10).join(hfc_singles) if hfc_singles else '  (None)'}

HFC Blends / Refrigerant Mixtures:
{chr(10).join(hfc_blends) if hfc_blends else '  (None)'}

HCFC - Hydrochlorofluorocarbons:
{chr(10).join(hcfc_list) if hcfc_list else '  (None)'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 MATCHING EXAMPLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Document Says        → Your Output (matched from list above)
────────────────────────────────────────────────────────────
"HFC-134a"          → "HFC-134a" ✓ (exact match)
"HFC134a"           → "HFC-134a" ✓ (missing hyphen)
"R-134a"            → "HFC-134a" ✓ (code to name)
"R410A"             → "R-410A" ✓ (missing hyphens)
"r 22"              → "HCFC-22" ✓ (case + spaces, match code R-22)
"Freon 22"          → Check if similar to any substance, possibly "HCFC-22"
"134a"              → "HFC-134a" ✓ (partial, obvious match)
"XYZ-999"           → "[UNKNOWN] XYZ-999" ⚠️ (not in list)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ USE YOUR AI INTELLIGENCE TO MATCH INTELLIGENTLY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

        # Query all active activity fields from database
        activity_fields = self.env['activity.field'].search([
            ('active', '=', True)
        ], order='sequence')

        # Build activity fields context
        activity_fields_text = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏢 ACTIVITY FIELDS STANDARDIZATION CONTEXT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ CRITICAL: ACTIVITY FIELD CODE MAPPING REQUIRED ⚠️

You have access to the OFFICIAL LIST of {len(activity_fields)} activity fields below.

When you extract activity fields from the document, you MUST:
1. Identify checked/selected activities from section "2. Nội dung đăng ký" (Form 01)
   or "b) Thông tin về lĩnh vực hoạt động" (Form 02)
2. Match each activity to the EXACT code from the official list below
3. Return ONLY the codes in the "activity_field_codes" array
4. If an activity doesn't match any official field, skip it (do NOT create unknown codes)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 OFFICIAL ACTIVITY FIELDS LIST ({len(activity_fields)} fields)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Code                    | Activity Field Name
────────────────────────────────────────────────────────────────────────
{chr(10).join([f'{field.code:23s} | {field.name}' for field in activity_fields])}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🧠 MATCHING EXAMPLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Document Shows (checkbox checked)           → Code to Return
────────────────────────────────────────────────────────────────────────
"Sản xuất chất được kiểm soát"              → "production"
"Nhập khẩu chất được kiểm soát"             → "import"
"Xuất khẩu chất được kiểm soát"             → "export"
"Sản xuất thiết bị chứa chất..."            → "equipment_production"
"Nhập khẩu thiết bị chứa chất..."           → "equipment_import"
"Sở hữu hệ thống điều hòa..."               → "ac_ownership"
"Sở hữu thiết bị làm lạnh công nghiệp..."   → "refrigeration_ownership"
"Thu gom, tái chế, tái sử dụng..."          → "collection_recycling"

⚠️ IMPORTANT:
- ONLY return codes that are checked/selected in the document!
- Do NOT return codes that are not checked
- Return as array: "activity_field_codes": ["production", "import"]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

        # Return as list of types.Part.from_text (can add more context items in the future)
        return [
            types.Part.from_text(text=mega_prompt_text),      # Substances context
            types.Part.from_text(text=activity_fields_text)   # Activity fields context
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

    def _build_text_extraction_prompt(self, document_type):
        """
        Build simple text extraction prompt (Strategy 2 - Step 1)

        This prompt asks AI to extract PDF content as plain text,
        without JSON structure. Simpler = less likely to be truncated.

        Args:
            document_type (str): '01' or '02'

        Returns:
            str: Text extraction prompt
        """
        form_name = "Form 01 (Registration)" if document_type == '01' else "Form 02 (Report)"

        return f"""
Read this Vietnamese {form_name} PDF document and extract ALL the text content.

INSTRUCTIONS:
1. Extract ALL text from the document, preserving the structure as much as possible
2. Include section headers, table headers, and all data rows
3. Preserve Vietnamese text exactly as it appears
4. For tables, indicate rows clearly (use "Row N:" prefix)
5. For sections, use clear separators like "=== Section Name ==="
6. Extract ALL numerical values (preserve commas, dots as they appear)
7. DO NOT summarize - extract EVERYTHING verbatim

OUTPUT FORMAT:
- Plain text format
- Preserve document structure
- One line per data row in tables
- Clear section separators

Example format:
=== Organization Information ===
Name: [organization name]
License Number: [number]
...

=== Table 1.1: Substance Usage ===
HEADER: Substance Name | Year 1 (kg) | Year 2 (kg) | Year 3 (kg) | Average (kg)
Row 1: R-22 | 100.5 | 120.0 | 110.5 | 110.33
Row 2: R-410A | 200.0 | 210.0 | 205.0 | 205.00
...

Extract ALL content from this document now.
"""

    def _build_text_to_json_prompt(self, document_type, extracted_text):
        """
        Build prompt to convert text to JSON (Strategy 2 - Step 2)

        This prompt takes the plain text and asks AI to structure it as JSON.

        Args:
            document_type (str): '01' or '02'
            extracted_text (str): Plain text from Step 1

        Returns:
            str: JSON conversion prompt
        """
        # Get the structured prompt template (reuse existing JSON structure)
        structured_prompt = self._build_extraction_prompt(document_type)

        # Prepend instructions to work with text instead of PDF
        return f"""
You are given extracted text from a Vietnamese document. Convert this text into structured JSON.

EXTRACTED TEXT:
{extracted_text}

---

Now convert the above text into JSON following these exact specifications:

{structured_prompt}

IMPORTANT:
- Use the text provided above, NOT a PDF
- Follow the JSON structure EXACTLY as specified
- Preserve all Vietnamese text from the extracted text
- Convert all numeric values correctly
"""

    def _get_default_prompt_form_01(self):
        """
        Get default extraction prompt for Form 01 (Registration)

        Returns:
            str: Default Form 01 extraction prompt
        """
        return """
╔══════════════════════════════════════════════════════════════════════════════╗
║                    VIETNAMESE FORM 01 EXTRACTION SPECIALIST                  ║
║                     (Professional Document Auditor Mode)                     ║
╚══════════════════════════════════════════════════════════════════════════════╝

You are a PROFESSIONAL DOCUMENT AUDITOR specializing in Vietnamese regulatory forms.
Your role is to extract REAL DATA from Form 01 (Registration) while identifying and
IGNORING template/mockup/example data.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 PART I: DOCUMENT INTELLIGENCE - REAL DATA vs TEMPLATE/MOCKUP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ CRITICAL: Many companies submit PARTIALLY FILLED templates with mockup data.

✅ EXTRACT ONLY REAL DATA:
  1. Organization name that's SPECIFIC (not "Công ty ABC", "Tên công ty")
  2. Actual substance names (HFC-134a, R-410A, R-32), NOT examples
  3. Numbers that are HANDWRITTEN/TYPED by user (even if messy)
  4. Checkboxes CLEARLY marked (✓, X, filled box)
  5. Specific dates (15/03/2024), NOT placeholders (dd/mm/yyyy, __/__/____)

❌ IGNORE TEMPLATE/MOCKUP DATA:
  1. **Placeholder text**: "Tên doanh nghiệp", "Tên chất", "Ghi chú"
  2. **Example markers**: "Ví dụ:", "VD:", "Example:", "(mẫu)"
  3. **Instruction text**: "Ghi rõ...", "Điền vào...", "Nêu rõ..."
  4. **Template numbers**: Perfect sequences (1, 2, 3) or round numbers (100, 200, 300)
  5. **Empty template cells**: Unfilled rows with only borders

🔍 TEMPLATE DETECTION RULES:
  - **Repetition test**: Same substance 5+ times with perfect round numbers → TEMPLATE
  - **Number pattern**: All values are multiples of 100 → TEMPLATE
  - **Gray text/Italic**: Often indicates placeholder → SKIP
  - **Brackets/parentheses**: "(Tên chất)", "[Ghi rõ]" → TEMPLATE
  - **Cross-validation**: If organization name is template, ENTIRE form is likely template

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔧 PART II: HANDLING POOR QUALITY DOCUMENTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

For blurry, rotated, or messy documents:

1. **Context-based inference**:
   - Blurry substance name? → Check HS code column for clues
   - Unclear number? → Look at neighboring cells for patterns
   - Missing data? → Cross-reference with other sections

2. **Line wrap reconstruction** (CRITICAL):
   - "300.0" (line 1) + "00" (line 2) = 300000 (NOT 30000!)
   - Always concatenate multi-line cell content BEFORE parsing

3. **Handwritten ambiguity**:
   - "1" vs "7": Use unit context (1 ton vs 7 kg makes sense?)
   - "0" vs "6": Check if surrounding numbers follow pattern
   - When unclear: Mark as null, DON'T guess

4. **Bilingual forms**:
   - Vietnamese + English side-by-side
   - Don't confuse English section headers with checkmarks
   - Prioritize Vietnamese text for substance names

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📐 PART III: JSON OUTPUT STRUCTURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{
  "year": <integer>,
  "year_1": <integer - actual year from column header, e.g., 2023>,
  "year_2": <integer - actual year from column header, e.g., 2024>,
  "year_3": <integer - actual year from column header, e.g., 2025>,

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
  "contact_country_code": "<ISO 2-letter, e.g., VN>",
  "contact_state_code": "<Province code, e.g., HN, SG, BD>",

  "activity_field_codes": ["production", "import", "export", ...],

  "has_table_1_1": <boolean>,
  "has_table_1_2": <boolean>,
  "has_table_1_3": <boolean>,
  "has_table_1_4": <boolean>,

  "substance_usage": [
    {
      "is_title": <true for section headers, false for data>,
      "sequence": <incremental number>,
      "usage_type": "production|import|export",
      "substance_name": "<standardized name from official list>",
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

  "equipment_product": [...],
  "equipment_ownership": [...],
  "collection_recycling": [...]
}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔄 PART IV: EXTRACTION WORKFLOW (Follow this order)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STEP 1: DOCUMENT QUALITY ASSESSMENT
  → Scan entire document for template indicators
  → Check if organization name is real or placeholder
  → Identify which sections are filled vs empty template

STEP 2: ORGANIZATION INFORMATION
  → Extract company name, license, contact info
  → **Country code**: Use ISO 3166-1 (VN for Vietnam)
  → **State code**: Extract province (HN, SG, DN, BD...) from address end

STEP 3: YEAR EXTRACTION (Critical for multi-year data)
  → Look at Table 1.1 column headers for ACTUAL years
  → Example: "Năm 2023" → year_1=2023, "Năm 2024" → year_2=2024
  → If not shown: infer from main year field (year_1 = year-1, etc.)

STEP 4: ACTIVITY FIELD RECOGNITION
  → Check Section "2. Nội dung đăng ký" for checkboxes
  → ⚠️ CAREFUL: Don't confuse bilingual text with checkmarks
  → Only mark as checked if CLEAR visual indication (✓, X, filled)
  → Map to codes:
    * "Sản xuất chất..." → "production"
    * "Nhập khẩu chất..." → "import"
    * "Xuất khẩu chất..." → "export"
    * "Sản xuất thiết bị..." → "equipment_production"
    * "Nhập khẩu thiết bị..." → "equipment_import"
    * "Sở hữu máy điều hòa..." → "ac_ownership"
    * "Sở hữu thiết bị lạnh..." → "refrigeration_ownership"
    * "Thu gom, tái chế..." → "collection_recycling"

STEP 5: TABLE PRESENCE DETERMINATION
  → has_table_1_1 = true IF any("production", "import", "export") checked
  → has_table_1_2 = true IF any("equipment_production", "equipment_import") checked
  → has_table_1_3 = true IF any("ac_ownership", "refrigeration_ownership") checked
  → has_table_1_4 = true IF "collection_recycling" checked

STEP 6: TABLE EXTRACTION (ONLY extract checked tables)
  → For each table, apply REAL vs TEMPLATE filter
  → Extract ONLY rows with real data
  → Skip template rows with placeholder text

STEP 7: DATA VALIDATION & STANDARDIZATION
  → Substance names → Match to official list (see PART V below)
  → Numbers → Standardize format (see NUMBER RULES below)
  → Dates → Convert to YYYY-MM-DD
  → Province codes → Convert to ISO codes

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 PART V: TABLE STRUCTURE RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**TITLE ROW vs DATA ROW:**

✅ TITLE ROW (is_title=true):
  - MERGED CELLS spanning multiple columns
  - Contains section names: "Sản xuất chất được kiểm soát"
  - NO specific substance names or quantities
  - ALL numeric fields = null

❌ DATA ROW (is_title=false):
  - SEPARATE CELLS (not merged)
  - Contains actual substance names (HFC-134a, R-410A)
  - Has numeric values

**COMMON PARSING ERRORS TO AVOID:**

1. **Header/Data Confusion** (FORD case):
   - If "Điều hòa không khí" appears on SAME LINE as "FORD RANGER"
   - SPLIT into 2 rows: Title row + Data row

2. **Column Overflow** (BKRE, HOÀNG BÁCH cases):
   - "Nhập khẩu chất..." written in WRONG column (Substance Name column)
   - RECOGNIZE as descriptive text, NOT substance name
   - Don't push HS code into Substance Name field

3. **Duplicate Spillover** (HOÀNG BÁCH case):
   - Data from row N appearing in row N+1
   - CHECK for exact duplicates, keep only ONE instance

4. **Missing Sections** (Viễn Nam case):
   - Table completely missing → set has_table_X = false
   - Return empty array for that table

**CONDITIONAL EXTRACTION:**
  - ONLY include section titles for CHECKED activities
  - Example: If "production" NOT checked → DON'T create "Sản xuất chất..." title row
  - For Table 1.4: ALWAYS include all 4 sections (collection, reuse, recycle, disposal)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔢 PART VI: NUMBER FORMATTING RULES (CRITICAL)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Vietnamese documents use BOTH formats inconsistently:
  - European: "1.000,5" (dot=thousands, comma=decimal) → 1000.5
  - US: "1,000.5" (comma=thousands, dot=decimal) → 1000.5

**DETECTION STRATEGY:**
  1. Look for decimal patterns: "100,25" vs "100.25"
  2. If you see "X.XXX,X" → comma is decimal
  3. If you see "X,XXX.X" → dot is decimal

**LINE WRAP HANDLING** (⚠️ MOST CRITICAL BUG):
  - Numbers often wrap to next line in small cells
  - "300.0" (line 1) + "00" (line 2) = 300000 (NOT 30000!)
  - "180.0" (line 1) + "00" (line 2) = 180000 (NOT 18000!)
  - "500.0" (line 1) + "00" (line 2) = 500000 (NOT 50000!)
  - **Rule**: ALWAYS concatenate ALL parts before parsing

**FINAL CONVERSION:**
  1. Remove ALL thousands separators (both comma AND dot)
  2. Convert decimal separator to dot "."
  3. Return as float/int: 300000.5 or 300000

**NULL HANDLING:**
  - Empty cell → null (NOT 0, NOT "")
  - Missing data → null
  - 0 is a VALID value (different from missing!)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🧪 PART VII: SUBSTANCE NAME STANDARDIZATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

You have access to the OFFICIAL LIST of controlled substances (see context above).

**MATCHING STRATEGY:**
  1. Extract raw name from document
  2. Apply FUZZY MATCHING to official list:
     - "HFC134a" → "HFC-134a" (missing hyphen)
     - "R410A" → "R-410A" (missing hyphens)
     - "r-22" → "HCFC-22" (case + code-to-name)
  3. Return EXACT standardized name from official list
  4. If NO match: prefix with "[UNKNOWN] "

**HS CODE FALLBACK:**
  - If substance name is unclear/generic ("HFC" only)
  - AND HS code is provided
  - Extract HS code accurately - system will lookup substance
  - Common HS codes: 2903.39, 2903.41, 3824.78

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ PART VIII: OUTPUT REQUIREMENTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Return ONLY valid JSON (no markdown, no explanations)
2. Use null for missing values (NOT "None", NOT empty string "")
3. Preserve Vietnamese characters EXACTLY
4. Extract ONLY real data (skip all template/mockup rows)
5. Apply ALL formatting rules (numbers, dates, codes)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BEGIN EXTRACTION NOW.
"""

    def _get_default_prompt_form_02(self):
        """
        Get default extraction prompt for Form 02 (Report)

        Returns:
            str: Default Form 02 extraction prompt
        """
        return """
╔══════════════════════════════════════════════════════════════════════════════╗
║                    VIETNAMESE FORM 02 EXTRACTION SPECIALIST                  ║
║                     (Professional Document Auditor Mode)                     ║
╚══════════════════════════════════════════════════════════════════════════════╝

You are a PROFESSIONAL DOCUMENT AUDITOR specializing in Vietnamese regulatory forms.
Your role is to extract REAL DATA from Form 02 (Report) while identifying and
IGNORING template/mockup/example data.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 PART I: DOCUMENT INTELLIGENCE - REAL DATA vs TEMPLATE/MOCKUP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ CRITICAL: Many companies submit PARTIALLY FILLED templates with mockup data.

✅ EXTRACT ONLY REAL DATA:
  1. Organization name that's SPECIFIC (not "Công ty ABC", "Tên công ty")
  2. Actual substance names (HFC-134a, R-410A, R-32), NOT examples
  3. Numbers that are HANDWRITTEN/TYPED by user (even if messy)
  4. Specific dates (15/03/2024), NOT placeholders (dd/mm/yyyy, __/__/____)
  5. Country codes that are REAL (VN, CN, TH), NOT template "(Mã nước)"

❌ IGNORE TEMPLATE/MOCKUP DATA:
  1. **Placeholder text**: "Tên doanh nghiệp", "Tên chất", "Ghi chú"
  2. **Example markers**: "Ví dụ:", "VD:", "Example:", "(mẫu)"
  3. **Instruction text**: "Ghi rõ...", "Điền vào...", "Nêu rõ..."
  4. **Template numbers**: Perfect sequences (1, 2, 3) or round numbers (100, 200, 300)
  5. **Empty template cells**: Unfilled rows with only borders

🔍 TEMPLATE DETECTION RULES:
  - **Repetition test**: Same substance 5+ times with perfect round numbers → TEMPLATE
  - **Number pattern**: All values are multiples of 100 → TEMPLATE
  - **Gray text/Italic**: Often indicates placeholder → SKIP
  - **Brackets/parentheses**: "(Tên chất)", "[Ghi rõ]" → TEMPLATE
  - **Cross-validation**: If organization name is template, ENTIRE form is likely template

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔧 PART II: HANDLING POOR QUALITY DOCUMENTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

For blurry, rotated, or messy documents:

1. **Context-based inference**:
   - Blurry substance name? → Check HS code column for clues
   - Unclear number? → Look at neighboring cells for patterns
   - Missing data? → Cross-reference with other sections

2. **Line wrap reconstruction** (CRITICAL):
   - "300.0" (line 1) + "00" (line 2) = 300000 (NOT 30000!)
   - Always concatenate multi-line cell content BEFORE parsing
   - Table 2.1 is especially prone to this bug!

3. **Handwritten ambiguity**:
   - "1" vs "7": Use unit context (1 ton vs 7 kg makes sense?)
   - "0" vs "6": Check if surrounding numbers follow pattern
   - When unclear: Mark as null, DON'T guess

4. **Bilingual forms**:
   - Vietnamese + English side-by-side
   - Don't confuse English section headers with data
   - Prioritize Vietnamese text for substance names

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📐 PART III: JSON OUTPUT STRUCTURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Return a JSON object with this EXACT structure (all field names in English):

{
  "year": <integer>,
  "year_1": <integer - actual year for year_1 column, e.g., 2023>,
  "year_2": <integer - actual year for year_2 column, e.g., 2024>,
  "year_3": <integer - actual year for year_3 column, e.g., 2025>,
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
  "contact_country_code": "<ISO 2-letter country code, e.g., VN>",
  "contact_state_code": "<State/Province code for Vietnam, see list below>",

  "activity_field_codes": [<array of codes from section "b) Thông tin về lĩnh vực hoạt động sử dụng chất được kiểm soát">],

  "has_table_2_1": <boolean>,
  "has_table_2_2": <boolean>,
  "has_table_2_3": <boolean>,
  "has_table_2_4": <boolean>,

  "quota_usage": [
    {
      "is_title": <true for merged cell rows, false for data rows>,
      "sequence": <incremental number>,
      "usage_type": "<production|import|export>",
      "substance_name": "<string>",
      "hs_code": "<string>",
      "allocated_quota_kg": <float or null>,
      "allocated_quota_co2": <float or null>,
      "adjusted_quota_kg": <float or null>,
      "adjusted_quota_co2": <float or null>,
      "total_quota_kg": <float or null>,
      "total_quota_co2": <float or null>,
      "average_price": <float or null>,
      "country_code": "<ISO 2-letter country code, e.g., VN, US, CN, TH, JP>",
      "customs_declaration_number": "<string>",
      "next_year_quota_kg": <float or null>,
      "next_year_quota_co2": <float or null>
    }
  ],

  "equipment_product_report": [
    {
      "is_title": <true for merged cell rows, false for data rows>,
      "sequence": <incremental number>,
      "production_type": "<production|import>",
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
      "is_title": <true for merged cell rows, false for data rows>,
      "sequence": <incremental number>,
      "ownership_type": "<air_conditioner|refrigeration>",
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

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔄 PART IV: EXTRACTION WORKFLOW (Follow this order)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STEP 1: DOCUMENT QUALITY ASSESSMENT
  → Scan entire document for template indicators
  → Check if organization name is real or placeholder
  → Identify which sections are filled vs empty template

STEP 2: ORGANIZATION INFORMATION
  → Extract company name, license, contact info
  → **Country code**: Use ISO 3166-1 (VN for Vietnam)
  → **State code**: Extract province (HN, SG, DN, BD...) from address end

STEP 3: YEAR EXTRACTION (Critical for multi-year data)
  → Look at Table 2.1 column headers for ACTUAL years (if present)
  → Example: "Năm 2023" → year_1=2023, "Năm 2024" → year_2=2024
  → If not shown: infer from main year field (year_1 = year-1, etc.)

STEP 4: ACTIVITY FIELD RECOGNITION
  → Check Section "b) Thông tin về lĩnh vực hoạt động" for activity types
  → Map to codes:
    * "Sản xuất chất..." → "production"
    * "Nhập khẩu chất..." → "import"
    * "Xuất khẩu chất..." → "export"
    * "Sản xuất thiết bị..." → "equipment_production"
    * "Nhập khẩu thiết bị..." → "equipment_import"
    * "Sở hữu máy điều hòa..." → "ac_ownership"
    * "Sở hữu thiết bị lạnh..." → "refrigeration_ownership"
    * "Thu gom, tái chế..." → "collection_recycling"

STEP 5: TABLE PRESENCE DETERMINATION
  → has_table_2_1 = true IF any("production", "import", "export") exists
  → has_table_2_2 = true IF any("equipment_production", "equipment_import") exists
  → has_table_2_3 = true IF any("ac_ownership", "refrigeration_ownership") exists
  → has_table_2_4 = true IF "collection_recycling" exists

STEP 6: TABLE EXTRACTION (ONLY extract existing tables)
  → For each table, apply REAL vs TEMPLATE filter
  → Extract ONLY rows with real data
  → Skip template rows with placeholder text
  → For Table 2.4: NO title rows, extract substance data with all columns

STEP 7: DATA VALIDATION & STANDARDIZATION
  → Substance names → Match to official list (see PART VII)
  → Numbers → Standardize format (see PART VI)
  → Country codes → Convert Vietnamese names to ISO codes (see PART V)
  → Dates → Convert to YYYY-MM-DD

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 PART V: TABLE STRUCTURE RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**TITLE ROW vs DATA ROW:**

✅ TITLE ROW (is_title=true) - For Tables 2.1, 2.2, 2.3 ONLY:
  - MERGED CELLS spanning multiple columns
  - Contains section names: "Sản xuất chất được kiểm soát", "Nhập khẩu chất được kiểm soát"
  - NO specific substance names or quantities
  - ALL numeric fields = null

❌ DATA ROW (is_title=false):
  - SEPARATE CELLS (not merged)
  - Contains actual substance names, equipment models, quantities
  - Has numeric values

**TABLE 2.4 SPECIAL RULE:**
  - NO title rows at all
  - Extract ONLY substance data rows with all columns filled
  - Each row = one substance with collection/reuse/recycle/disposal data

**COUNTRY CODE EXTRACTION (Table 2.1 quota_usage):**
  ⚠️ Extract ONLY ISO 2-letter codes (VN, US, CN, TH, JP, KR, SG)
  - "Việt Nam" → "VN"
  - "Trung Quốc" → "CN"
  - "Hoa Kỳ", "Mỹ" → "US"
  - "Thái Lan" → "TH"
  - "Nhật Bản" → "JP"
  - Use UPPERCASE, return null if unclear

**CONDITIONAL EXTRACTION:**
  - Tables 2.1, 2.2, 2.3: ALWAYS include title rows for ALL sections
  - Table 2.4: NO title rows, just data
  - If table doesn't exist → set has_table_2_x = false, return empty array

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔢 PART VI: NUMBER FORMATTING RULES (CRITICAL)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Vietnamese documents use BOTH formats inconsistently:
  - European: "1.000,5" (dot=thousands, comma=decimal) → 1000.5
  - US: "1,000.5" (comma=thousands, dot=decimal) → 1000.5

**DETECTION STRATEGY:**
  1. Look for decimal patterns: "100,25" vs "100.25"
  2. If you see "X.XXX,X" → comma is decimal
  3. If you see "X,XXX.X" → dot is decimal

**LINE WRAP HANDLING** (⚠️ MOST CRITICAL BUG - ESPECIALLY IN TABLE 2.1):
  - Numbers often wrap to next line in small cells
  - "300.0" (line 1) + "00" (line 2) = 300000 (NOT 30000!)
  - "180.0" (line 1) + "00" (line 2) = 180000 (NOT 18000!)
  - "500.0" (line 1) + "00" (line 2) = 500000 (NOT 50000!)
  - "219.0" (line 1) + "00" (line 2) = 219000 (NOT 21900!)
  - **Rule**: ALWAYS concatenate ALL parts before parsing

**FINAL CONVERSION:**
  1. Remove ALL thousands separators (both comma AND dot)
  2. Convert decimal separator to dot "."
  3. Return as float/int: 300000.5 or 300000

**NULL HANDLING:**
  - Empty cell → null (NOT 0, NOT "")
  - Missing data → null
  - 0 is a VALID value (different from missing!)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🧪 PART VII: SUBSTANCE NAME STANDARDIZATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

You have access to the OFFICIAL LIST of controlled substances (see context above).

**MATCHING STRATEGY:**
  1. Extract raw name from document
  2. Apply FUZZY MATCHING to official list:
     - "HFC134a" → "HFC-134a" (missing hyphen)
     - "R410A" → "R-410A" (missing hyphens)
     - "r-22" → "HCFC-22" (case + code-to-name)
  3. Return EXACT standardized name from official list
  4. If NO match: prefix with "[UNKNOWN] "

**HS CODE FALLBACK:**
  - If substance name is unclear/generic ("HFC" only)
  - AND HS code is provided
  - Extract HS code accurately - system will lookup substance
  - Common HS codes: 2903.39, 2903.41, 3824.78

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ PART VIII: OUTPUT REQUIREMENTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Return ONLY valid JSON (no markdown, no explanations)
2. Use null for missing values (NOT "None", NOT empty string "")
3. Preserve Vietnamese characters EXACTLY
4. Extract ONLY real data (skip all template/mockup rows)
5. Apply ALL formatting rules (numbers, dates, codes)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BEGIN EXTRACTION NOW.
"""

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

    def _extract_pdf_to_text(self, client, pdf_binary, document_type, filename):
        """
        Strategy 2 - Step 1: Extract PDF content to plain text

        This is a simpler extraction that focuses on getting raw text data
        without worrying about JSON structure. Less likely to be truncated.

        Args:
            client: Gemini client instance
            pdf_binary (bytes): Binary PDF data
            document_type (str): '01' or '02'
            filename (str): Original filename for logging

        Returns:
            str: Plain text extracted from PDF

        Raises:
            ValueError: If extraction fails
        """
        import tempfile
        import os
        import time

        # Constants
        GEMINI_POLL_INTERVAL_SECONDS = 2
        GEMINI_MAX_POLL_RETRIES = 30

        # Build simple text extraction prompt
        prompt = self._build_text_extraction_prompt(document_type)

        tmp_file_path = None
        uploaded_file = None

        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                tmp_file.write(pdf_binary)
                tmp_file_path = tmp_file.name

            _logger.info(f"Created temp file for text extraction: {tmp_file_path}")

            # Upload file to Gemini
            uploaded_file = client.files.upload(file=tmp_file_path)
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

            # Build mega prompt context
            mega_context = self._build_mega_prompt_context()

            # Get Gemini model from config
            GEMINI_MODEL = self.env['ir.config_parameter'].sudo().get_param(
                'robotia_document_extractor.gemini_model',
                default='gemini-2.5-pro'
            )

            # Generate text content with mega context (using higher token limit for text)
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=mega_context + [uploaded_file, prompt],
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=65536,  # Max tokens for text extraction
                    response_mime_type='text/plain',  # Plain text output
                )
            )

            extracted_text = response.text.strip()
            _logger.info(f"Text extraction successful (length: {len(extracted_text)} chars)")

            return extracted_text

        except Exception as e:
            _logger.exception(f"Text extraction failed")
            raise ValueError(f"Text extraction failed: {type(e).__name__}: {str(e)}")

        finally:
            # Cleanup temporary file
            if tmp_file_path and os.path.exists(tmp_file_path):
                try:
                    os.unlink(tmp_file_path)
                    _logger.info(f"Cleaned up temp file: {tmp_file_path}")
                except Exception as e:
                    _logger.warning(f"Failed to cleanup temp file: {e}")

            # Cleanup Gemini uploaded file
            if uploaded_file:
                try:
                    client.files.delete(name=uploaded_file.name)
                    _logger.info(f"Deleted Gemini file: {uploaded_file.name}")
                except Exception as e:
                    _logger.warning(f"Failed to delete Gemini file: {e}")

    def _convert_text_to_json(self, client, extracted_text, document_type):
        """
        Strategy 2 - Step 2: Convert plain text to structured JSON

        Takes the plain text from Step 1 and converts it to structured JSON.
        This is lighter weight than direct PDF→JSON extraction.

        Args:
            client: Gemini client instance
            extracted_text (str): Plain text from Step 1
            document_type (str): '01' or '02'

        Returns:
            dict: Structured data

        Raises:
            ValueError: If conversion fails
        """
        # Build JSON conversion prompt
        prompt = self._build_text_to_json_prompt(document_type, extracted_text)

        # Get max output tokens from config
        GEMINI_MAX_TOKENS = int(
            self.env['ir.config_parameter'].sudo().get_param(
                'robotia_document_extractor.gemini_max_output_tokens',
                default='65536'
            )
        )

        # Get Gemini model from config
        GEMINI_MODEL = self.env['ir.config_parameter'].sudo().get_param(
            'robotia_document_extractor.gemini_model',
            default='gemini-2.5-pro'
        )

        GEMINI_MAX_RETRIES = 3

        extracted_json = None
        last_error = None

        # Build mega prompt context
        mega_context = self._build_mega_prompt_context()

        for retry_attempt in range(GEMINI_MAX_RETRIES):
            try:
                _logger.info(f"JSON conversion attempt {retry_attempt + 1}/{GEMINI_MAX_RETRIES}")

                # Generate JSON from text with mega context (no file upload needed)
                response = client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=mega_context + [prompt],
                    config=types.GenerateContentConfig(
                        temperature=0.1,
                        max_output_tokens=GEMINI_MAX_TOKENS,
                        response_mime_type='application/json',
                        top_p=0.8,
                        top_k=40
                    )
                )

                extracted_json = response.text

                # Validate JSON
                try:
                    parsed_data = self._parse_json_response(extracted_json)
                    _logger.info(f"JSON conversion successful on attempt {retry_attempt + 1}")

                    # Clean and return
                    cleaned_data = self._clean_extracted_data(parsed_data, document_type)
                    return cleaned_data

                except json.JSONDecodeError:
                    raise

            except json.JSONDecodeError as e:
                last_error = e
                _logger.warning(f"Attempt {retry_attempt + 1} returned incomplete JSON: {str(e)}")
                if retry_attempt < GEMINI_MAX_RETRIES - 1:
                    wait_time = 2 ** retry_attempt
                    _logger.info(f"Retrying in {wait_time}s...")
                    import time
                    time.sleep(wait_time)
                else:
                    _logger.error("All JSON conversion attempts failed")

            except Exception as e:
                last_error = e
                _logger.warning(f"Attempt {retry_attempt + 1} failed: {type(e).__name__}: {str(e)}")
                if retry_attempt < GEMINI_MAX_RETRIES - 1:
                    wait_time = 2 ** retry_attempt
                    import time
                    time.sleep(wait_time)
                else:
                    raise

        # All retries failed
        raise ValueError(f"JSON conversion failed after {GEMINI_MAX_RETRIES} attempts: {last_error}")

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
                'quota_usage': data.get('quota_usage', []),
                'equipment_product_report': data.get('equipment_product_report', []),
                'equipment_ownership_report': data.get('equipment_ownership_report', []),
                'collection_recycling_report': data.get('collection_recycling_report', []),
            })

        _logger.info(f"Data cleaned successfully (Type: {document_type})")
        return cleaned
