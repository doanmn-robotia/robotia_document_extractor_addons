from google import genai
import logging
from odoo import models
import json

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
from odoo.addons.robotia_document_extractor.prompts import strategy_prompts

_logger = logging.getLogger(__name__)

class ExtractionServiceBatching(models.AbstractModel):
    _inherit = "document.extraction.service"

    def _initialize_default_prompts(self):
        """
        Initialize default extraction prompts in system parameters
        Called during module installation via XML data file
        """
        params = self.env['ir.config_parameter'].sudo()
        # Set Batch Form 01 default prompt if not exists
        if not params.get_param('robotia_document_extractor.batch_prompt_form_01'):
            params.set_param(
                'robotia_document_extractor.batch_prompt_form_01',
                self._get_default_batch_prompt_form_01()
            )

        # Set Batch Form 02 default prompt if not exists
        if not params.get_param('robotia_document_extractor.batch_prompt_form_02'):
            params.set_param(
                'robotia_document_extractor.batch_prompt_form_02',
                self._get_default_batch_prompt_form_02()
            )
        return super()._initialize_default_prompts()

    def extract_pdf(self, pdf_binary, document_type, log_id=None):
        """
        Extract structured data from PDF using configurable extraction strategy

        Available Strategies (configured in Settings):
        - batch_extract: Batch Extraction (PDF → Images → Batch AI with chat session)

        Args:
            pdf_binary (bytes): Binary PDF data
            document_type (str): '01' for Registration, '02' for Report
            filename (str): Original filename for logging
            log_id (int, optional): Extraction log ID for saving OCR data

        Returns:
            dict: Structured data extracted from PDF

        Raises:
            ValueError: If API key not configured or extraction fails
        """

        ICP = self.env['ir.config_parameter'].sudo()
        api_key = ICP.get_param('robotia_document_extractor.gemini_api_key')
        strategy = ICP.get_param('robotia_document_extractor.extraction_strategy', default='ai_native')
        if strategy == 'batch_extract':
            # Configure Gemini
            client = genai.Client(api_key=api_key)
            _logger.info(f"Starting AI extraction for {filename} (Type: {document_type})")
            _logger.info(f"Using extraction strategy: {strategy}")
            # Strategy 3: Batch Extraction (PDF → Images → Batch AI with chat session)
            return self._extract_with_batch_extract(client, pdf_binary, document_type, filename)

        return super().extract_pdf(pdf_binary, document_type, log_id)



    # =========================================================================
    # BATCH EXTRACTION STRATEGY (Strategy 3)
    # =========================================================================

    def _pdf_to_images(self, pdf_binary, filename):
        """
        Convert PDF to JPEG images using PyMuPDF

        Args:
            pdf_binary (bytes): Binary PDF data
            filename (str): Original filename for logging

        Returns:
            list: List of image file paths (temporary files)

        Raises:
            ImportError: If PyMuPDF or Pillow is not installed
            Exception: If PDF conversion fails
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise ImportError(
                "PyMuPDF is not installed. Please install it with: pip install PyMuPDF"
            )

        try:
            from PIL import Image
        except ImportError:
            raise ImportError(
                "Pillow is not installed. Please install it with: pip install Pillow"
            )

        import tempfile
        import io

        # Get DPI from config
        ICP = self.env['ir.config_parameter'].sudo()
        dpi = int(ICP.get_param('robotia_document_extractor.batch_image_dpi', '200'))

        _logger.info(f"Converting PDF to images (DPI: {dpi})...")

        try:
            # Open PDF from binary data
            doc = fitz.open(stream=pdf_binary, filetype="pdf")
            total_pages = len(doc)

            _logger.info(f"PDF has {total_pages} pages")

            image_paths = []

            # Calculate zoom for DPI
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)

            # Convert each page to image
            for page_num in range(total_pages):
                page = doc[page_num]

                # Render page to pixmap
                pix = page.get_pixmap(matrix=mat)

                # Convert to JPEG bytes
                img_data = pix.tobytes("jpeg")

                # Open with PIL to save
                img = Image.open(io.BytesIO(img_data))

                # Create temporary file
                tmp_file = tempfile.NamedTemporaryFile(
                    delete=False,
                    suffix=f'_page_{page_num + 1:03d}.jpg',
                    prefix='batch_extract_'
                )
                tmp_file.close()  # Close to allow PIL to write

                # Save as JPEG
                img.save(tmp_file.name, 'JPEG', quality=95)
                image_paths.append(tmp_file.name)

                _logger.debug(f"Page {page_num + 1}/{total_pages} converted")

            doc.close()

            _logger.info(f"Successfully converted {len(image_paths)} pages to images")

            return image_paths

        except Exception as e:
            _logger.error(f"PDF to images conversion failed: {str(e)}")
            raise

    def _get_default_batch_prompt_form_01(self):
        """
        Default batch extraction prompt for Form 01 (Registration)

        Preserves ALL critical rules from existing prompt but adapted for per-page extraction

        Returns:
            str: Default batch prompt for Form 01
        """
        # Note: This is a template. Actual batch prompt is built in _build_batch_prompt()
        # which calls strategy_prompts.get_batch_extract_prompt() with page numbers
        return "Batch prompt template for Form 01"

    def _get_default_batch_prompt_form_02(self):
        """
        Default batch extraction prompt for Form 02 (Report)

        Preserves ALL critical rules but adapted for per-page batch extraction

        Returns:
            str: Default batch prompt for Form 02
        """
        # Note: This is a template. Actual batch prompt is built in _build_batch_prompt()
        # which calls strategy_prompts.get_batch_extract_prompt() with page numbers
        return "Batch prompt template for Form 02"

    # =========================================================================
    # BATCH EXTRACTION - CORE METHODS
    # =========================================================================

    def _extract_with_batch_extract(self, client, pdf_binary, document_type, filename):
        """
        Strategy 3: Batch Extraction (PDF → Images → Batch AI with chat session)

        Main entry point for batch extraction strategy

        Args:
            client: Gemini client instance
            pdf_binary (bytes): Binary PDF data
            document_type (str): '01' or '02'
            filename (str): Original filename for logging

        Returns:
            dict: Extracted and cleaned data

        Raises:
            ValueError: If extraction fails
        """
        import os

        _logger.info("=" * 70)
        _logger.info("BATCH EXTRACTION STRATEGY")
        _logger.info("=" * 70)

        image_paths = []

        try:
            # Step 1: Convert PDF to images
            _logger.info("Step 1/3: Converting PDF to images...")
            image_paths = self._pdf_to_images(pdf_binary, filename)
            _logger.info(f"✓ Converted {len(image_paths)} pages to images")

            # Step 2: Phase 1 - Batch AI extraction
            _logger.info("Step 2/3: Phase 1 - Batch AI extraction...")
            page_results = self._phase1_batch_extraction(client, image_paths, document_type)
            _logger.info(f"✓ Extracted {len(page_results)} pages")

            # Step 3: Phase 2 - Python aggregation
            _logger.info("Step 3/3: Phase 2 - Python aggregation...")
            final_json = self._phase1_batch_extraction(page_results, document_type)
            _logger.info("✓ Aggregation complete")

            _logger.info("=" * 70)
            _logger.info("✓ BATCH EXTRACTION SUCCESSFUL")
            _logger.info("=" * 70)

            return final_json

        except Exception as e:
            _logger.error(f"Batch extraction failed: {type(e).__name__}: {str(e)}")
            raise ValueError(f"Batch extraction failed: {str(e)}")

        finally:
            # ALWAYS cleanup temporary image files
            if image_paths:
                _logger.info(f"Cleaning up {len(image_paths)} temporary image files...")
                for img_path in image_paths:
                    try:
                        if os.path.exists(img_path):
                            os.unlink(img_path)
                    except Exception as e:
                        _logger.warning(f"Failed to delete {img_path}: {e}")
                _logger.info("✓ Cleanup complete")

    def _phase1_batch_extraction(self, client, image_paths, document_type):
        """
        Phase 1: Batch AI extraction with adaptive sizing

        Args:
            client: Gemini client instance
            image_paths (list): List of image file paths
            document_type (str): '01' or '02'

        Returns:
            list: List of page result dicts (one per page)
        """
        import time

        ICP = self.env['ir.config_parameter'].sudo()
        GEMINI_MODEL = ICP.get_param('robotia_document_extractor.gemini_model', 'gemini-2.5-pro')

        total_pages = len(image_paths)

        _logger.info(f"Phase 1: Batch extraction ({total_pages} pages)")

        # Create chat session for context memory
        chat = client.chats.create(model=GEMINI_MODEL)
        _logger.info(f"✓ Chat session created (model: {GEMINI_MODEL})")

        # Send system prompt
        system_prompt = self._build_batch_system_prompt(document_type)
        chat.send_message(system_prompt)
        _logger.info("✓ System prompt sent")

        # Extract first batch (conservative size for analysis)
        first_batch_size = 3
        _logger.info(f"Extracting first batch ({first_batch_size} pages) for complexity analysis...")

        first_batch_results = self._extract_batch(
            chat,
            image_paths[:first_batch_size],
            list(range(1, first_batch_size + 1)),
            total_pages,
            document_type
        )

        # Calculate optimal batch size based on complexity
        batch_size = self._calculate_optimal_batch_size(first_batch_results)
        _logger.info(f"✓ Adaptive batch size determined: {batch_size} pages/call")

        all_results = first_batch_results

        # Process remaining batches
        for start_idx in range(first_batch_size, total_pages, batch_size):
            end_idx = min(start_idx + batch_size, total_pages)
            batch_paths = image_paths[start_idx:end_idx]
            page_numbers = list(range(start_idx + 1, end_idx + 1))

            _logger.info(f"Extracting batch: pages {page_numbers[0]}-{page_numbers[-1]}")

            batch_results = self._extract_batch(
                chat,
                batch_paths,
                page_numbers,
                total_pages,
                document_type
            )

            all_results.extend(batch_results)

            # Rate limiting between batches
            if end_idx < total_pages:
                _logger.info("⏳ Rate limiting (5s)...")
                time.sleep(5)

        _logger.info(f"✓ Phase 1 complete: {len(all_results)} pages extracted")

        return all_results

    def _extract_batch(self, chat, batch_paths, page_numbers, total_pages, document_type):
        """
        Extract single batch of pages

        Args:
            chat: Chat session instance
            batch_paths (list): Image paths for this batch
            page_numbers (list): Page numbers for this batch
            total_pages (int): Total pages in document
            document_type (str): '01' or '02'

        Returns:
            list: List of page dicts for this batch
        """
        # Build mega context + batch prompt
        mega_context = self._build_mega_prompt_context()
        batch_prompt = self._build_batch_prompt(page_numbers, total_pages, document_type)

        # Prepare contents (text + multiple images)
        contents = mega_context + [types.Part.from_text(text=batch_prompt)]

        for img_path in batch_paths:
            with open(img_path, 'rb') as f:
                image_bytes = f.read()

            contents.append(
                types.Part(
                    inline_data=types.Blob(
                        mime_type="image/jpeg",
                        data=image_bytes
                    )
                )
            )

        # Send to chat
        try:
            response = chat.send_message(contents)
            response_text = response.text

            # Clean markdown
            if response_text.startswith("```json"):
                response_text = response_text.replace("```json\n", "").replace("\n```", "")
            elif response_text.startswith("```"):
                response_text = response_text.replace("```\n", "").replace("\n```", "")

            # Parse JSON - expect array of page objects
            batch_json = json.loads(response_text)

            # Validate response structure
            if not isinstance(batch_json, list):
                raise ValueError("Expected array of page objects")

            if len(batch_json) != len(page_numbers):
                _logger.warning(f"Expected {len(page_numbers)} pages, got {len(batch_json)}")

            # Log summary
            for page_data in batch_json:
                page_num = page_data.get("page", "?")
                _logger.debug(f"  ✓ Page {page_num} extracted")

            return batch_json

        except Exception as e:
            _logger.error(f"Batch extraction failed: {e}")
            # Return error placeholders
            return [
                {
                    "page": page_num,
                    "error": str(e),
                    "extraction_failed": True
                }
                for page_num in page_numbers
            ]

    def _calculate_optimal_batch_size(self, first_batch_results):
        """
        Calculate optimal batch size based on document complexity

        Analyzes first batch to count table rows and determines batch size:
        - Complex (>50 rows/page): 3 pages/batch
        - Medium (20-50 rows/page): 5 pages/batch
        - Simple (<20 rows/page): 7 pages/batch

        Args:
            first_batch_results (list): Results from first batch

        Returns:
            int: Optimal batch size (3-7 pages)
        """
        ICP = self.env['ir.config_parameter'].sudo()
        min_size = int(ICP.get_param('robotia_document_extractor.batch_size_min', '3'))
        max_size = int(ICP.get_param('robotia_document_extractor.batch_size_max', '7'))

        # Count total rows across all tables in first batch
        total_rows = 0

        for page in first_batch_results:
            if page.get('error'):
                continue

            # Count rows in all table types
            for table_key in [
                'substance_usage', 'equipment_product', 'equipment_ownership',
                'collection_recycling', 'quota_usage', 'equipment_product_report',
                'equipment_ownership_report', 'collection_recycling_report'
            ]:
                if page.get(table_key):
                    total_rows += len(page[table_key])

        # Calculate average rows per page
        pages_count = len([p for p in first_batch_results if not p.get('error')])
        rows_per_page = total_rows / pages_count if pages_count > 0 else 0

        _logger.info(f"Complexity analysis: {rows_per_page:.1f} rows/page")

        # Determine batch size based on complexity
        if rows_per_page > 50:
            return min_size  # Complex: 3 pages
        elif rows_per_page > 20:
            return (min_size + max_size) // 2  # Medium: 5 pages
        else:
            return max_size  # Simple: 7 pages

    def _build_batch_system_prompt(self, document_type):
        """
        Build system prompt for chat initialization

        Args:
            document_type (str): '01' or '02'

        Returns:
            str: System prompt for chat session
        """
        return strategy_prompts.get_batch_system_prompt(document_type)

    def _build_batch_prompt(self, page_numbers, total_pages, document_type):
        """
        Build per-batch extraction prompt

        Args:
            page_numbers (list): Page numbers for this batch
            total_pages (int): Total pages in document
            document_type (str): '01' or '02'

        Returns:
            str: Formatted batch prompt
        """
        start = page_numbers[0]
        end = page_numbers[-1]
        count = len(page_numbers)

        return strategy_prompts.get_batch_extract_prompt(
            document_type, start, end, total_pages, count
        )

    # =========================================================================
    # PHASE 2: PYTHON AGGREGATION
    # =========================================================================

    def _phase2_python_aggregation(self, page_results, document_type):
        """
        Phase 2: Aggregate page results into final JSON

        Pure Python aggregation (deterministic, no AI):
        1. Merge metadata from all pages
        2. Aggregate table rows
        3. Deduplicate by sequence number
        4. Validate

        Args:
            page_results (list): List of page result dicts
            document_type (str): '01' or '02'

        Returns:
            dict: Final aggregated JSON
        """
        _logger.info(f"Phase 2: Python aggregation ({len(page_results)} pages)")

        # Start with empty dict - _merge_metadata will initialize all fields
        final_json = {}

        # Merge metadata
        _logger.info("  Merging metadata...")
        final_json = self._merge_metadata(final_json, page_results, document_type)

        # Aggregate tables
        _logger.info("  Aggregating tables...")
        final_json = self._aggregate_tables(final_json, page_results, document_type)

        # Validate
        _logger.info("  Validating...")
        self._validate_aggregated_json(final_json, document_type)

        _logger.info("✓ Phase 2 complete")

        return final_json


    def _merge_metadata(self, final_json, page_results, document_type):
        """
        Merge metadata from all pages into final JSON

        Strategy:
        - Initialize all expected fields (from prompt schema)
        - First non-null value wins for scalar fields
        - Merge arrays (activity_field_codes)
        """
        # Define all expected metadata fields based on document type
        # These match the PROMPT schema exactly
        metadata_fields = [
            'year', 'year_1', 'year_2', 'year_3',
            'organization_name', 'business_license_number',
            'business_license_date', 'business_license_place',
            'legal_representative_name', 'legal_representative_position',
            'contact_person_name', 'contact_address',
            'contact_phone', 'contact_fax', 'contact_email',
            'contact_country_code', 'contact_state_code'
        ]

        # Initialize all metadata fields to None
        for field in metadata_fields:
            if field not in final_json:
                final_json[field] = None

        # Initialize arrays (use set for activity codes to auto-deduplicate)
        activity_codes_set = set()

        # Initialize ALL flags based on document type
        if document_type == '01':
            final_json['has_table_1_1'] = None
            final_json['has_table_1_2'] = None
            final_json['has_table_1_3'] = None
            final_json['has_table_1_4'] = None
            final_json['is_capacity_merged_table_1_2'] = None
            final_json['is_capacity_merged_table_1_3'] = None
        else:  # '02'
            final_json['has_table_2_1'] = None
            final_json['has_table_2_2'] = None
            final_json['has_table_2_3'] = None
            final_json['has_table_2_4'] = None
            final_json['is_capacity_merged_table_2_2'] = None
            final_json['is_capacity_merged_table_2_3'] = None

        # Merge from page results (first non-null wins)
        for page in page_results:
            if page.get('error'):
                continue

            # Merge scalar metadata fields
            for field in metadata_fields:
                if final_json.get(field) is None and page.get(field):
                    final_json[field] = page[field]

            # Merge activity_field_codes (set automatically handles uniqueness)
            if page.get('activity_field_codes'):
                activity_codes_set.update(page['activity_field_codes'])

            # Merge ALL flags (first non-null wins)
            all_flag_keys = [
                'has_table_1_1', 'has_table_1_2', 'has_table_1_3', 'has_table_1_4',
                'has_table_2_1', 'has_table_2_2', 'has_table_2_3', 'has_table_2_4',
                'is_capacity_merged_table_1_2', 'is_capacity_merged_table_1_3',
                'is_capacity_merged_table_2_2', 'is_capacity_merged_table_2_3'
            ]
            for flag_key in all_flag_keys:
                if flag_key in final_json and final_json.get(flag_key) is None and page.get(flag_key) is not None:
                    final_json[flag_key] = page[flag_key]

        # Default remaining null flags to False
        all_flag_keys = [
            'has_table_1_1', 'has_table_1_2', 'has_table_1_3', 'has_table_1_4',
            'has_table_2_1', 'has_table_2_2', 'has_table_2_3', 'has_table_2_4',
            'is_capacity_merged_table_1_2', 'is_capacity_merged_table_1_3',
            'is_capacity_merged_table_2_2', 'is_capacity_merged_table_2_3'
        ]
        for flag_key in all_flag_keys:
            if flag_key in final_json and final_json[flag_key] is None:
                final_json[flag_key] = False

        # Convert activity codes set back to list for JSON serialization
        final_json['activity_field_codes'] = list(activity_codes_set)

        # Set default country code (Vietnam forms)
        if final_json.get('contact_country_code') is None:
            final_json['contact_country_code'] = 'VN'
            _logger.debug("Set default contact_country_code='VN'")

        # Validate critical metadata
        if not final_json.get('organization_name'):
            _logger.warning("Missing organization_name after merge - extraction may have failed")
        if not final_json.get('year'):
            _logger.warning("Missing year after merge - extraction may have failed")

        return final_json

    def _aggregate_tables(self, final_json, page_results, document_type):
        """
        Aggregate all table rows from all pages

        Collects rows from all pages and deduplicates by sequence number
        """
        # Define table keys based on document type
        if document_type == '01':
            table_keys = ['substance_usage', 'equipment_product', 'equipment_ownership', 'collection_recycling']
        else:  # '02'
            table_keys = ['quota_usage', 'equipment_product_report', 'equipment_ownership_report', 'collection_recycling_report']

        # Initialize all table arrays
        for table_key in table_keys:
            final_json[table_key] = []

        # Aggregate rows from all pages
        for table_key in table_keys:
            all_rows = []

            for page in page_results:
                if page.get('error'):
                    continue

                if page.get(table_key):
                    all_rows.extend(page[table_key])

            # Deduplicate by sequence (except collection_recycling_report which has no sequence)
            if table_key == 'collection_recycling_report':
                final_json[table_key] = all_rows
            else:
                final_json[table_key] = self._deduplicate_by_sequence(all_rows)

            _logger.debug(f"    {table_key}: {len(final_json[table_key])} rows")

        return final_json

    def _deduplicate_by_sequence(self, rows):
        """
        Remove duplicate rows by sequence number

        Title rows (is_title=true) are always kept
        Data rows are deduplicated by sequence number

        Args:
            rows (list): List of row dicts

        Returns:
            list: Deduplicated rows
        """
        seen_sequences = set()
        unique_rows = []

        for row in rows:
            # Title rows: always keep
            if row.get('is_title'):
                unique_rows.append(row)
                continue

            # Data rows: check sequence
            seq = row.get('sequence')

            if seq is not None and seq not in seen_sequences:
                seen_sequences.add(seq)
                unique_rows.append(row)

        return unique_rows

    def _validate_aggregated_json(self, final_json, document_type):
        """
        Validate final aggregated JSON

        Checks for:
        - Missing critical metadata
        - Reasonable row counts
        - Duplicate sequences
        """
        warnings = []

        # Check critical metadata
        if not final_json.get('organization_name'):
            warnings.append("Missing organization_name")

        # Check for duplicate sequences in tables
        if document_type == '01':
            for table_key in ['substance_usage', 'equipment_product', 'equipment_ownership']:
                rows = final_json.get(table_key, [])
                sequences = [r['sequence'] for r in rows if not r.get('is_title') and r.get('sequence')]
                if len(sequences) != len(set(sequences)):
                    warnings.append(f"Duplicate sequences in {table_key}")
        else:  # '02'
            for table_key in ['quota_usage', 'equipment_product_report', 'equipment_ownership_report']:
                rows = final_json.get(table_key, [])
                sequences = [r['sequence'] for r in rows if not r.get('is_title') and r.get('sequence')]
                if len(sequences) != len(set(sequences)):
                    warnings.append(f"Duplicate sequences in {table_key}")

        if warnings:
            _logger.warning(f"Validation warnings: {', '.join(warnings)}")
        else:
            _logger.info("  ✅ Validation passed")
