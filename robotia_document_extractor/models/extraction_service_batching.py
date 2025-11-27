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

    def extract_pdf(self, pdf_binary, document_type, filename):
        """
        Extract structured data from PDF using configurable extraction strategy

        Available Strategies (configured in Settings):
        - batch_extract: Batch Extraction (PDF → Images → Batch AI with chat session)

        Args:
            pdf_binary (bytes): Binary PDF data
            document_type (str): '01' for Registration, '02' for Report
            filename (str): Original filename for logging

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

        return super().extract_pdf(pdf_binary, document_type, filename)



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

    def _get_critical_extraction_rules(self, document_type):
        """
        Extract critical rules from existing prompts to preserve in batch prompts

        This ensures ALL important instructions are maintained in batch extraction:
        - Template detection
        - Year field extraction
        - Line wrap reconstruction
        - Capacity field parsing
        - Substance standardization
        - Vietnamese handling

        Args:
            document_type (str): '01' or '02'

        Returns:
            str: Critical extraction rules text
        """
        if document_type == '01':
            return """
## PART I: DOCUMENT INTELLIGENCE - REAL DATA vs TEMPLATE/MOCKUP

CRITICAL: Many companies submit PARTIALLY FILLED templates with mockup data.

**EXTRACT ONLY REAL DATA:**
- Organization name that's SPECIFIC (not "Công ty ABC", "Tên công ty")
- Actual substance names (HFC-134a, R-410A, R-32), NOT examples
- Numbers that are HANDWRITTEN/TYPED by user (even if messy)
- Checkboxes CLEARLY marked (✓, X, filled box)
- Specific dates (15/03/2024), NOT placeholders (dd/mm/yyyy, __/__/____)

**IGNORE TEMPLATE/MOCKUP DATA:**
- Placeholder text: "Tên doanh nghiệp", "Tên chất", "Ghi chú"
- Example markers: "Ví dụ:", "VD:", "Example:", "(mẫu)"
- Instruction text: "Ghi rõ...", "Điền vào...", "Nêu rõ..."
- Template numbers: Perfect sequences (1,2,3) or round numbers (100,200,300)
- Empty template cells: Unfilled rows with only borders

**TEMPLATE DETECTION RULES:**
- Repetition test: Same substance 5+ times with round numbers → TEMPLATE
- Number pattern: All values multiples of 100 → TEMPLATE
- Gray text/Italic: Often placeholder → SKIP
- Brackets: "(Tên chất)", "[Ghi rõ]" → TEMPLATE
- Cross-validation: If organization name is template, ENTIRE form is template

## YEAR FIELDS EXTRACTION (CRITICAL)

**Extract year values from table headers:**

1. **Main year field (`year`):**
   - Extract from document header/title
   - Usually the registration year or report year
   - Example: "Đăng ký năm 2024" → year = 2024

2. **Table column years (`year_1`, `year_2`, `year_3`):**
   - These are the 3 YEAR VALUES from table column headers
   - Found in Table 1.1 (Substance Usage) - typically the first 3 quantity columns
   - Headers are often MERGED CELLS containing year numbers

**Example from Table 1.1:**
```
Header row: | Chất kiểm soát | 2022 (kg) | 2023 (kg) | 2024 (kg) | Trung bình |
                                  ↑           ↑           ↑
                              year_1      year_2      year_3
```

**Extraction rules:**
- Look at the MERGED HEADER CELLS above the first 3 quantity columns in Table 1.1
- Extract ONLY the year numbers (integers): 2022, 2023, 2024
- Ignore column sub-headers like "(kg)", "(tấn CO2)"
- If year is written in Vietnamese: "Năm 2024" → extract 2024
- If only 2-digit: "22" → convert to 2022 (assume 20XX century)
- Common patterns:
  - "2022" → year_1 = 2022
  - "Năm 2023" → year_2 = 2023
  - "N-1" or "Năm trước" → year_1 = year - 1
  - "N" or "Năm hiện tại" → year_2 = year
  - "N+1" or "Năm sau" → year_3 = year + 1

**If years are not explicitly stated:**
- Use logical sequence based on main `year` field
- Example: if year = 2024 → year_1 = 2022, year_2 = 2023, year_3 = 2024

## HANDLING POOR QUALITY DOCUMENTS

**Context-based inference:**
- Blurry substance name? → Check HS code column
- Unclear number? → Look at neighboring cells
- Missing data? → Cross-reference other sections

**Line wrap reconstruction (CRITICAL):**
- "300.0" (line 1) + "00" (line 2) = 300000 (NOT 30000!)
- ALWAYS concatenate multi-line cell content BEFORE parsing

**Handwritten ambiguity:**
- "1" vs "7": Use unit context
- When unclear: Mark as null, DON'T guess

**Capacity field parsing (CRITICAL for Tables 1.2 and 1.3):**

**IMPORTANT - Table mapping:**
- Table 1.2 = "equipment_product" array
- Table 1.3 = "equipment_ownership" array
- Both tables have capacity-related columns in PDF

**STEP 1: Determine PDF table structure FOR EACH TABLE**

For Table 1.2 (Equipment/Product):
- Look at Table 1.2's column headers in PDF
- If 1 column "Năng suất lạnh/Công suất điện" (merged) → is_capacity_merged_table_1_2 = TRUE
- If 2 columns "Năng suất lạnh" AND "Công suất điện" (separate) → is_capacity_merged_table_1_2 = FALSE

For Table 1.3 (Equipment Ownership):
- Look at Table 1.3's column headers in PDF
- If 1 column "Năng suất lạnh/Công suất điện" (merged) → is_capacity_merged_table_1_3 = TRUE
- If 2 columns "Năng suất lạnh" AND "Công suất điện" (separate) → is_capacity_merged_table_1_3 = FALSE

**STEP 2: Extract data into equipment_product array (Table 1.2)**

CASE 1 - Table 1.2 has MERGED column (is_capacity_merged_table_1_2 = TRUE):
  → For each row in equipment_product array:
     - Extract entire "Năng suất lạnh/Công suất điện" cell value to "capacity" field AS-IS (e.g., "5 HP/3.5 kW")
     - Set "cooling_capacity" = null
     - Set "power_capacity" = null

CASE 2 - Table 1.2 has SEPARATE columns (is_capacity_merged_table_1_2 = FALSE):
  → For each row in equipment_product array:
     - Extract "Năng suất lạnh" column to "cooling_capacity" (ONLY HP/BTU/TR/RT units)
     - Extract "Công suất điện" column to "power_capacity" (ONLY kW/W units)
     - Set "capacity" = null

**STEP 3: Extract data into equipment_ownership array (Table 1.3)**

CASE 1 - Table 1.3 has MERGED column (is_capacity_merged_table_1_3 = TRUE):
  → For each row in equipment_ownership array:
     - Extract entire "Năng suất lạnh/Công suất điện" cell value to "capacity" field AS-IS
     - Set "cooling_capacity" = null
     - Set "power_capacity" = null

CASE 2 - Table 1.3 has SEPARATE columns (is_capacity_merged_table_1_3 = FALSE):
  → For each row in equipment_ownership array:
     - Extract "Năng suất lạnh" column to "cooling_capacity" (ONLY HP/BTU/TR/RT units)
     - Extract "Công suất điện" column to "power_capacity" (ONLY kW/W units)
     - Set "capacity" = null

**Unit extraction rules:**
- **ALWAYS include unit** (e.g., "5 HP", NOT just "5")
- Common units: **HP, kW, BTU, TR, RT, kcal/h, W**
- Preserve formatting (e.g., "3.5 kW", "2,000 BTU")
- Handle Vietnamese notation (e.g., "mã lực" = HP)

## NUMBER FORMATTING (CRITICAL)

- LINE WRAP BUG: "300.0" + "00" (next line) = 300000 (NOT 30000!)
- ALWAYS concatenate multi-line numbers BEFORE parsing
- Remove thousands separators, convert decimal to dot

## SUBSTANCE NAME STANDARDIZATION

- Match to official list using fuzzy matching
- "HFC134a" → "HFC-134a", "R410A" → "R-410A"
- If no match: prefix "[UNKNOWN] "

## ACTIVITY FIELD MAPPING

- "Sản xuất chất..." → "production"
- "Nhập khẩu chất..." → "import"
- "Xuất khẩu chất..." → "export"
- "Sản xuất thiết bị..." → "equipment_production"
- "Nhập khẩu thiết bị..." → "equipment_import"
- "Sở hữu máy điều hòa..." → "ac_ownership"
- "Sở hữu thiết bị lạnh..." → "refrigeration_ownership"
- "Thu gom, tái chế..." → "collection_recycling"

## TABLE PRESENCE LOGIC

- has_table_1_1 = true IF any(production, import, export) checked
- has_table_1_2 = true IF any(equipment_production, equipment_import) checked
- has_table_1_3 = true IF any(ac_ownership, refrigeration_ownership) checked
- has_table_1_4 = true IF collection_recycling checked
"""
        else:  # '02'
            return """
## PART I: DOCUMENT INTELLIGENCE - REAL DATA vs TEMPLATE/MOCKUP

CRITICAL: Many companies submit PARTIALLY FILLED templates with mockup data.

**EXTRACT ONLY REAL DATA:**
- Organization name that's SPECIFIC (not "Công ty ABC", "Tên công ty")
- Actual substance names (HFC-134a, R-410A, R-32), NOT examples
- Numbers that are HANDWRITTEN/TYPED by user (even if messy)
- Specific dates (15/03/2024), NOT placeholders
- Country codes that are REAL (VN, CN, TH), NOT template "(Mã nước)"

**IGNORE TEMPLATE/MOCKUP DATA:**
- Placeholder text: "Tên doanh nghiệp", "Tên chất", "Ghi chú"
- Example markers: "Ví dụ:", "VD:", "Example:", "(mẫu)"
- Instruction text: "Ghi rõ...", "Điền vào...", "Nêu rõ..."
- Template numbers: Perfect sequences or round numbers
- Empty template cells

## YEAR FIELDS EXTRACTION (CRITICAL)

**Extract year values from table headers:**

1. **Main year field (`year`):**
   - Extract from document header/title
   - Usually the report year
   - Example: "Báo cáo năm 2024" → year = 2024

2. **Table column years (`year_1`, `year_2`, `year_3`):**
   - These are the 3 YEAR VALUES from table column headers
   - Found in Table 2.1 (Quota Usage) - typically the first 3 quantity columns
   - Headers are often MERGED CELLS containing year numbers

**Example from Table 2.1:**
```
Header row: | Tên chất | Mã HS | 2022 | 2023 | 2024 | Giá TB |
                                  ↑      ↑      ↑
                              year_1  year_2  year_3
```

**Extraction rules:**
- Look at the MERGED HEADER CELLS above the first 3 quantity columns in Table 2.1
- Extract ONLY the year numbers (integers): 2022, 2023, 2024
- Ignore column sub-headers like "(kg)", "(tấn CO2)", "(USD)"
- If year is written in Vietnamese: "Năm 2024" → extract 2024
- If only 2-digit: "22" → convert to 2022 (assume 20XX century)
- Common patterns:
  - "2022" → year_1 = 2022
  - "Năm 2023" → year_2 = 2023
  - "N-1" or "Năm trước" → year_1 = year - 1
  - "N" or "Năm hiện tại" → year_2 = year
  - "N+1" or "Năm sau" → year_3 = year + 1

**If years are not explicitly stated:**
- Use logical sequence based on main `year` field
- Example: if year = 2024 → year_1 = 2022, year_2 = 2023, year_3 = 2024

## HANDLING POOR QUALITY DOCUMENTS

**Context-based inference:**
- Blurry substance name? → Check HS code column
- Unclear number? → Look at neighboring cells
- Missing data? → Cross-reference other sections

**Line wrap reconstruction (CRITICAL for Table 2.1):**
- "300.0" (line 1) + "00" (line 2) = 300000 (NOT 30000!)
- ALWAYS concatenate multi-line cell content BEFORE parsing

**Handwritten ambiguity:**
- When unclear: Mark as null, DON'T guess

**Capacity field parsing (CRITICAL for Tables 2.2 and 2.3):**

**IMPORTANT - Table mapping:**
- Table 2.2 = "equipment_product_report" array
- Table 2.3 = "equipment_ownership_report" array
- Both tables have capacity-related columns in PDF

**STEP 1: Determine PDF table structure FOR EACH TABLE**

For Table 2.2 (Equipment/Product Report):
- Look at Table 2.2's column headers in PDF
- If 1 column "Năng suất lạnh/Công suất điện" (merged) → is_capacity_merged_table_2_2 = TRUE
- If 2 columns "Năng suất lạnh" AND "Công suất điện" (separate) → is_capacity_merged_table_2_2 = FALSE

For Table 2.3 (Equipment Ownership Report):
- Look at Table 2.3's column headers in PDF
- If 1 column "Năng suất lạnh/Công suất điện" (merged) → is_capacity_merged_table_2_3 = TRUE
- If 2 columns "Năng suất lạnh" AND "Công suất điện" (separate) → is_capacity_merged_table_2_3 = FALSE

**STEP 2: Extract data into equipment_product_report array (Table 2.2)**

CASE 1 - Table 2.2 has MERGED column (is_capacity_merged_table_2_2 = TRUE):
  → For each row in equipment_product_report array:
     - Extract entire "Năng suất lạnh/Công suất điện" cell value to "capacity" field AS-IS (e.g., "5 HP/3.5 kW")
     - Set "cooling_capacity" = null
     - Set "power_capacity" = null

CASE 2 - Table 2.2 has SEPARATE columns (is_capacity_merged_table_2_2 = FALSE):
  → For each row in equipment_product_report array:
     - Extract "Năng suất lạnh" column to "cooling_capacity" (ONLY HP/BTU/TR/RT units)
     - Extract "Công suất điện" column to "power_capacity" (ONLY kW/W units)
     - Set "capacity" = null

**STEP 3: Extract data into equipment_ownership_report array (Table 2.3)**

CASE 1 - Table 2.3 has MERGED column (is_capacity_merged_table_2_3 = TRUE):
  → For each row in equipment_ownership_report array:
     - Extract entire "Năng suất lạnh/Công suất điện" cell value to "capacity" field AS-IS
     - Set "cooling_capacity" = null
     - Set "power_capacity" = null

CASE 2 - Table 2.3 has SEPARATE columns (is_capacity_merged_table_2_3 = FALSE):
  → For each row in equipment_ownership_report array:
     - Extract "Năng suất lạnh" column to "cooling_capacity" (ONLY HP/BTU/TR/RT units)
     - Extract "Công suất điện" column to "power_capacity" (ONLY kW/W units)
     - Set "capacity" = null

**Unit extraction rules:**
- **ALWAYS include unit** (e.g., "5 HP", NOT just "5")
- Common units: **HP, kW, BTU, TR, RT, kcal/h, W**
- Preserve formatting (e.g., "3.5 kW", "2,000 BTU")
- Handle Vietnamese notation (e.g., "mã lực" = HP)

## TABLE 2.4 SPECIAL RULES

- NO title rows at all
- One row per substance with ALL activities
- Extract all columns (collection, reuse, recycle, disposal)

## COUNTRY CODE EXTRACTION (Table 2.1)

- "Việt Nam" → "VN", "Trung Quốc" → "CN", "Hoa Kỳ" / "Mỹ" → "US"
- "Thái Lan" → "TH", "Nhật Bản" → "JP"
- Return ISO 2-letter UPPERCASE

## NUMBER FORMATTING (CRITICAL for Table 2.1)

- LINE WRAP BUG: "300.0" + "00" (next line) = 300000 (NOT 30000!)
- ALWAYS concatenate multi-line numbers BEFORE parsing
- Remove thousands separators, convert decimal to dot

## SUBSTANCE NAME STANDARDIZATION

- Match to official list using fuzzy matching
- "HFC134a" → "HFC-134a", "R410A" → "R-410A"
- If no match: prefix "[UNKNOWN] "

## TABLE PRESENCE LOGIC

- has_table_2_1 = true IF any(production, import, export) checked
- has_table_2_2 = true IF any(equipment_production, equipment_import) checked
- has_table_2_3 = true IF any(ac_ownership, refrigeration_ownership) checked
- has_table_2_4 = true IF collection_recycling checked
"""

    def _get_default_batch_prompt_form_01(self):
        """
        Default batch extraction prompt for Form 01 (Registration)

        Preserves ALL critical rules from existing prompt but adapted for per-page extraction

        Returns:
            str: Default batch prompt for Form 01
        """
        critical_rules = self._get_critical_extraction_rules('01')

        return f"""
Extract data from PAGES {{start}}-{{end}} (out of {{total}} total).

I am sending you {{count}} page images.

Return JSON ARRAY with {{count}} objects (one per page):

[
  {{
    "page": 1,

    // METADATA (extract if visible on this page, else null)
    "year": <integer or null>,
    "year_1": <integer or null>,
    "year_2": <integer or null>,
    "year_3": <integer or null>,
    "organization_name": "<string or null>",
    "business_license_number": "<string or null>",
    "business_license_date": "<YYYY-MM-DD or null>",
    "business_license_place": "<string or null>",
    "legal_representative_name": "<string or null>",
    "legal_representative_position": "<string or null>",
    "contact_person_name": "<string or null>",
    "contact_address": "<string or null>",
    "contact_phone": "<string or null>",
    "contact_fax": "<string or null>",
    "contact_email": "<string or null>",
    "contact_country_code": "<ISO 2-letter code or null>",
    "contact_state_code": "<ISO Province code or null>",
    "activity_field_codes": [],

    // FLAGS (determine from visible content on this page)
    "has_table_1_1": <boolean or null>,
    "has_table_1_2": <boolean or null>,
    "has_table_1_3": <boolean or null>,
    "has_table_1_4": <boolean or null>,
    "is_capacity_merged_table_1_2": <boolean or null>,
    "is_capacity_merged_table_1_3": <boolean or null>,

    // TABLES (extract ONLY visible rows on this page, empty array if not visible)
    "substance_usage": [
      {{
        "is_title": <boolean>,
        "sequence": <integer>,
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
      }}
    ],

    "equipment_product": [
      {{
        "is_title": <boolean>,
        "sequence": <integer>,
        "product_type": "<string>",
        "hs_code": "<string or null>",
        "capacity": "<string or null>",
        "cooling_capacity": "<string or null>",
        "power_capacity": "<string or null>",
        "quantity": <float or null>,
        "substance_name": "<string>",
        "substance_quantity_per_unit": <float or null>,
        "notes": "<string or null>"
      }}
    ],

    "equipment_ownership": [
      {{
        "is_title": <boolean>,
        "sequence": <integer>,
        "equipment_type": "<string>",
        "start_year": <integer or null>,
        "capacity": "<string or null>",
        "cooling_capacity": "<string or null>",
        "power_capacity": "<string or null>",
        "equipment_quantity": <integer or null>,
        "substance_name": "<string>",
        "refill_frequency": <float or null>,
        "substance_quantity_per_refill": <float or null>
      }}
    ],

    "collection_recycling": [
      {{
        "is_title": <boolean>,
        "sequence": <integer>,
        "activity_type": "<collection|reuse|recycle|disposal>",
        "substance_name": "<string>",
        "quantity_kg": <float or null>,
        "quantity_co2": <float or null>
      }}
    ]
  }},
  // ... repeat for all {{count}} pages
]

{critical_rules}

## BATCH-SPECIFIC INSTRUCTIONS

**PER-PAGE EXTRACTION:**
1. Each page object represents ONE page from the document
2. Extract ONLY what is visible on that specific page
3. If a field/table is not visible on a page → set to null or empty array []
4. Preserve sequence numbers EXACTLY as they appear (critical for deduplication)

**METADATA EXTRACTION:**
- If metadata (org name, license, etc.) is visible on page → extract it
- If not visible → set to null
- Header/footer info may repeat across pages → extract from first occurrence

**TABLE EXTRACTION:**
- Extract ALL visible rows from tables on this page
- Include sequence number from PDF (row number in table)
- Tables may span across multiple pages in different batches
- Title rows (section headers) have is_title=true
- ALWAYS preserve sequence numbers for deduplication

**CONTEXT MEMORY:**
- You are processing batches from same document
- Remember table structure from previous batches
- If you saw Table 1.1 header in previous batch, continue extracting rows
- Maintain consistency in field extraction across batches

CRITICAL: Return array with EXACTLY {{count}} page objects!
Return ONLY valid JSON array. No markdown, no explanations.
"""

    def _get_default_batch_prompt_form_02(self):
        """
        Default batch extraction prompt for Form 02 (Report)

        Preserves ALL critical rules but adapted for per-page batch extraction

        Returns:
            str: Default batch prompt for Form 02
        """
        critical_rules = self._get_critical_extraction_rules('02')

        return f"""
Extract data from PAGES {{start}}-{{end}} (out of {{total}} total).

I am sending you {{count}} page images.

Return JSON ARRAY with {{count}} objects (one per page):

[
  {{
    "page": 1,

    // METADATA (extract if visible, else null)
    "year": <integer or null>,
    "year_1": <integer or null>,
    "year_2": <integer or null>,
    "year_3": <integer or null>,
    "organization_name": "<string or null>",
    "business_license_number": "<string or null>",
    "business_license_date": "<YYYY-MM-DD or null>",
    "business_license_place": "<string or null>",
    "contact_address": "<string or null>",
    "contact_phone": "<string or null>",
    "contact_fax": "<string or null>",
    "contact_email": "<string or null>",
    "contact_country_code": "<ISO 2-letter code or null>",
    "contact_state_code": "<ISO Province code or null>",
    "activity_field_codes": [],

    // FLAGS
    "has_table_2_1": <boolean or null>,
    "has_table_2_2": <boolean or null>,
    "has_table_2_3": <boolean or null>,
    "has_table_2_4": <boolean or null>,
    "is_capacity_merged_table_2_2": <boolean or null>,
    "is_capacity_merged_table_2_3": <boolean or null>,

    // TABLES (visible rows only)
    "quota_usage": [
      {{
        "is_title": <boolean>,
        "sequence": <integer>,
        "usage_type": "<production|import|export>",
        "substance_name": "<string>",
        "hs_code": "<string or null>",
        "allocated_quota_kg": <float or null>,
        "allocated_quota_co2": <float or null>,
        "adjusted_quota_kg": <float or null>,
        "adjusted_quota_co2": <float or null>,
        "total_quota_kg": <float or null>,
        "total_quota_co2": <float or null>,
        "average_price": <float or null>,
        "country_text": "<string or null>",
        "customs_declaration_number": "<string or null>",
        "next_year_quota_kg": <float or null>,
        "next_year_quota_co2": <float or null>
      }}
    ],

    "equipment_product_report": [
      {{
        "is_title": <boolean>,
        "sequence": <integer>,
        "production_type": "<production|import>",
        "product_type": "<string>",
        "hs_code": "<string or null>",
        "capacity": "<string or null>",
        "cooling_capacity": "<string or null>",
        "power_capacity": "<string or null>",
        "quantity": <float or null>,
        "substance_name": "<string>",
        "substance_quantity_per_unit": <float or null>,
        "notes": "<string or null>"
      }}
    ],

    "equipment_ownership_report": [
      {{
        "is_title": <boolean>,
        "sequence": <integer>,
        "ownership_type": "<air_conditioner|refrigeration>",
        "equipment_type": "<string>",
        "equipment_quantity": <integer or null>,
        "substance_name": "<string>",
        "capacity": "<string or null>",
        "cooling_capacity": "<string or null>",
        "power_capacity": "<string or null>",
        "start_year": <integer or null>,
        "refill_frequency": <float or null>,
        "substance_quantity_per_refill": <float or null>,
        "notes": "<string or null>"
      }}
    ],

    "collection_recycling_report": [
      {{
        "substance_name": "<string>",
        "collection_quantity_kg": <float or null>,
        "collection_location": "<string or null>",
        "storage_location": "<string or null>",
        "reuse_quantity_kg": <float or null>,
        "reuse_technology": "<string or null>",
        "recycle_quantity_kg": <float or null>,
        "recycle_technology": "<string or null>",
        "recycle_usage_location": "<string or null>",
        "disposal_quantity_kg": <float or null>,
        "disposal_technology": "<string or null>",
        "disposal_facility": "<string or null>"
      }}
    ]
  }},
  // ... repeat for all {{count}} pages
]

{critical_rules}

## BATCH-SPECIFIC INSTRUCTIONS

**PER-PAGE EXTRACTION:**
1. Each object = ONE page
2. Extract ONLY visible content on that page
3. Not visible → null or []
4. Preserve sequence numbers EXACTLY

**TABLE 2.4 NOTE:**
- NO is_title field in collection_recycling_report
- One row per substance with ALL activities

**CONTEXT MEMORY:**
- Remember previous batches from same document
- Tables may continue across batches
- Maintain consistency

CRITICAL: Return array with EXACTLY {{count}} page objects!
Return ONLY valid JSON array.
"""

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
        import time

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
            final_json = self._phase2_python_aggregation(page_results, document_type)
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
        form_name = "Form 01 (Registration)" if document_type == '01' else "Form 02 (Report)"

        return f"""
You are a STRUCTURED DATA EXTRACTOR for Vietnamese {form_name}.

YOUR JOB:
- Extract content from multiple page images sent together
- Return array of page objects (one per page)
- Maintain context across batches (chat memory)

CRITICAL RULES:
1. I will send you N pages at once
2. Return array with N page objects: [page1_json, page2_json, ...]
3. Each page object follows the schema I provide
4. If a field is not visible on a page, set to null or empty array []
5. Tables may span across pages in different batches - remember context from previous batches!

SEQUENCE NUMBERS ARE CRITICAL:
- Preserve sequence numbers EXACTLY as they appear in tables
- These are used for deduplication when merging batches
- Never skip or renumber sequences

You will receive multiple batches. Remember context from previous batches!
"""

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

        # Build prompt directly with values (bypass template .format() issue)
        critical_rules = self._get_critical_extraction_rules(document_type)

        if document_type == '01':
            return f"""
Extract data from PAGES {start}-{end} (out of {total_pages} total).

I am sending you {count} page images.

Return JSON ARRAY with {count} objects (one per page):

[
  {{
    "page": 1,

    // METADATA (extract if visible on this page, else null)
    "year": <integer or null>,
    "year_1": <integer or null>,
    "year_2": <integer or null>,
    "year_3": <integer or null>,
    "organization_name": "<string or null>",
    "business_license_number": "<string or null>",
    "business_license_date": "<YYYY-MM-DD or null>",
    "business_license_place": "<string or null>",
    "legal_representative_name": "<string or null>",
    "legal_representative_position": "<string or null>",
    "contact_person_name": "<string or null>",
    "contact_address": "<string or null>",
    "contact_phone": "<string or null>",
    "contact_fax": "<string or null>",
    "contact_email": "<string or null>",
    "contact_country_code": "<ISO 2-letter code or null>",
    "contact_state_code": "<ISO Province code or null>",
    "activity_field_codes": [],

    // FLAGS (determine from visible content on this page)
    "has_table_1_1": <boolean or null>,
    "has_table_1_2": <boolean or null>,
    "has_table_1_3": <boolean or null>,
    "has_table_1_4": <boolean or null>,
    "is_capacity_merged_table_1_2": <boolean or null>,
    "is_capacity_merged_table_1_3": <boolean or null>,

    // TABLES (extract ONLY visible rows on this page, empty array if not visible)
    "substance_usage": [
      {{
        "is_title": <boolean>,
        "sequence": <integer>,
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
      }}
    ],

    "equipment_product": [
      {{
        "is_title": <boolean>,
        "sequence": <integer>,
        "product_type": "<string>",
        "hs_code": "<string or null>",
        "capacity": "<string or null>",
        "cooling_capacity": "<string or null>",
        "power_capacity": "<string or null>",
        "quantity": <float or null>,
        "substance_name": "<string>",
        "substance_quantity_per_unit": <float or null>,
        "notes": "<string or null>"
      }}
    ],

    "equipment_ownership": [
      {{
        "is_title": <boolean>,
        "sequence": <integer>,
        "equipment_type": "<string>",
        "start_year": <integer or null>,
        "capacity": "<string or null>",
        "cooling_capacity": "<string or null>",
        "power_capacity": "<string or null>",
        "equipment_quantity": <integer or null>,
        "substance_name": "<string>",
        "refill_frequency": <float or null>,
        "substance_quantity_per_refill": <float or null>
      }}
    ],

    "collection_recycling": [
      {{
        "is_title": <boolean>,
        "sequence": <integer>,
        "activity_type": "<collection|reuse|recycle|disposal>",
        "substance_name": "<string>",
        "quantity_kg": <float or null>,
        "quantity_co2": <float or null>
      }}
    ]
  }},
  // ... repeat for all {count} pages
]

{critical_rules}

## BATCH-SPECIFIC INSTRUCTIONS

**PER-PAGE EXTRACTION:**
1. Each page object represents ONE page from the document
2. Extract ONLY what is visible on that specific page
3. If a field/table is not visible on a page → set to null or empty array []
4. Preserve sequence numbers EXACTLY as they appear (critical for deduplication)

**METADATA EXTRACTION:**
- If metadata (org name, license, etc.) is visible on page → extract it
- If not visible → set to null
- Header/footer info may repeat across pages → extract from first occurrence

**TABLE EXTRACTION:**
- Extract ALL visible rows from tables on this page
- Include sequence number from PDF (row number in table)
- Tables may span across multiple pages in different batches
- Title rows (section headers) have is_title=true
- ALWAYS preserve sequence numbers for deduplication

**CONTEXT MEMORY:**
- You are processing batches from same document
- Remember table structure from previous batches
- If you saw Table 1.1 header in previous batch, continue extracting rows
- Maintain consistency in field extraction across batches

CRITICAL: Return array with EXACTLY {count} page objects!
Return ONLY valid JSON array. No markdown, no explanations.
"""
        else:  # '02'
            return f"""
Extract data from PAGES {start}-{end} (out of {total_pages} total).

I am sending you {count} page images.

Return JSON ARRAY with {count} objects (one per page):

[
  {{
    "page": 1,

    // METADATA (extract if visible, else null)
    "year": <integer or null>,
    "year_1": <integer or null>,
    "year_2": <integer or null>,
    "year_3": <integer or null>,
    "organization_name": "<string or null>",
    "business_license_number": "<string or null>",
    "business_license_date": "<YYYY-MM-DD or null>",
    "business_license_place": "<string or null>",
    "legal_representative_name": "<string or null>",
    "legal_representative_position": "<string or null>",
    "contact_person_name": "<string or null>",
    "contact_address": "<string or null>",
    "contact_phone": "<string or null>",
    "contact_fax": "<string or null>",
    "contact_email": "<string or null>",
    "contact_country_code": "<ISO 2-letter code or null>",
    "contact_state_code": "<ISO Province code or null>",
    "activity_field_codes": [],

    // FLAGS
    "has_table_2_1": <boolean or null>,
    "has_table_2_2": <boolean or null>,
    "has_table_2_3": <boolean or null>,
    "has_table_2_4": <boolean or null>,
    "is_capacity_merged_table_2_2": <boolean or null>,
    "is_capacity_merged_table_2_3": <boolean or null>,

    // TABLES (visible rows only)
    "quota_usage": [
      {{
        "is_title": <boolean>,
        "sequence": <integer>,
        "usage_type": "<production|import|export>",
        "substance_name": "<string>",
        "hs_code": "<string or null>",
        "allocated_quota_kg": <float or null>,
        "allocated_quota_co2": <float or null>,
        "adjusted_quota_kg": <float or null>,
        "adjusted_quota_co2": <float or null>,
        "total_quota_kg": <float or null>,
        "total_quota_co2": <float or null>,
        "average_price": <float or null>,
        "country_text": "<string or null>",
        "customs_declaration_number": "<string or null>",
        "next_year_quota_kg": <float or null>,
        "next_year_quota_co2": <float or null>
      }}
    ],

    "equipment_product_report": [
      {{
        "is_title": <boolean>,
        "sequence": <integer>,
        "production_type": "<production|import>",
        "product_type": "<string>",
        "hs_code": "<string or null>",
        "capacity": "<string or null>",
        "cooling_capacity": "<string or null>",
        "power_capacity": "<string or null>",
        "quantity": <float or null>,
        "substance_name": "<string>",
        "substance_quantity_per_unit": <float or null>,
        "notes": "<string or null>"
      }}
    ],

    "equipment_ownership_report": [
      {{
        "is_title": <boolean>,
        "sequence": <integer>,
        "ownership_type": "<air_conditioner|refrigeration>",
        "equipment_type": "<string>",
        "equipment_quantity": <integer or null>,
        "substance_name": "<string>",
        "capacity": "<string or null>",
        "cooling_capacity": "<string or null>",
        "power_capacity": "<string or null>",
        "start_year": <integer or null>,
        "refill_frequency": <float or null>,
        "substance_quantity_per_refill": <float or null>,
        "notes": "<string or null>"
      }}
    ],

    "collection_recycling_report": [
      {{
        "substance_name": "<string>",
        "collection_quantity_kg": <float or null>,
        "collection_location": "<string or null>",
        "storage_location": "<string or null>",
        "reuse_quantity_kg": <float or null>,
        "reuse_technology": "<string or null>",
        "recycle_quantity_kg": <float or null>,
        "recycle_technology": "<string or null>",
        "recycle_usage_location": "<string or null>",
        "disposal_quantity_kg": <float or null>,
        "disposal_technology": "<string or null>",
        "disposal_facility": "<string or null>"
      }}
    ]
  }},
  // ... repeat for all {count} pages
]

{critical_rules}

## BATCH-SPECIFIC INSTRUCTIONS

**PER-PAGE EXTRACTION:**
1. Each object = ONE page
2. Extract ONLY visible content on that page
3. Not visible → null or []
4. Preserve sequence numbers EXACTLY

**TABLE 2.4 NOTE:**
- NO is_title field in collection_recycling_report
- One row per substance with ALL activities

**CONTEXT MEMORY:**
- Remember previous batches from same document
- Tables may continue across batches
- Maintain consistency

CRITICAL: Return array with EXACTLY {count} page objects!
Return ONLY valid JSON array.
"""

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
        4. Compute flags
        5. Validate

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

        # Compute flags
        _logger.info("  Computing flags...")
        final_json = self._compute_flags(final_json, document_type)

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

    def _compute_flags(self, final_json, document_type):
        """
        Validate and compute flags as FALLBACK

        Flags should come from AI extraction. This method:
        1. Validates AI-extracted flags against actual data
        2. Computes missing flags as fallback (logs warning)

        Args:
            final_json (dict): Final JSON structure
            document_type (str): '01' or '02'

        Returns:
            dict: Updated final_json with validated flags
        """
        if document_type == '01':
            # Validate/fallback for has_table_* flags
            for table_num, table_key in [
                ('1_1', 'substance_usage'),
                ('1_2', 'equipment_product'),
                ('1_3', 'equipment_ownership'),
                ('1_4', 'collection_recycling')
            ]:
                flag_key = f'has_table_{table_num}'
                has_data = len(final_json.get(table_key, [])) > 0

                if final_json.get(flag_key) is None:
                    # AI didn't extract flag - compute from data as fallback
                    final_json[flag_key] = has_data
                    _logger.warning(f"{flag_key} was None - computed from data: {has_data}")
                elif final_json[flag_key] != has_data:
                    # AI flag conflicts with actual data - trust data
                    _logger.warning(f"{flag_key} mismatch: AI said {final_json[flag_key]}, data says {has_data}. Using data.")
                    final_json[flag_key] = has_data

            # Validate capacity merge flags (if still None after merge)
            if final_json.get('is_capacity_merged_table_1_2') is None:
                final_json['is_capacity_merged_table_1_2'] = self._detect_capacity_merge_flag(
                    final_json.get('equipment_product', [])
                )
                _logger.warning("is_capacity_merged_table_1_2 was None - detected from data")

            if final_json.get('is_capacity_merged_table_1_3') is None:
                final_json['is_capacity_merged_table_1_3'] = self._detect_capacity_merge_flag(
                    final_json.get('equipment_ownership', [])
                )
                _logger.warning("is_capacity_merged_table_1_3 was None - detected from data")

        else:  # '02'
            # Validate/fallback for has_table_* flags
            for table_num, table_key in [
                ('2_1', 'quota_usage'),
                ('2_2', 'equipment_product_report'),
                ('2_3', 'equipment_ownership_report'),
                ('2_4', 'collection_recycling_report')
            ]:
                flag_key = f'has_table_{table_num}'
                has_data = len(final_json.get(table_key, [])) > 0

                if final_json.get(flag_key) is None:
                    final_json[flag_key] = has_data
                    _logger.warning(f"{flag_key} was None - computed from data: {has_data}")
                elif final_json[flag_key] != has_data:
                    _logger.warning(f"{flag_key} mismatch: AI said {final_json[flag_key]}, data says {has_data}. Using data.")
                    final_json[flag_key] = has_data

            # Validate capacity flags
            if final_json.get('is_capacity_merged_table_2_2') is None:
                final_json['is_capacity_merged_table_2_2'] = self._detect_capacity_merge_flag(
                    final_json.get('equipment_product_report', [])
                )
                _logger.warning("is_capacity_merged_table_2_2 was None - detected from data")

            if final_json.get('is_capacity_merged_table_2_3') is None:
                final_json['is_capacity_merged_table_2_3'] = self._detect_capacity_merge_flag(
                    final_json.get('equipment_ownership_report', [])
                )
                _logger.warning("is_capacity_merged_table_2_3 was None - detected from data")

        return final_json

    def _detect_capacity_merge_flag(self, table_rows):
        """
        Detect if capacity columns are merged by analyzing actual data

        Logic:
        - If ANY row has 'capacity' field populated → merged (True)
        - If ANY row has 'cooling_capacity' OR 'power_capacity' → separate (False)
        - If no rows with capacity data → default to True (merged format is more common)

        Args:
            table_rows (list): List of table row dicts

        Returns:
            bool: True if merged, False if separate
        """
        has_merged = False
        has_separate = False

        for row in table_rows:
            if row.get('is_title'):
                continue

            # Check if merged capacity exists
            if row.get('capacity'):
                has_merged = True

            # Check if separate capacities exist
            if row.get('cooling_capacity') or row.get('power_capacity'):
                has_separate = True

        # Prioritize actual data presence
        if has_merged and not has_separate:
            return True  # Merged format
        elif has_separate and not has_merged:
            return False  # Separate format
        elif has_merged and has_separate:
            # Conflict - both formats present (shouldn't happen, but default to merged)
            _logger.warning("Capacity data conflict: both merged and separate fields populated")
            return True
        else:
            # No capacity data at all - default to True (merged is more common in Vietnamese forms)
            return True

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
