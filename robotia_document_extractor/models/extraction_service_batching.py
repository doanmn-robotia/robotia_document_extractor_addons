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

## ACTIVITY FIELD EXTRACTION (DETAILED)

**WHERE**: Activity fields are usually on the FIRST PAGE of the form, near organization info section.

**VISUAL FORMAT**: Typically presented as checkboxes:
```
LĨNH VỰC HOẠT ĐỘNG (chọn các mục tương ứng):
☐ Sản xuất chất được kiểm soát
☐ Nhập khẩu chất được kiểm soát
☐ Xuất khẩu chất được kiểm soát
☐ Sản xuất thiết bị chứa chất được kiểm soát
☐ Nhập khẩu thiết bị chứa chất được kiểm soát
☐ Sở hữu máy điều hòa không khí
☐ Sở hữu thiết bị lạnh
☐ Thu gom, tái chế, tiêu hủy chất được kiểm soát
```

**HOW TO IDENTIFY CHECKED BOXES:**
1. **Visual marks**:
   - ✓ (checkmark)
   - X (X mark)
   - ✔ (heavy checkmark)
   - Filled/shaded box (☑)
   - Circled text (text with circle around it)
   - Underlined text

2. **Handwritten marks**:
   - Hand-drawn checkmark (even if messy)
   - Hand-drawn X
   - Pen mark inside box

3. **NOT checked** (ignore these):
   - Empty box: ☐
   - Faint/gray placeholder checkbox
   - No mark at all

**EXTRACTION LOGIC:**
For each checked activity field, add the corresponding CODE to `activity_field_codes` array:

| Vietnamese Text (if checked) | Code to Extract |
|------------------------------|-----------------|
| "Sản xuất chất..." | "production" |
| "Nhập khẩu chất..." | "import" |
| "Xuất khẩu chất..." | "export" |
| "Sản xuất thiết bị..." | "equipment_production" |
| "Nhập khẩu thiết bị..." | "equipment_import" |
| "Sở hữu máy điều hòa..." | "ac_ownership" |
| "Sở hữu thiết bị lạnh..." | "refrigeration_ownership" |
| "Thu gom, tái chế..." | "collection_recycling" |

**Example extraction**:
If checkmarks next to:
- "Sản xuất chất được kiểm soát" ✓
- "Sở hữu máy điều hòa không khí" ✓

Then extract:
```json
"activity_field_codes": ["production", "ac_ownership"]
```

**CROSS-VALIDATION WITH TABLES:**
- If "production", "import", or "export" checked → expect Table 1.1 data
- If "equipment_production" or "equipment_import" checked → expect Table 1.2 data
- If "ac_ownership" or "refrigeration_ownership" checked → expect Table 1.3 data
- If "collection_recycling" checked → expect Table 1.4 data

Use this to double-check your has_table_X_Y flags.

## TABLE EXTRACTION QUALITY RULES

**EXTRACT ALL DATA ROWS:**
When you see a table section (title row), extract:
1. The title row itself (is_title=true)
2. **ALL data rows under that section** (is_title=false)

**CRITICAL**: Do not extract ONLY title rows!

**Example - WRONG extraction (only titles)**:
```json
[
  {{"is_title": true, "substance_name": "Sản xuất chất được kiểm soát"}},
  {{"is_title": true, "substance_name": "Nhập khẩu chất được kiểm soát"}}
]
```

**Example - CORRECT extraction (titles + data)**:
```json
[
  {{"is_title": true, "substance_name": "Sản xuất chất được kiểm soát"}},
  {{"is_title": false, "substance_name": "HFC-134a", "year_1_quantity_kg": 100}},
  {{"is_title": false, "substance_name": "R-410A", "year_1_quantity_kg": 200}},
  {{"is_title": true, "substance_name": "Nhập khẩu chất được kiểm soát"}},
  {{"is_title": false, "substance_name": "HFC-32", "year_1_quantity_kg": 50}}
]
```

**SKIP PLACEHOLDER/SUMMARY ROWS:**
Do NOT extract these types of rows:
- **Summary rows**: "Tổng", "Tổng cộng", "Total", "Cộng"
- **Placeholder substances**: "HFC...", "HFC-xxx", "R-xxx", "(Tên chất)"
- **Example rows**: Rows with "Ví dụ:", "VD:", markers
- **Instruction rows**: "Ghi rõ...", "Điền vào đây", "[placeholder text]"
- **Empty template rows**: Rows with only borders, no actual data

**Recognition patterns**:
- Summary rows: Usually at bottom of section, contains totaling text
- Placeholder: Contains ellipsis (...), xxx, or bracketed text
- If substance_name contains "..." or brackets → SKIP
- If entire row is template/instruction → SKIP

**Example - Substance name analysis**:
- "HFC-134a" → ✅ EXTRACT (real substance)
- "R-410A" → ✅ EXTRACT (real substance)
- "HFC..." → ❌ SKIP (placeholder)
- "HFC-xxx" → ❌ SKIP (placeholder)
- "(Tên chất)" → ❌ SKIP (instruction)
- "Tổng" → ❌ SKIP (summary row)

## ⚠️ CRITICAL: NUMBER LINE WRAP IN TABLE CELLS ⚠️

**PROBLEM**: Numbers in table cells can wrap to multiple lines, causing data loss if not handled correctly.

**Common scenarios**:
1. **Trailing zeros wrap**:
   ```
   Cell content appears as:
   Line 1: "12600"
   Line 2: "0"

   WRONG extraction: 12600 (missing the zero!)
   CORRECT extraction: 126000 (concatenate: "12600" + "0")
   ```

2. **Large numbers wrap**:
   ```
   Cell content appears as:
   Line 1: "300.0"
   Line 2: "00"

   WRONG extraction: 300.0 (missing "00"!)
   CORRECT extraction: 300000 (concatenate: "300.0" + "00")
   ```

3. **Multi-line numbers**:
   ```
   Cell content appears as:
   Line 1: "1"
   Line 2: "234"
   Line 3: "567"

   WRONG extraction: 1 or 234 (partial!)
   CORRECT extraction: 1234567 (full concatenation)
   ```

**EXTRACTION RULES:**
1. **ALWAYS check if cell has multiple lines** before parsing numbers
2. **Concatenate ALL lines in the cell** first, then parse as a single number
3. **Look for wrapped digits**: Single digits or digit groups on separate lines = likely wrapped
4. **Visual clues**:
   - Small font or narrow column → high chance of wrapping
   - Isolated digits (especially zeros) below main number → wrapped content
   - Numbers that seem too small compared to context → missing digits

**Step-by-step process**:
```
1. Read the entire cell (all lines)
2. Check: Does it contain multiple lines with only digits?
3. If YES: Concatenate all lines (remove line breaks, keep digits)
4. Parse the concatenated string as number
5. Validate: Does the result make sense in context?
```

**Examples**:

**Example 1 - Trailing zero wrap**:
```
PDF cell shows:
┌─────────┐
│ 12600   │
│ 0       │
└─────────┘

AI should read: "12600" + "0" = "126000"
Extract as: 126000
```

**Example 2 - Decimal wrap**:
```
PDF cell shows:
┌─────────┐
│ 45.     │
│ 50      │
└─────────┘

AI should read: "45." + "50" = "45.50"
Extract as: 45.5 or 45.50
```

**Example 3 - Full number wrap**:
```
PDF cell shows:
┌─────────┐
│ 999     │
│ 888     │
│ 777     │
└─────────┘

AI should read: "999" + "888" + "777" = "999888777"
Extract as: 999888777
```

**VALIDATION CHECK:**
After extracting numbers, ask yourself:
- Does this number make sense for this field (quantity, CO2e, etc.)?
- Is it suspiciously small (e.g., 126 kg when similar substances show 100000+ kg)?
- Are there orphaned digits below the number in the cell?

If suspicious → Re-check the cell for wrapped content!

**CRITICAL**: This applies to ALL numeric fields in tables:
- Quantities (kg, tons)
- CO2 equivalent values
- Quotas
- Prices
- Equipment quantities
- ANY numeric data in table cells

## ⚠️ CRITICAL: ROW CONTINUATION ACROSS PAGES ⚠️

**PROBLEM**: A table row can be split across page boundaries when it reaches the end of a page.

**How it happens in PDF structure:**
```
Page 1 (ends mid-row):
┌──────────┬────────┬────────┬────────┐
│ HFC-134a │ 100.5  │ 200.3  │        │ ← Row incomplete (cut off at page end)
└──────────┴────────┴────────┴────────┘
                                    [Page 1 ends here]

Page 2 (continuation):
┌────────┬─────────┐
│ 150.2  │ 150.0   │ ← Continuation of HFC-134a row from page 1
├────────┼─────────┤
│ R-410A │ 300.0   │ ← New complete row
```

**EXTRACTION CHALLENGE:**
- Page 1 shows: HFC-134a with partial data (only first 2 columns)
- Page 2 shows: Numbers that look like a new row BUT are actually continuation

**HOW TO DETECT ROW CONTINUATION:**

1. **Visual clues on Page N (end of page)**:
   - Row appears incomplete (missing columns compared to header)
   - Row ends at page boundary (bottom edge)
   - No closing border or section break
   - Uneven number of filled cells compared to other rows

2. **Visual clues on Page N+1 (start of page)**:
   - Starts with partial row (no substance name or row identifier)
   - Starts with middle/end columns only
   - First line has numbers but no context
   - No table header repeated

**EXTRACTION STRATEGY:**

**For BATCH extraction (you're processing multiple pages in one batch):**
```
IF page P shows incomplete row at bottom AND page P+1 shows continuation:
  → Merge them into ONE row in the JSON
  → Use substance_name from page P
  → Combine all column data from both pages
  → Single sequence number for the merged row
```

**For CROSS-BATCH continuation (row split across batches):**
```
Remember context from previous batch:
- Did previous batch end with incomplete row?
- What was the substance_name and sequence?
- Which columns were already filled?

If current batch starts with continuation:
- Extract the continuation data
- Mark clearly in JSON: This continues from previous batch
- Include substance_name from memory
- Use same sequence number
```

**EXAMPLE - Correct handling:**

**Scenario**: Row for "HFC-134a" is split between page 3 and page 4

**Page 3 extraction** (incomplete row at bottom):
```json
{{
  "page": 3,
  "substance_usage": [
    // ... other complete rows ...
    {{
      "sequence": 15,
      "is_title": false,
      "substance_name": "HFC-134a",
      "usage_type": "production",
      "year_1_quantity_kg": 100.5,
      "year_2_quantity_kg": 200.3,
      "year_3_quantity_kg": null,  // Missing - row incomplete
      "avg_quantity_kg": null       // Missing - row incomplete
    }}
  ]
}}
```

**Page 4 extraction** (continuation at top):
```json
{{
  "page": 4,
  "substance_usage": [
    {{
      "sequence": 15,  // SAME sequence as page 3
      "is_title": false,
      "substance_name": "HFC-134a",  // Remembered from page 3
      "usage_type": "production",
      "year_1_quantity_kg": null,  // Already in page 3
      "year_2_quantity_kg": null,  // Already in page 3
      "year_3_quantity_kg": 150.2, // From continuation
      "avg_quantity_kg": 150.0      // From continuation
    }}
  ]
}}
```

**After deduplication by sequence**:
Python will merge these into ONE complete row with all data.

**CRITICAL RULES:**
1. **Use context memory** - remember incomplete rows from previous pages/batches
2. **Same sequence number** - continuation uses SAME sequence as original
3. **Same substance_name** - even if not visible on continuation page
4. **Fill missing columns** - continuation provides the missing data
5. **Check page boundaries** - rows at bottom of page may be incomplete
6. **Validate completeness** - does the row have all expected columns?

**When in doubt:**
- Look at table structure: How many columns should this table have?
- Check if row at page bottom is incomplete
- Check if next page starts with orphaned data
- Use sequence numbers to track and merge

## ⚠️ CRITICAL: NUMBER AND TEXT RECOGNITION ACCURACY ⚠️

**PROBLEM**: Similar-looking characters can be misread, especially with poor scan quality, small fonts, or handwriting.

**COMMON MISREADING PAIRS:**

**Numbers that look similar:**
- **0 (zero) vs O (letter O)**: "100" vs "1OO" or "10O"
- **1 (one) vs l (lowercase L) vs I (uppercase i)**: "100" vs "l00" or "I00"
- **2 vs Z**: "250" vs "Z50"
- **5 vs S**: "500" vs "S00"
- **6 vs b**: "600" vs "b00"
- **8 vs B**: "800" vs "B00"
- **9 vs g**: "900" vs "g00"

**Punctuation:**
- **.  (period) vs , (comma)**: "1.5" vs "1,5"
- **. (period) vs ° (degree symbol)**

**VALIDATION RULES:**

1. **Context check**:
   ```
   IF field expects number (quantity_kg, quota_kg, etc.):
     → Result MUST be pure digits (0-9) and decimal point only
     → NO letters (O, l, I, S, B, g, etc.)

   IF you see letter in number field:
     → WRONG! Misread character
     → Re-examine the image carefully
   ```

2. **Range check**:
   ```
   Example: year_1_quantity_kg field
   - Seeing "1OO.5" → Likely "100.5" (O misread as 0)
   - Seeing "S00" → Likely "500" (S misread as 5)
   - Seeing "l234" → Likely "1234" (l misread as 1)
   ```

3. **Pattern check**:
   ```
   In Vietnamese forms:
   - Years: Should be 20XX (2020-2030 range)
     - "2O24" → Wrong! Should be "2024"
     - "2Ol9" → Wrong! Should be "2019"

   - Quantities: Usually large numbers (thousands)
     - "lOOOO" → Wrong! Should be "10000"
     - "5OO" → Wrong! Should be "500"
   ```

4. **Consistency check**:
   ```
   Compare with similar fields:
   - If year_1 = 2022, year_2 should be ~2023 (not 2O23)
   - If substance A has 1000 kg, similar substance shouldn't have "lOOO" kg
   ```

**CAREFUL EXAMINATION REQUIRED FOR:**

1. **Small fonts**: Zoom in mentally, examine each digit
2. **Handwritten numbers**: Look at stroke patterns:
   - "0" has continuous loop, "O" may have gap
   - "1" is single stroke, "l" may have serif
3. **Degraded scans**: Low resolution, faded ink
   - Look at surrounding characters for context
   - Compare with similar numbers elsewhere
4. **Narrow columns**: Characters may be squeezed
   - Distinguish "1" from "l" from "I"
   - Check digit spacing

**SELF-VALIDATION QUESTIONS:**

Before finalizing extraction, ask yourself:
1. ✓ Are all numeric fields pure numbers (no letters)?
2. ✓ Do years fall in reasonable range (2020-2030)?
3. ✓ Do quantities make sense (not mixing 0/O or 1/l)?
4. ✓ Are similar values consistent across rows?
5. ✓ Did I double-check small or unclear characters?

**EXAMPLE - Wrong vs Right:**

**WRONG extraction**:
```json
{{
  "substance_name": "HFC-134a",
  "year_1_quantity_kg": "1OO.5",     // ❌ Letter O instead of zero
  "year_2_quantity_kg": "2OO.3",     // ❌ Letter O instead of zero
  "year": "2O24"                      // ❌ Letter O instead of zero
}}
```

**CORRECT extraction**:
```json
{{
  "substance_name": "HFC-134a",
  "year_1_quantity_kg": 100.5,       // ✅ Pure number
  "year_2_quantity_kg": 200.3,       // ✅ Pure number
  "year": 2024                        // ✅ Pure number
}}
```

**CRITICAL**: If you're unsure about a character:
- Zoom in on the image
- Compare with same character elsewhere in document
- Check if result makes sense in context
- When truly unclear → set to null rather than guess wrong

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

## ACTIVITY FIELD EXTRACTION (DETAILED)

**WHERE**: Activity fields are usually on the FIRST PAGE of the form, near organization info section.

**VISUAL FORMAT**: Typically presented as checkboxes:
```
LĨNH VỰC HOẠT ĐỘNG (chọn các mục tương ứng):
☐ Sản xuất chất được kiểm soát
☐ Nhập khẩu chất được kiểm soát
☐ Xuất khẩu chất được kiểm soát
☐ Sản xuất thiết bị chứa chất được kiểm soát
☐ Nhập khẩu thiết bị chứa chất được kiểm soát
☐ Sở hữu máy điều hòa không khí
☐ Sở hữu thiết bị lạnh
☐ Thu gom, tái chế, tiêu hủy chất được kiểm soát
```

**HOW TO IDENTIFY CHECKED BOXES:**
1. **Visual marks**:
   - ✓ (checkmark)
   - X (X mark)
   - ✔ (heavy checkmark)
   - Filled/shaded box (☑)
   - Circled text (text with circle around it)
   - Underlined text

2. **Handwritten marks**:
   - Hand-drawn checkmark (even if messy)
   - Hand-drawn X
   - Pen mark inside box

3. **NOT checked** (ignore these):
   - Empty box: ☐
   - Faint/gray placeholder checkbox
   - No mark at all

**EXTRACTION LOGIC:**
For each checked activity field, add the corresponding CODE to `activity_field_codes` array:

| Vietnamese Text (if checked) | Code to Extract |
|------------------------------|-----------------|
| "Sản xuất chất..." | "production" |
| "Nhập khẩu chất..." | "import" |
| "Xuất khẩu chất..." | "export" |
| "Sản xuất thiết bị..." | "equipment_production" |
| "Nhập khẩu thiết bị..." | "equipment_import" |
| "Sở hữu máy điều hòa..." | "ac_ownership" |
| "Sở hữu thiết bị lạnh..." | "refrigeration_ownership" |
| "Thu gom, tái chế..." | "collection_recycling" |

**Example extraction**:
If checkmarks next to:
- "Sản xuất chất được kiểm soát" ✓
- "Sở hữu máy điều hòa không khí" ✓

Then extract:
```json
"activity_field_codes": ["production", "ac_ownership"]
```

**CROSS-VALIDATION WITH TABLES:**
- If "production", "import", or "export" checked → expect Table 2.1 data
- If "equipment_production" or "equipment_import" checked → expect Table 2.2 data
- If "ac_ownership" or "refrigeration_ownership" checked → expect Table 2.3 data
- If "collection_recycling" checked → expect Table 2.4 data

Use this to double-check your has_table_X_Y flags.

## TABLE EXTRACTION QUALITY RULES

**EXTRACT ALL DATA ROWS:**
When you see a table section (title row), extract:
1. The title row itself (is_title=true)
2. **ALL data rows under that section** (is_title=false)

**CRITICAL**: Do not extract ONLY title rows!

**Example - WRONG extraction (only titles)**:
```json
[
  {{"is_title": true, "substance_name": "Sản xuất"}},
  {{"is_title": true, "substance_name": "Nhập khẩu"}}
]
```

**Example - CORRECT extraction (titles + data)**:
```json
[
  {{"is_title": true, "substance_name": "Sản xuất", "usage_type": "production"}},
  {{"is_title": false, "substance_name": "HFC-134a", "total_quota_kg": 100}},
  {{"is_title": false, "substance_name": "R-410A", "total_quota_kg": 200}},
  {{"is_title": true, "substance_name": "Nhập khẩu", "usage_type": "import"}},
  {{"is_title": false, "substance_name": "HFC-32", "total_quota_kg": 50}}
]
```

**SKIP PLACEHOLDER/SUMMARY ROWS:**
Do NOT extract these types of rows:
- **Summary rows**: "Tổng", "Tổng cộng", "Total", "Cộng"
- **Placeholder substances**: "HFC...", "HFC-xxx", "R-xxx", "(Tên chất)"
- **Example rows**: Rows with "Ví dụ:", "VD:", markers
- **Instruction rows**: "Ghi rõ...", "Điền vào đây", "[placeholder text]"
- **Empty template rows**: Rows with only borders, no actual data

**Recognition patterns**:
- Summary rows: Usually at bottom of section, contains totaling text
- Placeholder: Contains ellipsis (...), xxx, or bracketed text
- If substance_name contains "..." or brackets → SKIP
- If entire row is template/instruction → SKIP

**Example - Substance name analysis**:
- "HFC-134a" → ✅ EXTRACT (real substance)
- "R-410A" → ✅ EXTRACT (real substance)
- "HFC..." → ❌ SKIP (placeholder)
- "HFC-xxx" → ❌ SKIP (placeholder)
- "(Tên chất)" → ❌ SKIP (instruction)
- "Tổng" → ❌ SKIP (summary row)

**IMPORTANT NOTE FOR FORM 02:**
- Table 2.4 (Collection/Recycling Report) has NO title rows - all rows are data rows
- For Tables 2.1, 2.2, 2.3: Apply title row logic as above

## ⚠️ CRITICAL: NUMBER LINE WRAP IN TABLE CELLS ⚠️

**PROBLEM**: Numbers in table cells can wrap to multiple lines, causing data loss if not handled correctly.

**Common scenarios**:
1. **Trailing zeros wrap**:
   ```
   Cell content appears as:
   Line 1: "12600"
   Line 2: "0"

   WRONG extraction: 12600 (missing the zero!)
   CORRECT extraction: 126000 (concatenate: "12600" + "0")
   ```

2. **Large numbers wrap**:
   ```
   Cell content appears as:
   Line 1: "300.0"
   Line 2: "00"

   WRONG extraction: 300.0 (missing "00"!)
   CORRECT extraction: 300000 (concatenate: "300.0" + "00")
   ```

3. **Multi-line numbers**:
   ```
   Cell content appears as:
   Line 1: "1"
   Line 2: "234"
   Line 3: "567"

   WRONG extraction: 1 or 234 (partial!)
   CORRECT extraction: 1234567 (full concatenation)
   ```

**EXTRACTION RULES:**
1. **ALWAYS check if cell has multiple lines** before parsing numbers
2. **Concatenate ALL lines in the cell** first, then parse as a single number
3. **Look for wrapped digits**: Single digits or digit groups on separate lines = likely wrapped
4. **Visual clues**:
   - Small font or narrow column → high chance of wrapping
   - Isolated digits (especially zeros) below main number → wrapped content
   - Numbers that seem too small compared to context → missing digits

**Step-by-step process**:
```
1. Read the entire cell (all lines)
2. Check: Does it contain multiple lines with only digits?
3. If YES: Concatenate all lines (remove line breaks, keep digits)
4. Parse the concatenated string as number
5. Validate: Does the result make sense in context?
```

**Examples**:

**Example 1 - Trailing zero wrap**:
```
PDF cell shows:
┌─────────┐
│ 12600   │
│ 0       │
└─────────┘

AI should read: "12600" + "0" = "126000"
Extract as: 126000
```

**Example 2 - Decimal wrap**:
```
PDF cell shows:
┌─────────┐
│ 45.     │
│ 50      │
└─────────┘

AI should read: "45." + "50" = "45.50"
Extract as: 45.5 or 45.50
```

**Example 3 - Full number wrap**:
```
PDF cell shows:
┌─────────┐
│ 999     │
│ 888     │
│ 777     │
└─────────┘

AI should read: "999" + "888" + "777" = "999888777"
Extract as: 999888777
```

**VALIDATION CHECK:**
After extracting numbers, ask yourself:
- Does this number make sense for this field (quantity, CO2e, quota, price, etc.)?
- Is it suspiciously small (e.g., 126 kg when similar substances show 100000+ kg)?
- Are there orphaned digits below the number in the cell?

If suspicious → Re-check the cell for wrapped content!

**CRITICAL**: This applies to ALL numeric fields in Form 02 tables:
- **Table 2.1**: allocated_quota_kg, adjusted_quota_kg, total_quota_kg, CO2 values, average_price, next_year_quota
- **Table 2.2**: quantity, substance_quantity_per_unit
- **Table 2.3**: equipment_quantity, refill_frequency, substance_quantity_per_refill
- **Table 2.4**: collection_quantity_kg, reuse_quantity_kg, recycle_quantity_kg, disposal_quantity_kg
- **ANY numeric data in table cells**

## ⚠️ CRITICAL: ROW CONTINUATION ACROSS PAGES ⚠️

**PROBLEM**: A table row can be split across page boundaries when it reaches the end of a page.

**How it happens in PDF structure:**
```
Page 1 (ends mid-row):
┌──────────┬────────┬────────┬────────┐
│ HFC-134a │ 500.0  │ 600.0  │        │ ← Row incomplete (cut off at page end)
└──────────┴────────┴────────┴────────┘
                                    [Page 1 ends here]

Page 2 (continuation):
┌────────┬─────────┐
│ 550.0  │ 12.50   │ ← Continuation of HFC-134a row from page 1
├────────┼─────────┤
│ R-410A │ 700.0   │ ← New complete row
```

**EXTRACTION CHALLENGE:**
- Page 1 shows: HFC-134a with partial data (only first 2-3 columns)
- Page 2 shows: Numbers that look like a new row BUT are actually continuation

**HOW TO DETECT ROW CONTINUATION:**

1. **Visual clues on Page N (end of page)**:
   - Row appears incomplete (missing columns compared to header)
   - Row ends at page boundary (bottom edge)
   - No closing border or section break
   - Uneven number of filled cells compared to other rows

2. **Visual clues on Page N+1 (start of page)**:
   - Starts with partial row (no substance name or row identifier)
   - Starts with middle/end columns only
   - First line has numbers but no context
   - No table header repeated

**EXTRACTION STRATEGY:**

**For BATCH extraction (you're processing multiple pages in one batch):**
```
IF page P shows incomplete row at bottom AND page P+1 shows continuation:
  → Merge them into ONE row in the JSON
  → Use substance_name from page P
  → Combine all column data from both pages
  → Single sequence number for the merged row
```

**For CROSS-BATCH continuation (row split across batches):**
```
Remember context from previous batch:
- Did previous batch end with incomplete row?
- What was the substance_name and sequence?
- Which columns were already filled?

If current batch starts with continuation:
- Extract the continuation data
- Mark clearly in JSON: This continues from previous batch
- Include substance_name from memory
- Use same sequence number
```

**EXAMPLE - Correct handling for Table 2.1:**

**Scenario**: Row for "HFC-134a" is split between page 2 and page 3

**Page 2 extraction** (incomplete row at bottom):
```json
{{
  "page": 2,
  "quota_usage": [
    // ... other complete rows ...
    {{
      "sequence": 8,
      "is_title": false,
      "substance_name": "HFC-134a",
      "usage_type": "import",
      "hs_code": "2903.39.19",
      "allocated_quota_kg": 5000.0,
      "adjusted_quota_kg": null,      // Missing - row incomplete
      "total_quota_kg": null,          // Missing - row incomplete
      "average_price": null,           // Missing - row incomplete
      "next_year_quota_kg": null       // Missing - row incomplete
    }}
  ]
}}
```

**Page 3 extraction** (continuation at top):
```json
{{
  "page": 3,
  "quota_usage": [
    {{
      "sequence": 8,  // SAME sequence as page 2
      "is_title": false,
      "substance_name": "HFC-134a",  // Remembered from page 2
      "usage_type": "import",
      "hs_code": null,                // Already in page 2
      "allocated_quota_kg": null,     // Already in page 2
      "adjusted_quota_kg": 1000.0,    // From continuation
      "total_quota_kg": 6000.0,       // From continuation
      "average_price": 12.50,         // From continuation
      "next_year_quota_kg": 7000.0    // From continuation
    }}
  ]
}}
```

**After deduplication by sequence**:
Python will merge these into ONE complete row with all data.

**CRITICAL RULES:**
1. **Use context memory** - remember incomplete rows from previous pages/batches
2. **Same sequence number** - continuation uses SAME sequence as original
3. **Same substance_name** - even if not visible on continuation page
4. **Fill missing columns** - continuation provides the missing data
5. **Check page boundaries** - rows at bottom of page may be incomplete
6. **Validate completeness** - does the row have all expected columns?

**When in doubt:**
- Look at table structure: How many columns should this table have?
- Check if row at page bottom is incomplete
- Check if next page starts with orphaned data
- Use sequence numbers to track and merge

## ⚠️ CRITICAL: NUMBER AND TEXT RECOGNITION ACCURACY ⚠️

**PROBLEM**: Similar-looking characters can be misread, especially with poor scan quality, small fonts, or handwriting.

**COMMON MISREADING PAIRS:**

**Numbers that look similar:**
- **0 (zero) vs O (letter O)**: "100" vs "1OO" or "10O"
- **1 (one) vs l (lowercase L) vs I (uppercase i)**: "100" vs "l00" or "I00"
- **2 vs Z**: "250" vs "Z50"
- **5 vs S**: "500" vs "S00"
- **6 vs b**: "600" vs "b00"
- **8 vs B**: "800" vs "B00"
- **9 vs g**: "900" vs "g00"

**Punctuation:**
- **.  (period) vs , (comma)**: "1.5" vs "1,5"
- **. (period) vs ° (degree symbol)**

**VALIDATION RULES:**

1. **Context check**:
   ```
   IF field expects number (quota_kg, quantity_kg, price, etc.):
     → Result MUST be pure digits (0-9) and decimal point only
     → NO letters (O, l, I, S, B, g, etc.)

   IF you see letter in number field:
     → WRONG! Misread character
     → Re-examine the image carefully
   ```

2. **Range check**:
   ```
   Example: allocated_quota_kg field
   - Seeing "5OOO.0" → Likely "5000.0" (O misread as 0)
   - Seeing "lOOO" → Likely "1000" (l and O misread)
   - Seeing "S00.5" → Likely "500.5" (S misread as 5)
   ```

3. **Pattern check**:
   ```
   In Vietnamese forms:
   - Years: Should be 20XX (2020-2030 range)
     - "2O24" → Wrong! Should be "2024"
     - "2Ol9" → Wrong! Should be "2019"

   - Quotas: Usually large numbers (thousands)
     - "lOOOO" → Wrong! Should be "10000"
     - "5OOO" → Wrong! Should be "5000"

   - Prices: Usually reasonable (1-100 USD range)
     - "lO.5" → Wrong! Should be "10.5"
     - "2O.OO" → Wrong! Should be "20.00"
   ```

4. **Consistency check**:
   ```
   Compare with similar fields:
   - If year_1 = 2022, year_2 should be ~2023 (not 2O23)
   - If substance A has 1000 kg quota, similar substance shouldn't have "lOOO" kg
   - If average_price is 10.5 for one substance, similar shouldn't be "lO.5"
   ```

**CAREFUL EXAMINATION REQUIRED FOR:**

1. **Small fonts**: Zoom in mentally, examine each digit
2. **Handwritten numbers**: Look at stroke patterns:
   - "0" has continuous loop, "O" may have gap
   - "1" is single stroke, "l" may have serif
3. **Degraded scans**: Low resolution, faded ink
   - Look at surrounding characters for context
   - Compare with similar numbers elsewhere
4. **Narrow columns**: Characters may be squeezed
   - Distinguish "1" from "l" from "I"
   - Check digit spacing
5. **Table 2.1 specific**: Many numeric columns (quotas, CO2, prices)
   - Extra careful with large numbers (quota fields)
   - Decimal prices need precise reading

**SELF-VALIDATION QUESTIONS:**

Before finalizing extraction, ask yourself:
1. ✓ Are all numeric fields pure numbers (no letters)?
2. ✓ Do years fall in reasonable range (2020-2030)?
3. ✓ Do quotas/quantities make sense (not mixing 0/O or 1/l)?
4. ✓ Are prices reasonable (typically 1-100 USD)?
5. ✓ Are similar values consistent across rows?
6. ✓ Did I double-check small or unclear characters?

**EXAMPLE - Wrong vs Right:**

**WRONG extraction**:
```json
{{
  "substance_name": "HFC-134a",
  "allocated_quota_kg": "5OOO.O",    // ❌ Letters O instead of zeros
  "adjusted_quota_kg": "lOOO.O",     // ❌ Letter l and O
  "total_quota_kg": "6OOO.O",        // ❌ Letters O instead of zeros
  "average_price": "lO.5",           // ❌ Letter l instead of 1
  "year": "2O24"                      // ❌ Letter O instead of zero
}}
```

**CORRECT extraction**:
```json
{{
  "substance_name": "HFC-134a",
  "allocated_quota_kg": 5000.0,      // ✅ Pure number
  "adjusted_quota_kg": 1000.0,       // ✅ Pure number
  "total_quota_kg": 6000.0,          // ✅ Pure number
  "average_price": 10.5,             // ✅ Pure number
  "year": 2024                        // ✅ Pure number
}}
```

**CRITICAL**: If you're unsure about a character:
- Zoom in on the image
- Compare with same character elsewhere in document
- Check if result makes sense in context
- When truly unclear → set to null rather than guess wrong

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

## ⚠️ CRITICAL: UNDERSTANDING is_title FIELD ⚠️

**is_title is NOT the table header!**

is_title = true → **MERGED ROW** that acts as a **SECTION DIVIDER** within the table
is_title = false → **DATA ROW** with actual numerical/text data

**Example from Table 1.1 (Substance Usage):**

┌─────────────────────────────────────────┐
│ TABLE 1.1 HEADER (do not extract)      │  ← Table header (NOT a row)
├──────────┬──────┬──────┬──────┬────────┤
│ Chất     │ 2022 │ 2023 │ 2024 │ TB     │  ← Column headers (NOT a row)
├──────────┴──────┴──────┴──────┴────────┤
│ SECTION: Sản xuất chất được kiểm soát  │  ← is_title=TRUE (merged cell section)
├──────────┬──────┬──────┬──────┬────────┤
│ HFC-134a │ 100  │ 120  │ 110  │ 110    │  ← is_title=FALSE (data row)
│ R-410A   │ 200  │ 210  │ 205  │ 205    │  ← is_title=FALSE (data row)
├──────────┴──────┴──────┴──────┴────────┤
│ SECTION: Nhập khẩu chất được kiểm soát │  ← is_title=TRUE (merged cell section)
├──────────┬──────┬──────┬──────┬────────┤
│ HFC-32   │ 50   │ 60   │ 55   │ 55     │  ← is_title=FALSE (data row)
└──────────┴──────┴──────┴──────┴────────┘

**How to extract:**
```json
[
  {{
    "is_title": true,
    "substance_name": "Sản xuất chất được kiểm soát",  // Section title
    "usage_type": "production",
    // All other fields: null
  }},
  {{
    "is_title": false,
    "substance_name": "HFC-134a",  // Actual substance
    "usage_type": "production",
    "year_1_quantity_kg": 100,
    // ... data fields
  }},
  {{
    "is_title": true,
    "substance_name": "Nhập khẩu chất được kiểm soát",  // Section title
    "usage_type": "import",
    // All other fields: null
  }},
  {{
    "is_title": false,
    "substance_name": "HFC-32",
    "usage_type": "import",
    "year_1_quantity_kg": 50,
    // ... data fields
  }}
]
```

**Key Rules:**
1. Title rows have substance_name = section description (Vietnamese text)
2. Title rows have all numeric fields = null
3. Data rows have substance_name = standardized substance (from official list)
4. Sequence numbers continue across title and data rows

## 📄 TABLE CONTINUATION ACROSS PAGES

**Problem**: A table may span multiple pages. Page 2+ may NOT show the table header.

**How AI Should Handle This:**

1. **Use Context Memory** from previous batch:
   - Remember which table you were extracting
   - Remember table structure (column count, format)
   - Continue sequence numbers

2. **Recognition Patterns**:
   - If page starts with data rows (no header) → it's a continuation
   - Look at column structure: does it match previous table?
   - Check sequence: are row numbers continuing?

3. **Chat Memory is KEY**:
   - First batch: "I saw Table 1.1 starting with 3 rows"
   - Second batch: "I see rows continuing with same column structure → must be Table 1.1 continuation"
   - Keep extracting to same table array

4. **What if uncertain?**
   - Look at column count: Table 1.1 has ~8 columns
   - Look at content: substance names + numbers = likely Table 1.1
   - Look at section titles: "Sản xuất", "Nhập khẩu" = Table 1.1
   - Trust your context memory from previous batches!

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

## ⚠️ CRITICAL: UNDERSTANDING is_title FIELD ⚠️

**is_title is NOT the table header!**

is_title = true → **MERGED ROW** that acts as a **SECTION DIVIDER** within the table
is_title = false → **DATA ROW** with actual numerical/text data

**Example from Table 2.1 (Quota Usage):**

┌─────────────────────────────────────────┐
│ TABLE 2.1 HEADER (do not extract)      │  ← Table header (NOT a row)
├──────────┬──────┬──────┬──────┬────────┤
│ Chất     │ Cấp  │ Đã SD │ Còn │ HS    │  ← Column headers (NOT a row)
├──────────┴──────┴──────┴──────┴────────┤
│ SECTION: Sản xuất chất được kiểm soát  │  ← is_title=TRUE (merged cell section)
├──────────┬──────┬──────┬──────┬────────┤
│ HFC-134a │ 500  │ 400  │ 100  │ 3824  │  ← is_title=FALSE (data row)
│ R-410A   │ 600  │ 550  │ 50   │ 3824  │  ← is_title=FALSE (data row)
├──────────┴──────┴──────┴──────┴────────┤
│ SECTION: Nhập khẩu chất được kiểm soát │  ← is_title=TRUE (merged cell section)
├──────────┬──────┬──────┬──────┬────────┤
│ HFC-32   │ 300  │ 250  │ 50   │ 3824  │  ← is_title=FALSE (data row)
└──────────┴──────┴──────┴──────┴────────┘

**How to extract:**
```json
[
  {{
    "is_title": true,
    "substance_name": "Sản xuất chất được kiểm soát",  // Section title
    "usage_type": "production",
    // All other fields: null
  }},
  {{
    "is_title": false,
    "substance_name": "HFC-134a",  // Actual substance
    "usage_type": "production",
    "allocated_quota_kg": 500,
    // ... data fields
  }},
  {{
    "is_title": true,
    "substance_name": "Nhập khẩu chất được kiểm soát",  // Section title
    "usage_type": "import",
    // All other fields: null
  }},
  {{
    "is_title": false,
    "substance_name": "HFC-32",
    "usage_type": "import",
    "allocated_quota_kg": 300,
    // ... data fields
  }}
]
```

**Key Rules:**
1. Title rows have substance_name = section description (Vietnamese text)
2. Title rows have all numeric fields = null
3. Data rows have substance_name = standardized substance (from official list)
4. Sequence numbers continue across title and data rows
5. **Table 2.4 EXCEPTION**: NO is_title field (all rows are data rows)

## 📄 TABLE CONTINUATION ACROSS PAGES

**Problem**: A table may span multiple pages. Page 2+ may NOT show the table header.

**How AI Should Handle This:**

1. **Use Context Memory** from previous batch:
   - Remember which table you were extracting
   - Remember table structure (column count, format)
   - Continue sequence numbers

2. **Recognition Patterns**:
   - If page starts with data rows (no header) → it's a continuation
   - Look at column structure: does it match previous table?
   - Check sequence: are row numbers continuing?

3. **Chat Memory is KEY**:
   - First batch: "I saw Table 2.1 starting with 3 rows"
   - Second batch: "I see rows continuing with same column structure → must be Table 2.1 continuation"
   - Keep extracting to same table array

4. **What if uncertain?**
   - Look at column count: Table 2.1 has ~10 columns
   - Look at content: substance names + quota numbers = likely Table 2.1
   - Look at section titles: "Sản xuất", "Nhập khẩu" = Table 2.1
   - Trust your context memory from previous batches!

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

## ⚠️ CRITICAL: UNDERSTANDING is_title FIELD ⚠️

**is_title is NOT the table header!**

is_title = true → **MERGED ROW** that acts as a **SECTION DIVIDER** within the table
is_title = false → **DATA ROW** with actual numerical/text data

**Key Rules:**
1. Title rows have substance_name = section description (Vietnamese text)
2. Title rows have all numeric fields = null
3. Data rows have substance_name = standardized substance (from official list)
4. Sequence numbers continue across title and data rows

## 📄 TABLE CONTINUATION ACROSS PAGES

**Problem**: A table may span multiple pages. Page 2+ may NOT show the table header.

**How to Handle:**
1. Use context memory from previous batch
2. If page starts with data rows (no header) → it's a continuation
3. Continue sequence numbers
4. Trust your context memory from previous batches!

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

## ⚠️ CRITICAL: UNDERSTANDING is_title FIELD ⚠️

**is_title is NOT the table header!**

is_title = true → **MERGED ROW** that acts as a **SECTION DIVIDER** within the table
is_title = false → **DATA ROW** with actual numerical/text data

**Key Rules:**
1. Title rows have substance_name = section description (Vietnamese text)
2. Title rows have all numeric fields = null
3. Data rows have substance_name = standardized substance (from official list)
4. Sequence numbers continue across title and data rows
5. **Table 2.4 EXCEPTION**: NO is_title field (all rows are data rows)

## 📄 TABLE CONTINUATION ACROSS PAGES

**Problem**: A table may span multiple pages. Page 2+ may NOT show the table header.

**How to Handle:**
1. Use context memory from previous batch
2. If page starts with data rows (no header) → it's a continuation
3. Continue sequence numbers
4. Trust your context memory from previous batches!

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
