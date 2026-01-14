# -*- coding: utf-8 -*-

"""
Additional prompts for batch processing.

Provides critical reminders about:
- Year extraction from chat history (for metadata)
- Column alignment verification (for tables)
- Data accuracy validation (100% reliability requirement)
"""


def get_additional_prompt(category):
    """
    Get additional prompt instructions for specific category.

    These prompts emphasize CRITICAL requirements that need
    extra attention during batch processing:
    - Year field extraction (especially for metadata - review chat history)
    - Column alignment and data accuracy (for all tables)
    - Rethinking strategy for difficult cases

    Args:
        category (str): Category name (metadata, substance_usage, etc.)

    Returns:
        str: Additional prompt instructions for that category
    """

    # Map category to prompt function
    prompt_map = {
        'metadata': _get_metadata_additional_prompt,
        'substance_usage': _get_substance_usage_additional_prompt,
        'equipment_product': _get_equipment_product_additional_prompt,
        'equipment_ownership': _get_equipment_ownership_additional_prompt,
        'collection_recycling': _get_collection_recycling_additional_prompt,
        'quota_usage': _get_quota_usage_additional_prompt,
        'equipment_product_report': _get_equipment_product_report_additional_prompt,
        'equipment_ownership_report': _get_equipment_ownership_report_additional_prompt,
        'collection_recycling_report': _get_collection_recycling_report_additional_prompt,
    }

    prompt_func = prompt_map.get(category)
    if prompt_func:
        return prompt_func()

    # Default for unknown categories
    return _get_default_additional_prompt()


def _get_metadata_additional_prompt():
    """
    Additional prompts for metadata extraction.

    CRITICAL: Metadata is extracted LAST, so AI must review chat history
    to find year information from previously extracted tables.
    """
    return """

---

## ⚠️ CRITICAL REMINDERS FOR METADATA EXTRACTION

### 1. YEAR FIELD EXTRACTION - REVIEW CHAT HISTORY! (ABSOLUTELY CRITICAL!)

**IMPORTANT CONTEXT:**
- Metadata is extracted **LAST** in the processing pipeline
- Other tables (substance_usage, equipment_product, etc.) have already been extracted **BEFORE** this
- You must **REVIEW THE CHAT HISTORY** to find year information from those previously extracted tables

**EXTRACTION STRATEGY:**

**STEP 1: Review previous messages in chat history**
- Look for previously extracted categories (substance_usage, quota_usage, equipment_product, etc.)
- Check if any of those categories contain year information in their table headers

**STEP 2: Extract year based on table type found:**

**Option A: If "substance_usage" (Bảng 1.1) was extracted:**
- Bảng 1.1 has 3 year columns: year_1, year_2 (year), year_3
- Example from chat history: `"year_1": 2022, "year_2": 2023, "year_3": 2024`
- **Use year_2 as metadata `year`** → year = 2023

**Option B: If other tables were extracted (Bảng 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4):**
- These tables have single `year` field
- Example from chat history: `"year": 2024`
- **Use that year directly** → year = 2024

**Option C: If no tables with year found in chat history:**
- Look in current OCR markdown for text like:
  - "2. Báo cáo về tình hình sử dụng chất được kiểm soát trong năm 2024"
  - Table headers with year information
- Extract year from that text

**Option D: If year is unclear from all sources:**
- Set `year` to null

**WHAT `year` IS NOT:**
- ❌ NOT "Ngày nộp báo cáo" (submission date)
- ❌ NOT "Ngày ký" (signature date)
- ❌ NOT "Ngày lập báo cáo" (report creation date)
- ❌ NOT business license date
- ❌ NOT any date from signature section

**VALIDATION CHECKLIST:**

Before finalizing metadata, verify:
✓ Did I review chat history for previously extracted tables?
✓ Did I find year_1, year_2, year_3 from Bảng 1.1 (substance_usage)?
✓ Or did I find year from other tables (Bảng 1.2-1.4, 2.1-2.4)?
✓ Did I use year_2 (middle year) if Bảng 1.1 was found?
✓ Is the year value reasonable (2015-2030 range)?

**EXAMPLE SCENARIO:**

```
Chat history shows:
- Category "substance_usage" (Bảng 1.1) was extracted with:
  {
    "year_1": 2022,
    "year_2": 2023,
    "year_3": 2024,
    "substance_usage": [...]
  }

CORRECT metadata extraction:
{
  "year": 2023,  ← Use year_2 from Bảng 1.1
  "organization_name": "...",
  ...
}
```

### 2. OTHER METADATA FIELDS - VERIFICATION

**Organization Information:**
- organization_name: Must be specific (not placeholder like "Tên công ty")
- business_id: Must be "Mã số doanh nghiệp" (10-13 digits), NOT tax ID or license number

**Business License Date:**
- Use "Ngày đăng ký lần đầu" (FIRST registration date)
- ❌ IGNORE "Đăng ký thay đổi lần..." (renewal dates)
- Format: YYYY-MM-DD (convert from DD/MM/YYYY)

**Contact Information:**
- contact_state_code: Use province lookup table (VN-SG, VN-HN, etc.)
- contact_country_code: Always "VN" for Vietnamese addresses

### 3. ACTIVITY FIELD CODES

**Detection Priority:**
1. **PRIMARY**: Checkboxes in metadata section (if any are ticked)
2. **SECONDARY**: Infer from chat history - which tables were extracted?
   - If "substance_usage" with production/import/export → Add those codes
   - If "equipment_product" found → Add equipment_production/equipment_import
   - If "equipment_ownership" found → Add ac_ownership/refrigeration_ownership
   - If "collection_recycling" found → Add collection_recycling

### 4. RETHINK STRATEGY

**Before finalizing metadata:**
1. PAUSE and review entire chat history
2. Find all previously extracted categories
3. Identify year information from those categories
4. Apply year extraction rules above
5. If ANY field is unclear → Use null (NEVER guess!)

---
"""


def _get_substance_usage_additional_prompt():
    """Additional prompts for substance usage (Bảng 1.1) - Multi-year handling."""
    return """

---

## ⚠️ CRITICAL REMINDERS FOR SUBSTANCE USAGE (Bảng 1.1)

### 1. MULTI-YEAR EXTRACTION (year_1, year_2, year_3)

**Bảng 1.1 is SPECIAL** - It has 3 year columns:

**Column structure:**
- **Cột 1**: year_1 (năm quá khứ / past year)
- **Cột 2**: year_2 (năm hiện tại / current year) ← Đây là `year` chính
- **Cột 3**: year_3 (năm tương lai / future year)

**Header extraction example:**
```
| STT | Tên chất | Mã HS | 2022 (kg) | 2022 (CO2e) | 2023 (kg) | 2023 (CO2e) | 2024 (kg) | 2024 (CO2e) | Trung bình |
```

**EXTRACT:**
- year_1 = 2022 (cột 1)
- year_2 = 2023 (cột 2) ← Năm chính, sẽ được dùng cho metadata `year`
- year_3 = 2024 (cột 3)

### 2. COLUMN ALIGNMENT ACCURACY - 100% RELIABILITY REQUIRED!

**YÊU CẦU TUYỆT ĐỐI:** Dữ liệu phải khớp đúng cột, không được lệch!

**Common errors to ABSOLUTELY AVOID:**
❌ **Column shift**: Dữ liệu từ cột A xuất hiện ở cột B
❌ **Missing columns**: Bỏ sót một cột hoàn toàn
❌ **Wrong year assignment**: Dữ liệu year_1 bị gán vào year_2
❌ **Incomplete extraction**: Thiếu dữ liệu so với bảng gốc

**RETHINK PROCESS - VERIFY BEFORE EXTRACTION:**

**STEP 1: Analyze table structure**
1. Đếm tổng số cột trong header
2. Xác định vị trí chính xác của từng cột (STT, Tên chất, Mã HS, các cột năm)
3. Vẽ mental map: Cột 1 = STT, Cột 2 = Tên, Cột 3 = HS, Cột 4 = 2022 kg, ...

**STEP 2: For each data row**
1. Đếm tổng số ô dữ liệu trong hàng
2. Khớp từng ô với cột header theo **VỊ TRÍ** (position), không phải theo nội dung
3. Verify: Số ô dữ liệu = số cột header?
4. Double-check: Ô số 4 → Cột năm 1 (kg), Ô số 5 → Cột năm 1 (CO2e)

**STEP 3: Cross-validation**
- Check if CO2e ≈ kg × GWP (reasonable range)
- Check if numbers make sense (not negative, not unreasonably large)
- Check if substance names are consistent with database

**EXAMPLE - DETAILED VERIFICATION:**

```
Header row:
| [1] STT | [2] Tên chất | [3] Mã HS | [4] 2022 (kg) | [5] 2022 (CO2e) | [6] 2023 (kg) | [7] 2023 (CO2e) | [8] 2024 (kg) | [9] 2024 (CO2e) | [10] Trung bình (kg) | [11] Trung bình (CO2e) |

Data row:
| [1] 1 | [2] R-410A | [3] 2903.39 | [4] 100.5 | [5] 209.040 | [6] 120.0 | [7] 249.600 | [8] 150.0 | [9] 312.000 | [10] 123.5 | [11] 256.880 |

Verification checklist:
✓ Total cells = 11 (matches header)
✓ Cell [1] (position 1) → sequence = 1
✓ Cell [2] (position 2) → substance_name = "R-410A"
✓ Cell [3] (position 3) → hs_code = "2903.39"
✓ Cell [4] (position 4) → year_1_quantity_kg = 100.5
✓ Cell [5] (position 5) → year_1_quantity_co2 = 209.040
✓ Cell [6] (position 6) → year_2_quantity_kg = 120.0
✓ Cell [7] (position 7) → year_2_quantity_co2 = 249.600
✓ Cell [8] (position 8) → year_3_quantity_kg = 150.0
✓ Cell [9] (position 9) → year_3_quantity_co2 = 312.000
✓ Cell [10] (position 10) → avg_quantity_kg = 123.5
✓ Cell [11] (position 11) → avg_quantity_co2 = 256.880

Cross-validation:
✓ 100.5 × 2.08 (GWP) ≈ 209.040 ✓ (matches!)
✓ 120.0 × 2.08 ≈ 249.600 ✓ (matches!)
✓ 150.0 × 2.08 ≈ 312.000 ✓ (matches!)

RESULT: Data is accurate, proceed with extraction
```

### 3. HANDLING DIFFICULT CASES

**If you encounter ANY of these:**
- Merged cells spanning multiple columns
- Unclear column boundaries (faded lines)
- Blurry or low-quality numbers
- Line wraps within cells (number split across lines)
- Inconsistent column count between rows

**MANDATORY ACTION - RETHINK:**

1. **STOP** extraction immediately
2. **RE-ANALYZE** the problematic section carefully:
   - Re-count columns
   - Check if there's a pattern in adjacent rows
   - Look for visual cues (borders, alignment)
3. **USE CONTEXT** from other rows:
   - Compare with previous/next rows
   - Check if column structure is consistent
4. **MAKE DECISION:**
   - If confident (≥90%) → Extract with verification
   - If uncertain → Use null for that specific cell
   - NEVER shift columns to "make it fit"
   - NEVER guess or auto-fill

**EXAMPLE - LINE WRAP HANDLING:**

```
Problematic cell (line wrap):
| 120  |
| .50  |

Analysis:
✓ Both lines within same cell border
✓ Second line has only decimal digits
✓ Second line is right-aligned
→ CONCLUSION: This is line wrap
→ CORRECT EXTRACTION: 120.50

But if:
| 120  | (in column 5)
| 50   | (unclear if same cell or next cell)

Analysis:
✗ Cell boundary unclear
✗ Could be 120.50 OR could be two separate values (120 and 50)
→ CONCLUSION: Ambiguous
→ CORRECT ACTION: Use null for this cell (precision > recall!)
```

### 4. QUALITY VERIFICATION BEFORE SUBMITTING

**Before returning JSON, perform final check:**

✓ All year_1_* fields have consistent data presence (all filled or all null for a row)
✓ All year_2_* fields have consistent data presence
✓ All year_3_* fields have consistent data presence
✓ No column shift detected (verify by cross-checking CO2e = kg × GWP)
✓ Sequence numbers are continuous (1, 2, 3, ... including title rows)
✓ No summary rows included ("Tổng cộng", "Tổng", "Cộng")

**If ANY check fails:**
- Go back and re-analyze that section
- Fix the issue before returning JSON
- Use null if still unclear

**REMEMBER:**
- **Độ tin cậy 100%** (100% reliability) is MANDATORY
- Better to have null than wrong data
- Precision > Recall

---
"""


def _get_table_column_accuracy_prompt():
    """
    Shared prompt for all table categories about column alignment.
    Used by equipment, collection, quota tables.
    """
    return """

### COLUMN ALIGNMENT ACCURACY - 100% RELIABILITY REQUIRED!

**YÊU CẦU TUYỆT ĐỐI:** Trích xuất đủ, đúng, không bị lệch cột!

**CRITICAL REQUIREMENTS:**
✓ Extract ALL data (đầy đủ)
✓ Extract CORRECTLY (chính xác)
✓ NO column shift (không lệch cột)
✓ NO missing columns (không thiếu cột)
✓ NO incorrect column assignment (không gán sai cột)

**RETHINK PROCESS:**

**STEP 1: Before extracting any row**
1. Count total columns in table header
2. Identify each column's purpose and position
3. Create mental map: Column 1 = X, Column 2 = Y, Column 3 = Z, ...

**STEP 2: For each data row**
1. Count total data cells in row
2. Verify: Number of cells = Number of header columns?
3. Match each cell to correct column by POSITION (not by content guessing)
4. Double-check critical columns (quantities, capacities, codes)

**STEP 3: Verification**
- Cross-check with adjacent rows for consistency
- Verify data types match column types (numbers in numeric columns, text in text columns)
- Look for anomalies (sudden jumps, unexpected values)

**IF UNCLEAR OR AMBIGUOUS:**
1. PAUSE and re-analyze table structure
2. Re-count columns and cells
3. Use adjacent rows as reference
4. If still uncertain → Use null for that cell
5. NEVER guess or shift columns to fit

**EXAMPLE - COLUMN POSITION VERIFICATION:**

```
Header: | [1] STT | [2] Loại thiết bị | [3] Công suất thiết kế | [4] Công suất thực tế | [5] Đơn vị | [6] Số lượng | [7] Chất sử dụng |

Data row: | [1] 1 | [2] Điều hòa | [3] 5 | [4] 3.5 | [5] HP / kW | [6] 10 | [7] R-410A |

Extraction verification:
✓ Cell at position 1 → sequence = 1
✓ Cell at position 2 → equipment_type = "Điều hòa"
✓ Cell at position 3 → design_capacity = 5
✓ Cell at position 4 → actual_capacity = 3.5
✓ Cell at position 5 → capacity_unit = "HP / kW"
✓ Cell at position 6 → quantity = 10
✓ Cell at position 7 → substance_used = "R-410A"

RESULT: All columns aligned correctly ✓
```

**COMMON ERRORS TO AVOID:**

❌ **Error 1: Missing column**
```
Header has 7 columns, but only extracted 6 fields
→ One column was skipped!
```

❌ **Error 2: Column shift**
```
Extracted design_capacity = 3.5, actual_capacity = 10
But visually: design_capacity = 5, actual_capacity = 3.5
→ Values shifted right by one column!
```

❌ **Error 3: Merged cell mishandling**
```
Merged cell spanning columns 3-4 contains "5 HP / 3.5 kW"
Incorrectly extracted as: design_capacity = "5 HP / 3.5 kW", actual_capacity = null
→ Should handle merged cell properly!
```

**QUALITY CHECK BEFORE SUBMITTING:**

Before returning JSON:
✓ Total extracted fields per row = Total header columns
✓ No column shifts detected
✓ All numeric fields contain numbers (or null)
✓ All text fields contain text (or null)
✓ Data makes logical sense (no anomalies)

**IF ANY ISSUE FOUND:**
- STOP and re-analyze
- Fix before submitting
- Use null if unclear
"""


def _get_equipment_product_additional_prompt():
    """Additional prompts for equipment product (Bảng 1.2)."""
    return f"""

---

## ⚠️ CRITICAL REMINDERS FOR EQUIPMENT PRODUCT (Bảng 1.2)

### 1. YEAR EXTRACTION

**`year` field**: Năm báo cáo dữ liệu (single year)

**SOURCES (priority order):**
1. Table header (e.g., "Bảng 1.2 - Năm 2024")
2. Text in section: "Năm báo cáo: 2024"
3. If not found → null (will be inferred from metadata later)

**NOT from:** Signature dates, submission dates

### 2. CAPACITY COLUMN STRUCTURE DETECTION

**CRITICAL:** Must detect table structure FIRST before extraction!

**Check table header:**

**Option A: 1 capacity column (merged)**
- Header shows: "Công suất" (single column)
- Data contains: "5 HP / 3.5 kW" (combined value)
- **Set:** `is_capacity_merged_table_1_2 = true`
- **Use field:** `capacity` (string, e.g., "5 HP / 3.5 kW")

**Option B: 2 separate capacity columns**
- Header shows: "Công suất thiết kế" | "Công suất thực tế" (two columns)
- Data contains: "5 HP" | "3.5 kW" (separate values)
- **Set:** `is_capacity_merged_table_1_2 = false`
- **Use fields:** `cooling_capacity` (e.g., "5 HP"), `power_capacity` (e.g., "3.5 kW")

**Verification:**
- Count capacity-related columns in header
- 1 column → merged, 2 columns → separate
- Set flag accordingly BEFORE extracting data

{_get_table_column_accuracy_prompt()}

---
"""


def _get_equipment_ownership_additional_prompt():
    """Additional prompts for equipment ownership (Bảng 1.3)."""
    return f"""

---

## ⚠️ CRITICAL REMINDERS FOR EQUIPMENT OWNERSHIP (Bảng 1.3)

### 1. YEAR EXTRACTION

**`year` field**: Năm báo cáo tồn kho thiết bị

**SOURCES:**
1. Table header
2. Section text
3. null if not found

{_get_table_column_accuracy_prompt()}

### 2. CAPACITY COLUMNS

**Similar to Bảng 1.2:**
- Detect if capacity is merged or separate
- Set `is_capacity_merged_table_1_3` accordingly
- Use appropriate fields based on structure

---
"""


def _get_collection_recycling_additional_prompt():
    """Additional prompts for collection/recycling (Bảng 1.4)."""
    return f"""

---

## ⚠️ CRITICAL REMINDERS FOR COLLECTION/RECYCLING (Bảng 1.4)

### 1. YEAR EXTRACTION

**`year` field**: Năm hoạt động thu gom/tái chế

**SOURCES:**
1. Table header
2. Section text
3. null if not found

### 2. ACTIVITY TYPE DETECTION

**Table structure:**
Bảng 1.4 is divided into sections (title rows):
- Thu gom (collection) → activity_type = "collection"
- Tái sử dụng (reuse) → activity_type = "reuse"
- Tái chế (recycling) → activity_type = "recycling"
- Chuyển đổi (processing) → activity_type = "processing"
- Tiêu hủy (destruction) → activity_type = "destruction"
- Xuất khẩu (export) → activity_type = "export_recycling"

**Extraction:**
- Each section has title row with `is_title = true`
- Data rows under that section inherit the activity_type

{_get_table_column_accuracy_prompt()}

---
"""


def _get_quota_usage_additional_prompt():
    """Additional prompts for quota usage (Bảng 2.1 - Form 02)."""
    return f"""

---

## ⚠️ CRITICAL REMINDERS FOR QUOTA USAGE (Bảng 2.1)

### 1. YEAR EXTRACTION

**`year` field**: Năm sử dụng hạn ngạch (NOT năm phân bổ hạn ngạch)

**SOURCES (priority order):**
1. Text: "Quý ... năm 2024" → year = 2024
2. Table header: "Bảng 2.1 - Năm 2024"
3. Metadata text: "2. Báo cáo về tình hình sử dụng chất được kiểm soát trong năm 2024"
4. null if not found

**NOT from:** License dates, signature dates, submission dates

{_get_table_column_accuracy_prompt()}

### 2. QUOTA COLUMNS - CRITICAL ALIGNMENT!

**Bảng 2.1 has many numeric columns - BE EXTREMELY CAREFUL:**

Typical structure:
| Chất | Mã HS | Hạn ngạch phân bổ (kg) | Hạn ngạch phân bổ (CO2e) | Điều chỉnh (kg) | Điều chỉnh (CO2e) | Tổng hạn ngạch (kg) | Tổng hạn ngạch (CO2e) | Đã sử dụng (kg) | Đã sử dụng (CO2e) | Còn lại (kg) | Còn lại (CO2e) | Số tờ khai HQ |

**VERIFY each row:**
- allocated_quota_kg → Column position for "Hạn ngạch phân bổ (kg)"
- allocated_quota_co2 → Column position for "Hạn ngạch phân bổ (CO2e)"
- adjusted_quota_kg → Column position for "Điều chỉnh (kg)"
- ... and so on

**Cross-validation:**
- Check: total_quota ≈ allocated_quota + adjusted_quota
- Check: remaining_quota ≈ total_quota - used_quota
- If calculation doesn't match → Re-check column alignment!

---
"""


def _get_equipment_product_report_additional_prompt():
    """Additional prompts for equipment product report (Bảng 2.2)."""
    return _get_equipment_product_additional_prompt()  # Same structure as Bảng 1.2


def _get_equipment_ownership_report_additional_prompt():
    """Additional prompts for equipment ownership report (Bảng 2.3)."""
    return _get_equipment_ownership_additional_prompt()  # Same structure as Bảng 1.3


def _get_collection_recycling_report_additional_prompt():
    """Additional prompts for collection/recycling report (Bảng 2.4)."""
    return f"""

---

## ⚠️ CRITICAL REMINDERS FOR COLLECTION/RECYCLING REPORT (Bảng 2.4)

### 1. TITLE ROWS SUPPORT

**Bảng 2.4 supports TITLE ROWS for section headers:**
- Title rows have `is_title = true` and `title_name = "section text"`
- Data rows have `is_title = false` and `title_name = null`
- Each section may group substances by activity type

**Common title row examples:**
- "Thu gom chất được kiểm soát"
- "Tái sử dụng"
- "Tái chế"
- "Tiêu hủy"

### 2. COMPLEX COLUMN STRUCTURE

**Bảng 2.4 has MANY columns grouped by activity:**
- Thu gom (3 columns): Khối lượng, Địa điểm thu gom, Địa điểm lưu giữ
- Tái sử dụng (2 columns): Khối lượng, Công nghệ
- Tái chế (3 columns): Khối lượng, Công nghệ, Nơi sử dụng
- Tiêu hủy (3 columns): Khối lượng, Công nghệ, Cơ sở xử lý

**BE EXTREMELY CAREFUL with column alignment!**
Each substance row has up to 11+ data columns.

### 3. NULL VALUE HANDLING

- If a substance doesn't have data for an activity → Set those columns to null
- Don't leave fields empty - use explicit null
- Title rows should have all data fields as null

{_get_table_column_accuracy_prompt()}

---
"""


def _get_default_additional_prompt():
    """Default additional prompt for unknown categories."""
    return f"""

---

## ⚠️ GENERAL DATA EXTRACTION REMINDERS

{_get_table_column_accuracy_prompt()}

### YEAR EXTRACTION (if applicable)

- Extract from table header or section text
- Use null if unclear
- Do NOT use signature dates or submission dates

### RETHINK STRATEGY

**When uncertain:**
- PAUSE and re-analyze
- Verify table structure
- Use null for unclear values
- NEVER guess!

---
"""
