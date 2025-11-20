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
            default='gemini-2.0-flash-exp'
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
📋 PART I: DOCUMENT INTELLIGENCE - IDENTIFYING REAL vs TEMPLATE DATA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ CRITICAL: Companies often use pre-filled templates with example data. You MUST distinguish:

✅ REAL DATA - Extract these:
  1. Organization info that's SPECIFIC (not "Công ty ABC", "Tên công ty", etc.)
  2. Tables with ACTUAL substance names (HFC-134a, R-410A, etc.), NOT generic examples
  3. Numbers that appear HANDWRITTEN or TYPED by user (even if messy)
  4. Checkboxes that are CLEARLY marked (✓, X, filled)
  5. Dates that are SPECIFIC (15/03/2024, not "dd/mm/yyyy" or "__/__/____")

❌ TEMPLATE/MOCKUP DATA - Skip these:
  1. Placeholder text: "Tên doanh nghiệp", "Tên chất", "Ghi chú", etc.
  2. Example rows: "Ví dụ: HFC-134a", "Example: 100 kg", etc.
  3. Template numbers: Sequential (1, 2, 3...), rounded (100, 200, 300...), or "XXX"
  4. Empty cells with light gray borders (unfilled template)
  5. Instruction text: "Ghi rõ...", "Điền vào...", "Fill in...", etc.

🔍 HOW TO IDENTIFY TEMPLATE DATA:
  - Look for REPETITIVE patterns (same substance appearing 10 times with perfect numbers)
  - Check if numbers are TOO PERFECT (all round numbers: 100, 200, 300...)
  - Identify PLACEHOLDER formatting (gray text, italic, brackets)
  - Detect INSTRUCTIONAL language ("ghi rõ", "nêu rõ", "điền vào")
  - Spot EXAMPLE markers ("VD:", "Ví dụ:", "Example:")

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔧 PART II: HANDLING POOR QUALITY DOCUMENTS (Blurry, Rotated, Messy)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

When encountering low-quality scans:

1. **Blurry text**: Use CONTEXT to infer
   - If substance name is unclear, check HS code column
   - If number is blurry, check neighboring cells for pattern
   - Cross-reference with other tables in same document

2. **Partial visibility**: Reconstruct from visible parts
   - "HFC-13__" + context → likely "HFC-134a"
   - "300.__0" across lines → "300.000" (see line wrap rules below)

3. **Handwritten numbers**: Be EXTRA careful
   - "1" vs "7", "0" vs "6", "3" vs "8" - use context
   - If handwritten "03" could be "0.3" or "3", analyze units

4. **Mixed quality**: Prioritize clearer sections
   - If header is blurry but data is clear, infer header from data
   - If data is unclear, mark as null (don't guess)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📐 PART III: JSON OUTPUT STRUCTURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Return ONLY valid JSON with this EXACT structure:

⚠️⚠️⚠️ CRITICAL TABLE STRUCTURE RULE ⚠️⚠️⚠️

**HOW TO IDENTIFY TITLE vs DATA ROWS:**

✅ TITLE ROW = Row with MERGED CELLS spanning across multiple columns
   - Contains section names (often bold): "Sản xuất chất được kiểm soát", "Nhập khẩu chất được kiểm soát", etc.
   - Does NOT contain specific substance/equipment names or quantity data
   - Mark as: is_title=true, all numeric fields=null

❌ DATA ROW = Row with SEPARATE CELLS (not merged)
   - Contains specific substance names, equipment models, or actual data values
   - Mark as: is_title=false, fill in actual data

⚠️ COMMON TABLE PARSING ERRORS TO AVOID:

1. **Header vs Data Confusion (FORD case)**
   - Equipment type headers ("Điều hòa không khí...") may appear on same line as first data row
   - SOLUTION: Create TWO separate rows - one title row + one data row
   - Example: "Điều hòa không khí | FORD RANGER..." → Split into title row + data row

2. **Column Overflow (BKRE, HOÀNG BÁCH cases)**
   - Companies may write descriptions in wrong columns
   - "Nhập khẩu chất..." written in Substance Name column
   - SOLUTION: Recognize these as descriptive text, not data values
   - Don't push HS code to Substance Name column

3. **Duplicate Data (HOÀNG BÁCH case)**
   - Data from one row may spill into next row
   - SOLUTION: Each row should have unique data, check for exact duplicates

4. **Missing Sections (Viễn Nam case)**
   - Some tables may be completely missing
   - SOLUTION: Set has_table_X = false, return empty array for that section

Return a JSON object with this structure (all field names in English):

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

STEP 0: EXTRACT ORGANIZATION INFORMATION

   When extracting organization information, pay special attention to:

   **contact_country_code field:**
   - Use ISO 3166-1 alpha-2 country codes (2 letters, UPPERCASE)
   - For Vietnam: "VN"
   - Examples: "US", "CN", "TH", "JP", "KR", "SG"

   **contact_state_code field:**
   - Use ISO 3166-2 subdivision codes for provinces/states
   - For Vietnam, extract the province/city name from contact_address and convert to standard code
   - Common examples:
     * Hà Nội → "HN"
     * TP. Hồ Chí Minh, Sài Gòn → "SG"
     * Đà Nẵng → "DN"
     * Bình Dương → "BD"
     * Đồng Nai → "DO"
     * Hải Phòng → "HP"
     * Cần Thơ → "CT"
   - Use your knowledge to convert Vietnamese province names to their standard ISO codes
   - Province name usually appears at the end of address after district/ward
   - If province is unclear, use null

STEP 1: EXTRACT YEAR INFORMATION

   ⚠️ CRITICAL: Look at Table 1.1 column headers to identify the actual years:

   The table has columns like "Năm trước (year_1)", "Năm hiện tại (year_2)", "Năm sau (year_3)"

   - Find the ACTUAL YEAR NUMBER in each column header (e.g., "2023", "2024", "2025")
   - Extract these as integer values:
     * year_1: The year shown in the first quantity column (past year)
     * year_2: The year shown in the second quantity column (current year)
     * year_3: The year shown in the third quantity column (next year)

   Example:
   - If headers show "Năm 2023", "Năm 2024", "Năm 2025"
   - Then: year_1 = 2023, year_2 = 2024, year_3 = 2025

   If year values are not explicitly shown in table headers, infer from:
   - The "year" field (main reporting year, typically equals year_2)
   - year_1 = year - 1, year_2 = year, year_3 = year + 1

STEP 2: EXTRACT ACTIVITY FIELD CODES (Section "2. Nội dung đăng ký")

   ⚠️ CRITICAL: CAREFUL CHECKBOX RECOGNITION ⚠️

   Look for checkboxes (☑ or ☐) in section "2.a) Lĩnh vực sử dụng chất được kiểm soát"

   **Common Recognition Issues to Avoid:**
   1. Bilingual forms: Don't confuse English text with checkboxes
   2. Faint marks: Some checkmarks may be light or unclear
   3. Table borders: Don't mistake table lines for checkmarks
   4. Multiple languages: Vietnamese + English side-by-side may cause confusion

   **How to identify checked boxes:**
   - Look for explicit check marks (✓, ✗, X, filled box)
   - Compare with unchecked boxes in the same section
   - ONLY mark as checked if there's clear visual indication
   - When in doubt, check if corresponding table exists in the document

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

STEP 3: DETERMINE TABLE PRESENCE based on activity fields

   **Activity Fields → Tables Mapping:**

   has_table_1_1 = true IF any of these is checked:
     - "production" OR "import" OR "export"

   has_table_1_2 = true IF any of these is checked:
     - "equipment_production" OR "equipment_import"

   has_table_1_3 = true IF any of these is checked:
     - "ac_ownership" OR "refrigeration_ownership"

   has_table_1_4 = true IF this is checked:
     - "collection_recycling"

STEP 4: CONDITIONAL EXTRACTION - Extract ONLY relevant sub-sections

   For Table 1.1 (Bảng 1.1: Substance Usage):
   - IF "production" checked → include title + data rows
   - IF "import" checked → include title + data rows
   - IF "export" checked → include title + data rows
   - DO NOT create title rows for unchecked activities

   For Table 1.2 (Bảng 1.2: Equipment/Product):
   - IF "equipment_production" checked → include title + data rows
   - IF "equipment_import" checked → include title + data rows

   For Table 1.3 (Bảng 1.3: Equipment Ownership):
   - IF "ac_ownership" checked → include title + data rows
   - IF "refrigeration_ownership" checked → include title + data rows

   For Table 1.4 (Bảng 1.4: Collection & Recycling):
   - ALWAYS has 4 sub-sections if table exists
   - Include all 4 title rows + their data rows

STEP 5: EXTRACT TABLE DATA WITH FIXED TITLES

   ⚠️⚠️⚠️ CRITICAL: USE EXACT TITLE TEXT FROM TEMPLATE ⚠️⚠️⚠️

   For Table 1.1 (Substance Usage) - Include only checked sections:
   [
     // IF "production" is checked:
     {"is_title": true, "sequence": 1, "usage_type": "production", "substance_name": "Sản xuất chất được kiểm soát",
      "year_1_quantity_kg": null, "year_1_quantity_co2": null, ...all numeric fields: null},
     ...data rows for production with is_title=false, usage_type="production", sequence=2,3,4...

     // IF "import" is checked:
     {"is_title": true, "sequence": X, "usage_type": "import", "substance_name": "Nhập khẩu chất được kiểm soát",
      "year_1_quantity_kg": null, ...all numeric fields: null},
     ...data rows for import with is_title=false, usage_type="import"...

     // IF "export" is checked:
     {"is_title": true, "sequence": Y, "usage_type": "export", "substance_name": "Xuất khẩu chất được kiểm soát",
      "year_1_quantity_kg": null, ...all numeric fields: null},
     ...data rows for export with is_title=false, usage_type="export"...
   ]

   For Table 1.2 (Equipment/Product) - Include only checked sections:
   [
     // IF "equipment_production" is checked:
     {"is_title": true, "sequence": 1, "product_type": "Sản xuất thiết bị, sản phẩm có chứa hoặc sản xuất từ chất được kiểm soát",
      "hs_code": null, "capacity": null, "quantity": null, ...all other fields: null},
     ...data rows for production with is_title=false...

     // IF "equipment_import" is checked:
     {"is_title": true, "sequence": X, "product_type": "Nhập khẩu thiết bị, sản phẩm có chứa hoặc sản xuất từ chất được kiểm soát",
      "hs_code": null, ...all fields: null},
     ...data rows for import with is_title=false...
   ]

   For Table 1.3 (Equipment Ownership) - Include only checked sections:
   [
     // IF "ac_ownership" is checked:
     {"is_title": true, "sequence": 1, "equipment_type": "Máy điều hòa không khí có năng suất lạnh danh định lớn hơn 26,5 kW (90.000 BTU/h) và có tổng năng suất lạnh danh định của các thiết bị lớn hơn 586 kW (2.000.000 BTU/h)",
      "start_year": null, "capacity": null, "equipment_quantity": null, ...all other fields: null},
     ...data rows for air conditioner with is_title=false...

     // IF "refrigeration_ownership" is checked:
     {"is_title": true, "sequence": X, "equipment_type": "Thiết bị lạnh công nghiệp có công suất điện lớn hơn 40 kW",
      "start_year": null, ...all fields: null},
     ...data rows for refrigeration with is_title=false...
   ]

   For Table 1.4 (Collection & Recycling) - ALWAYS include all 4 sections:
   [
     {"is_title": true, "sequence": 1, "activity_type": "collection", "substance_name": "Thu gom chất được kiểm soát",
      "quantity_kg": null, "quantity_co2": null},
     ...data rows for collection with is_title=false, activity_type="collection"...

     {"is_title": true, "sequence": X, "activity_type": "reuse", "substance_name": "Tái sử dụng chất được kiểm soát sau thu gom",
      "quantity_kg": null, "quantity_co2": null},
     ...data rows for reuse with is_title=false, activity_type="reuse"...

     {"is_title": true, "sequence": Y, "activity_type": "recycle", "substance_name": "Tái chế chất sau thu gom",
      "quantity_kg": null, "quantity_co2": null},
     ...data rows for recycle with is_title=false, activity_type="recycle"...

     {"is_title": true, "sequence": Z, "activity_type": "disposal", "substance_name": "Xử lý chất được kiểm soát",
      "quantity_kg": null, "quantity_co2": null},
     ...data rows for disposal with is_title=false, activity_type="disposal"...
   ]

   - Use sequential numbering for "sequence" field
   - Title rows: ALL numeric/data fields MUST be null
   - Data rows: Fill actual values from PDF

STEP 6: DATA CONVERSION - CRITICAL NUMBER FORMATTING RULES

   ⚠️⚠️⚠️ VIETNAMESE NUMBER FORMAT STANDARDIZATION ⚠️⚠️⚠️

   Vietnamese documents use BOTH formats inconsistently:
   - Format 1: "1.000,5" (European) → 1000.5 (dot for thousands, comma for decimal)
   - Format 2: "1,000.5" (US) → 1000.5 (comma for thousands, dot for decimal)

   **CRITICAL RULES FOR NUMBER EXTRACTION:**

   1. **Identify the decimal separator context:**
      - If you see patterns like "1.000,5" or "100,25" → comma is decimal separator
      - If you see patterns like "1,000.5" or "100.25" → dot is decimal separator

   2. **Common patterns to recognize:**
      - "300.000" or "300,000" → 300000 (no decimal part, thousands separator)
      - "300.000,5" → 300000.5 (European format)
      - "300,000.5" → 300000.5 (US format)
      - "0,3" or "0.3" → 0.3 (decimal number)
      - "03 kg" misread as "0,3 kg" → should be 3.0 (watch for OCR errors)

   3. **LINE WRAP HANDLING - CRITICAL BUG FIX:**
      - When numbers wrap to next line, DO NOT drop trailing zeros!
      - Example: "300.0" on line 1 + "00" on line 2 = 300000 (NOT 30000)
      - Example: "180.0" on line 1 + "00" on line 2 = 180000 (NOT 18000)
      - Look for partial numbers at line breaks and reconstruct the full number
      - If cell content spans multiple lines, concatenate before parsing

   4. **Currency mixing (VND vs USD):**
      - Vietnamese Dong (VND): Usually large numbers (millions/billions)
      - US Dollar (USD): Usually smaller numbers
      - Check context and units to determine which currency

   5. **Final conversion:**
      - Remove ALL thousand separators (both comma and dot)
      - Convert decimal separator to dot "."
      - Return as float/int (e.g., 300000.5 or 300000)

   6. **Use null for empty/missing values:**
      - NEVER use empty string ""
      - NEVER use 0 for missing data (0 is a valid value)
      - Use null for missing/empty cells

   7. **Preserve Vietnamese text EXACTLY:**
      - For names, addresses, text fields → keep original Vietnamese characters

STEP 7: OUTPUT FORMAT

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

CRITICAL INSTRUCTIONS:

STEP 0: EXTRACT ORGANIZATION INFORMATION

   When extracting organization information, pay special attention to:

   **contact_country_code field:**
   - Use ISO 3166-1 alpha-2 country codes (2 letters, UPPERCASE)
   - For Vietnam: "VN"
   - Examples: "US", "CN", "TH", "JP", "KR", "SG"

   **contact_state_code field:**
   - Use ISO 3166-2 subdivision codes for provinces/states
   - For Vietnam, extract the province/city name from contact_address and convert to standard code
   - Common examples:
     * Hà Nội → "HN"
     * TP. Hồ Chí Minh, Sài Gòn → "SG"
     * Đà Nẵng → "DN"
     * Bình Dương → "BD"
     * Đồng Nai → "DO"
     * Hải Phòng → "HP"
     * Cần Thơ → "CT"
   - Use your knowledge to convert Vietnamese province names to their standard ISO codes
   - Province name usually appears at the end of address after district/ward
   - If province is unclear, use null

STEP 1: EXTRACT YEAR INFORMATION

   ⚠️ CRITICAL: Look at Table 2.1 column headers to identify the actual years:

   The table may have year-specific columns in quota usage or other tables.

   - Find the ACTUAL YEAR NUMBER in column headers if present
   - Extract these as integer values:
     * year_1: The year shown in the first year column (past year)
     * year_2: The year shown in the second year column (current year)
     * year_3: The year shown in the third year column (next year)

   Example:
   - If headers show "Năm 2023", "Năm 2024", "Năm 2025"
   - Then: year_1 = 2023, year_2 = 2024, year_3 = 2025

   If year values are not explicitly shown in table headers, infer from:
   - The "year" field (main reporting year, typically equals year_2)
   - year_1 = year - 1, year_2 = year, year_3 = year + 1

STEP 2: EXTRACT ACTIVITY FIELD CODES from section "b) Thông tin về lĩnh vực hoạt động sử dụng chất được kiểm soát"
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

STEP 3: DETERMINE TABLE PRESENCE based on activity fields

   **Activity Fields → Tables Mapping:**

   has_table_2_1 = true IF any of these is checked:
     - "production" OR "import" OR "export"

   has_table_2_2 = true IF any of these is checked:
     - "equipment_production" OR "equipment_import"

   has_table_2_3 = true IF any of these is checked:
     - "ac_ownership" OR "refrigeration_ownership"

   has_table_2_4 = true IF this is checked:
     - "collection_recycling"

STEP 3: CONDITIONAL EXTRACTION - Extract ONLY relevant tables

   For Table 2.1 (Bảng 2.1: Quota Usage):
   - Extract ONLY if has_table_2_1 = true
   - Extract ALL rows for production, import, export with quota information

   For Table 2.2 (Bảng 2.2: Equipment/Product Report):
   - Extract ONLY if has_table_2_2 = true
   - Extract ALL equipment/product rows

   For Table 2.3 (Bảng 2.3: Equipment Ownership Report):
   - Extract ONLY if has_table_2_3 = true
   - Extract ALL equipment ownership rows

   For Table 2.4 (Bảng 2.4: Collection & Recycling Report):
   - Extract ONLY if has_table_2_4 = true
   - Extract ALL substance rows with collection, reuse, recycle, disposal data

STEP 4: EXTRACT TABLE DATA WITH FIXED TITLES

   ⚠️⚠️⚠️ CRITICAL: ALWAYS INCLUDE TITLE ROWS FOR TABLES 2.1, 2.2, 2.3 ⚠️⚠️⚠️

   For Table 2.1 (Quota Usage Report) - ALWAYS include 3 title rows:
   [
     {"is_title": true, "sequence": 1, "usage_type": "production", "substance_name": "Sản xuất chất được kiểm soát",
      "hs_code": null, "allocated_quota_kg": null, ...all other numeric fields: null},
     ...data rows for production with is_title=false, usage_type="production", sequence=2,3,4...
     {"is_title": true, "sequence": X, "usage_type": "import", "substance_name": "Nhập khẩu chất được kiểm soát",
      "hs_code": null, ...all numeric fields: null},
     ...data rows for import with is_title=false, usage_type="import"...
     {"is_title": true, "sequence": Y, "usage_type": "export", "substance_name": "Xuất khẩu chất được kiểm soát",
      "hs_code": null, ...all numeric fields: null},
     ...data rows for export with is_title=false, usage_type="export"...
   ]

   For Table 2.2 (Equipment/Product Report) - ALWAYS include 2 title rows:
   [
     {"is_title": true, "sequence": 1, "production_type": "production",
      "product_type": "Sản xuất thiết bị, sản phẩm có chứa hoặc sản xuất từ chất được kiểm soát",
      "hs_code": null, "capacity": null, ...all other fields: null},
     ...data rows for production with is_title=false, production_type="production"...
     {"is_title": true, "sequence": X, "production_type": "import",
      "product_type": "Nhập khẩu thiết bị, sản phẩm có chứa hoặc sản xuất từ chất được kiểm soát",
      "hs_code": null, ...all fields: null},
     ...data rows for import with is_title=false, production_type="import"...
   ]

   For Table 2.3 (Equipment Ownership Report) - ALWAYS include 2 title rows:
   [
     {"is_title": true, "sequence": 1, "ownership_type": "air_conditioner",
      "equipment_type": "Máy điều hòa không khí có năng suất lạnh danh định lớn hơn 26,5 kW (90.000 BTU/h) và có tổng năng suất lạnh danh định của các thiết bị lớn hơn 586 kW (2.000.000 BTU/h)",
      "equipment_quantity": null, "substance_name": null, ...all other fields: null},
     ...data rows for air conditioner with is_title=false, ownership_type="air_conditioner"...
     {"is_title": true, "sequence": X, "ownership_type": "refrigeration",
      "equipment_type": "Thiết bị lạnh công nghiệp có công suất điện lớn hơn 40 kW",
      "equipment_quantity": null, ...all fields: null},
     ...data rows for refrigeration with is_title=false, ownership_type="refrigeration"...
   ]

   For Table 2.4 (Collection & Recycling Report) - NO title rows, just substance data rows with all columns filled

   - For each table that exists (has_table_2_x = true), extract ALL rows completely
   - If table does not exist (has_table_2_x = false), return empty array for that table

STEP 5: COUNTRY CODE EXTRACTION (for quota_usage table)
   ⚠️⚠️⚠️ CRITICAL: Extract ISO 2-letter country code, NOT full location name ⚠️⚠️⚠️

   For the field "country_code" in quota_usage (Table 2.1):
   - Extract ONLY the ISO 2-letter country code (e.g., "VN", "US", "CN", "TH", "JP", "KR", "SG")
   - Common country codes:
     * "VN" - Vietnam (Việt Nam)
     * "US" - United States (Hoa Kỳ, Mỹ)
     * "CN" - China (Trung Quốc)
     * "TH" - Thailand (Thái Lan)
     * "JP" - Japan (Nhật Bản)
     * "KR" - South Korea (Hàn Quốc)
     * "SG" - Singapore
     * "MY" - Malaysia (Ma-lai-xi-a)
     * "ID" - Indonesia
     * "IN" - India (Ấn Độ)
     * "DE" - Germany (Đức)
     * "FR" - France (Pháp)
     * "GB" - United Kingdom (Anh)

   - If you see Vietnamese country names, convert to ISO code:
     * "Việt Nam" → "VN"
     * "Trung Quốc" → "CN"
     * "Hoa Kỳ", "Mỹ" → "US"
     * "Thái Lan" → "TH"
     * "Nhật Bản" → "JP"

   - If country code is not clear or not found, use null
   - Use UPPERCASE for country codes (e.g., "VN" not "vn")

STEP 6: DATA FORMATTING - CRITICAL NUMBER FORMATTING RULES

   ⚠️⚠️⚠️ VIETNAMESE NUMBER FORMAT STANDARDIZATION ⚠️⚠️⚠️

   Vietnamese documents use BOTH formats inconsistently:
   - Format 1: "1.000,5" (European) → 1000.5 (dot for thousands, comma for decimal)
   - Format 2: "1,000.5" (US) → 1000.5 (comma for thousands, dot for decimal)

   **CRITICAL RULES FOR NUMBER EXTRACTION:**

   1. **Identify the decimal separator context:**
      - If you see patterns like "1.000,5" or "100,25" → comma is decimal separator
      - If you see patterns like "1,000.5" or "100.25" → dot is decimal separator

   2. **Common patterns to recognize:**
      - "300.000" or "300,000" → 300000 (no decimal part, thousands separator)
      - "300.000,5" → 300000.5 (European format)
      - "300,000.5" → 300000.5 (US format)
      - "0,3" or "0.3" → 0.3 (decimal number)

   3. **LINE WRAP HANDLING - CRITICAL BUG FIX:**
      ⚠️ THIS IS THE MOST CRITICAL BUG TO FIX ⚠️
      - When numbers wrap to next line, DO NOT drop trailing zeros!
      - Example: "300.0" on line 1 + "00" on line 2 = 300000 (NOT 30000)
      - Example: "180.0" on line 1 + "00" on line 2 = 180000 (NOT 18000)
      - Example: "500.0" on line 1 + "00" on line 2 = 500000 (NOT 50000)
      - Example: "219.0" on line 1 + "00" on line 2 = 219000 (NOT 21900)
      - Look for partial numbers at line breaks and reconstruct the full number
      - If cell content spans multiple lines, concatenate ALL parts before parsing
      - Pay special attention to Table 2.1 where this bug commonly occurs

   4. **Currency mixing (VND vs USD):**
      - Vietnamese Dong (VND): Usually large numbers (millions/billions)
      - US Dollar (USD): Usually smaller numbers
      - Check context and units to determine which currency

   5. **Final conversion:**
      - Remove ALL thousand separators (both comma and dot)
      - Convert decimal separator to dot "."
      - Return as float/int (e.g., 300000.5 or 300000)

   6. **Use null for empty/missing values:**
      - NEVER use empty string ""
      - NEVER use 0 for missing data (0 is a valid value)
      - Use null for missing/empty cells

   7. **Preserve Vietnamese text EXACTLY:**
      - For names, addresses, text fields → keep original Vietnamese characters

   8. **Table 2.4 special handling:**
      - Complex structure with multiple columns per substance
      - Read each column carefully and map to correct field

STEP 7: OUTPUT FORMAT
   - Return ONLY valid JSON, no explanations or markdown formatting
   - Ensure all has_table_2_x fields are set correctly based on activity fields
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
                default='gemini-2.0-flash-exp'
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
            default='gemini-2.0-flash-exp'
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
