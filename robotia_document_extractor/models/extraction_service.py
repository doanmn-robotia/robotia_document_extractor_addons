# -*- coding: utf-8 -*-

from odoo import models, api
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

# Import prompt modules
from odoo.addons.robotia_document_extractor.prompts import context_prompts, strategy_prompts

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

    def extract_pdf(self, pdf_binary, document_type, filename):
        """
        Extract structured data from PDF using configurable extraction strategy

        Available Strategies (configured in Settings):
        - ai_native: 100% AI (Gemini processes PDF directly)
        - text_extract: Text Extraction + AI (PyMuPDF extracts text, then AI structures)

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
            return self._extract_with_ai_native(client, pdf_binary, document_type, filename)

        elif strategy == 'text_extract':
            # Strategy 2: Text Extract + AI (PyMuPDF → AI)
            return self._extract_with_text_extract(client, pdf_binary, document_type, filename)

        else:
            _logger.warning(f"Unknown strategy '{strategy}', falling back to ai_native")
            return self._extract_with_ai_native(client, pdf_binary, document_type, filename)

    def _extract_with_ai_native(self, client, pdf_binary, document_type, filename):
        """
        Strategy: 100% AI (Gemini processes PDF directly)

        Primary method with automatic fallback to 2-step if needed.
        """
        # Try direct PDF → JSON extraction
        try:
            _logger.info("=" * 70)
            _logger.info("AI NATIVE: Direct PDF → JSON extraction")
            _logger.info("=" * 70)
            extracted_data = self._extract_direct_pdf_to_json(client, pdf_binary, document_type, filename)
            _logger.info("✓ AI Native succeeded")
            return extracted_data

        except Exception as e:
            _logger.warning("✗ Direct extraction failed")
            _logger.warning(f"Error: {type(e).__name__}: {str(e)}")

            # Check if fallback is allowed
            ICP = self.env['ir.config_parameter'].sudo()
            allow_fallback = ICP.get_param('robotia_document_extractor.gemini_allow_fallback', default='True')
            allow_fallback = allow_fallback.lower() in ('true', '1', 'yes')

            if not allow_fallback:
                _logger.error("✗ Fallback disabled - failing immediately")
                raise ValueError(f"Direct extraction failed and fallback is disabled. Error: {str(e)}")

            _logger.info("→ Fallback enabled, trying 2-step extraction...")

            # Fallback: 2-step extraction (PDF → Text → JSON) using Gemini
            try:
                _logger.info("=" * 70)
                _logger.info("FALLBACK: 2-Step extraction (Gemini PDF → Text → JSON)")
                _logger.info("=" * 70)

                extracted_text = self._extract_pdf_to_text(client, pdf_binary, document_type, filename)
                _logger.info(f"✓ Step 1 complete - Extracted {len(extracted_text)} chars")

                extracted_data = self._convert_text_to_json(client, extracted_text, document_type)
                _logger.info("✓ Step 2 complete - JSON conversion successful")

                _logger.info("✓ Fallback succeeded")
                return extracted_data

            except Exception as e2:
                _logger.error("✗ All AI Native strategies failed")
                raise ValueError(f"AI Native extraction failed. Error: {str(e2)}")

    def _extract_with_text_extract(self, client, pdf_binary, document_type, filename):
        """
        Strategy: Text Extract + AI (PyMuPDF → Gemini)

        Extracts text using PyMuPDF, then structures with AI.
        Falls back to AI Native if PyMuPDF fails.
        """
        try:
            _logger.info("=" * 70)
            _logger.info("TEXT EXTRACT: PyMuPDF → AI structuring")
            _logger.info("=" * 70)

            # Step 1: Extract text using PyMuPDF
            _logger.info("Step 1/2: Extracting text with PyMuPDF...")
            extracted_text = self._extract_pdf_to_text_pymupdf(pdf_binary, filename)
            _logger.info(f"✓ Step 1 complete - Extracted {len(extracted_text)} chars")

            # Check if extraction produced meaningful text
            if len(extracted_text.strip()) < 100:
                _logger.warning("PyMuPDF produced too little text, falling back to AI Native")
                return self._extract_with_ai_native(client, pdf_binary, document_type, filename)

            # Step 2: Structure with AI
            _logger.info("Step 2/2: Structuring with AI...")
            extracted_data = self._convert_text_to_json(client, extracted_text, document_type)
            _logger.info("✓ Step 2 complete - JSON conversion successful")

            _logger.info("✓ Text Extract strategy succeeded")
            return extracted_data

        except Exception as e:
            _logger.warning(f"✗ Text Extract strategy failed: {str(e)}")
            _logger.info("Falling back to AI Native...")
            return self._extract_with_ai_native(client, pdf_binary, document_type, filename)

    def _extract_pdf_to_text_pymupdf(self, pdf_binary, filename):
        """
        Extract text from PDF using PyMuPDF (fast, good for digital PDFs)

        Args:
            pdf_binary (bytes): Binary PDF data
            filename (str): Original filename for logging

        Returns:
            str: Extracted text with page markers

        Raises:
            ImportError: If PyMuPDF is not installed
            Exception: If PDF extraction fails
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise ImportError(
                "PyMuPDF is not installed. Please install it with: pip install PyMuPDF"
            )

        try:
            # Open PDF from binary data
            doc = fitz.open(stream=pdf_binary, filetype="pdf")
            total_pages = len(doc)

            _logger.info(f"PyMuPDF: Processing {total_pages} pages...")

            full_text = ""

            # Extract text from each page
            for page_num in range(total_pages):
                page = doc[page_num]

                # Add page marker
                full_text += f"\n{'='*70}\n"
                full_text += f"PAGE {page_num + 1}\n"
                full_text += f"{'='*70}\n"

                # Extract text with layout preservation
                page_text = page.get_text("text")
                full_text += page_text

                _logger.debug(f"Page {page_num + 1}: Extracted {len(page_text)} characters")

            doc.close()

            _logger.info(f"PyMuPDF: Successfully extracted {len(full_text)} total characters")

            return full_text

        except Exception as e:
            _logger.error(f"PyMuPDF extraction failed: {str(e)}")
            raise

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

        # Get max retries from config (default: 3)
        GEMINI_MAX_RETRIES = int(
            self.env['ir.config_parameter'].sudo().get_param(
                'robotia_document_extractor.gemini_max_retries',
                default='3'
            )
        )

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
        return strategy_prompts.get_text_extract_prompt(document_type)

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
        return strategy_prompts.get_text_to_json_prompt(document_type, extracted_text)

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

        # Get max retries from config (default: 3)
        GEMINI_MAX_RETRIES = int(
            self.env['ir.config_parameter'].sudo().get_param(
                'robotia_document_extractor.gemini_max_retries',
                default='3'
            )
        )

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
                    _logger.info(f"Retrying immediately...")
                else:
                    _logger.error("All JSON conversion attempts failed")

            except Exception as e:
                last_error = e
                _logger.warning(f"Attempt {retry_attempt + 1} failed: {type(e).__name__}: {str(e)}")
                if retry_attempt < GEMINI_MAX_RETRIES - 1:
                    _logger.info(f"Retrying immediately...")
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
            'year_1': data.get('year_1'),
            'year_2': data.get('year_2'),
            'year_3': data.get('year_3'),
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
