# -*- coding: utf-8 -*-

"""
Meta prompts - Shared extraction rules applicable to all forms
"""



def get_precision_philosophy():
    """Precision-first extraction philosophy and confidence rules
    
    Returns:
        str: Precision philosophy prompt
    """
    return """
## EXTRACTION PHILOSOPHY (CRITICAL!)

### Core Principle: PRECISION > RECALL

Priority order:
1. **ACCURACY** (100% correct data)
2. **COMPLETENESS** (all available data)

We prefer:
✓ 50 fields extracted with 100% accuracy
✗ 100 fields extracted with 90% accuracy (10 wrong fields)

### Confidence-Based Extraction

Extract data ONLY when you are highly confident it is correct.

Confidence levels:
✓ **100% confident** (clear, readable, unambiguous) → Extract
✓ **90%+ confident** (slightly blurry but context confirms) → Extract
✗ **<90% confident** (unclear, ambiguous, illegible) → Return null

### When to Return NULL (Critical Decision Points)

ALWAYS return null when:
✗ Text is blurry and could be multiple interpretations
✗ Number digits are unclear (5 vs S, 0 vs O, 1 vs l)
✗ Checkbox state is ambiguous (cannot determine if ticked)
✗ Field contains placeholder text only
✗ Handwriting is illegible
✗ Text is partially covered/obscured
✗ Multiple valid interpretations exist

### Golden Rules

**NEVER:**
- Guess when unclear
- Infer from patterns/expectations
- Auto-complete missing data based on assumptions
- Fill fields because "it should have a value"
- Choose randomly between multiple interpretations

**ALWAYS:**
- Be conservative with extraction
- Prefer null over wrong data
- Use context ONLY to confirm (not to guess)
- Let users fill unclear fields manually

### Examples

| Scenario | Confidence | Action | Reasoning |
|----------|-----------|--------|-----------|
| Clear "123.45" | 100% | Extract: 123.45 | Perfectly readable |
| Blurry "12?.45" (middle digit unclear) | <90% | null | Could be 123.45, 125.45, 128.45, etc. |
| "HFC-134a" with fuzzy last char | 95% | Extract: "HFC-134a" | Database + context confirms |
| Checkbox ☐ with faint mark | <90% | null | Cannot determine if ticked |
| "100" in gray italic | <90% | null | Likely placeholder |
| "Tổng cộng" row | N/A | Skip row | Summary row (don't extract) |
| "Công ty..." without legal form | <90% | null | Likely placeholder text |

### Validation Checklist

Before finalizing extraction, verify:
✓ All extracted numbers are 100% readable?
✓ No fields contain placeholder/example text?
✓ All substance names match database or marked [UNKNOWN]?
✓ Years are in reasonable range (2020-2030)?
✓ No ambiguous checkboxes extracted?
✓ Used null for unclear fields (not empty string)?
"""


def get_extraction_rules():
    """Core extraction rules - real data vs template detection
    
    Returns:
        str: Extraction rules prompt
    """
    return """
## EXTRACTION RULES

Real Data Indicators:
✓ Specific org name (not "Công ty ABC", "Tên công ty")
✓ Actual substances (HFC-134a, R-410A)
✓ Handwritten/typed numbers
✓ Specific dates (15/03/2024)
✓ Legal entity form ("TNHH", "Cổ phần", "JSC")

Template Indicators (SKIP):
✗ Placeholders: "Tên công ty", "(mẫu)", "Ví dụ:", "Ghi rõ..."
✗ Example markers: "VD:", "Example:"
✗ Round numbers only (100, 200, 300)
✗ Gray/italic text
✗ Brackets: "(Tên chất)", "[Ghi rõ]"

Template Scoring System:
✓ Placeholder text: +2 points
✓ Example markers: +3 points
✓ All numbers multiples of 100: +1 point
✓ Generic org name (no legal form): +2 points
    - Gray/italic text: +1 point
- Brackets around values: +1 point

Decision:
✓ Score ≥5 points → TEMPLATE (skip entire form)
✓ Score 3-4 points → UNCERTAIN (extract but flag)
✓ Score ≤2 points → REAL DATA (extract normally)

Real Data Override (even if high score):
✓ Legal entity form present: -3 points
✓ Specific address with street numbers: -2 points
✓ Irregular numbers (123.45, 1789): -2 points
✓ Handwritten annotations: -3 points

### Table Row Continuation Across Pages (CRITICAL!)

Problem: Table rows may be split across page breaks.

Detection signals:
✓ Page ends mid-row (incomplete data in last row)
✓ Next page starts with continuation (no substance name, just data)
✓ Sequence numbers continue (e.g., page 1 ends at seq 5, page 2 continues)
✓ Same table structure on both pages

How to merge:
1. Identify incomplete row at end of page (missing fields)
2. Identify continuation at start of next page (no substance name in first column)
3. Merge data from both parts into ONE row
4. Use substance name from first part
5. Combine all data fields

Example:
Page 1 (last row):
| HFC-134a | 2903.4 | 52000 | 74560 | 72000 | 102960 | 71994 | 10295 | 5.1 | Trung | 106263 | 70000 | 100100 |
                                                                                    Quốc   | 923811 |
                                                                                    Nhật  | 106312 |
                                                                                           | 279050 |
                                                                                           | 106329 |

Page 2 (first row - continuation):
|  |  |  |  |  |  |  |  |  |  | 979010 |  |  |
                                  | 106348 |
                                  | 536010 |
                                  | 106377 |
                                  | 106753 |
                                  | 106612 |
                                  | 335900 |
                                  | 106739 |
                                  | 331640 |
                                  | 106753 |
                                  | 642220 |
                                  | 106302 |
                                  | 182751 |
                                  | 106753 |

Merged result (ONE row):
| HFC-134a | 2903.4 | 52000 | 74560 | ... | Trung Quốc, Nhật | 106263, 923811, 106312, 979010, 106348, ... | 70000 | 100100 |

### Summary Rows - DO NOT EXTRACT (CRITICAL!)

ALWAYS skip rows with these indicators:

Summary row markers:
✗ "Tổng cộng" (Total)
✗ "Tổng" (Sum)
✗ "Cộng" (Total)
✗ "Tổng số" (Total amount)
✗ "Grand Total"
✗ "Subtotal"

Detection:
- Row starts with summary marker in first column
- Usually has aggregated numbers (sum of above rows)
- Often in bold or different formatting

Action: SKIP these rows entirely, do NOT create data row for them

Example (DO NOT EXTRACT):
| Tổng cộng |  | 29395 | 52010 | 34595 | 604814 | 34140 | 60029 |  |  | 63400 | 100788 |
                   0              0              2.8     4.067                    0       4

Correct behavior:
- Extract all substance rows (HFC-134a, R-410A, etc.)
- SKIP "Tổng cộng" row
- Continue with next section
"""


def get_data_validation():
    """Data type validation rules and critical fixes
    
    Returns:
        str: Data validation prompt
    """
    return """
## DATA VALIDATION

### Data Types

Integer fields (MUST return whole numbers):
- year, year_1, year_2, year_3
- sequence, equipment_quantity, start_year
- All ID fields (substance_id, etc.)

Float fields (return as numbers, not strings):
- All quantity fields (quantity_kg, quantity_co2, etc.)
- Prices, frequencies, capacities (numeric values)

Text fields (preserve exact spelling, spacing, Vietnamese chars):
- organization_name, contact_address, product_type, etc.

### Number Precision Rules (CRITICAL!)

**Ambiguous Digit Detection:**

Common OCR misreadings - VERIFY carefully:
- **0 vs O**: In numeric context → Use 0. Unclear → null
- **1 vs l vs I**: In numeric context → Use 1. Unclear → null
- **5 vs S**: In numeric field → Use 5. In text → Use S. Unclear → null
- **8 vs B**: In numeric field → Use 8. In text → Use B. Unclear → null
- **2 vs Z, 6 vs b, 9 vs g**: Check context carefully

**Resolution strategy:**
1. Check surrounding numbers for consistency
2. Verify against reasonable value ranges
3. Cross-reference with other cells/rows
4. **If still unclear → Return null (NEVER guess)**

**Number Format Handling:**

Vietnamese number format (most common):
- Thousands: "." (dot) → "1.000.000" = 1,000,000
- Decimals: "," (comma) → "123,45" = 123.45

Ambiguous cases:
- "1,234.56" vs "1.234,56" → Check document consistency
- If format unclear throughout → null

**Decimal Precision:**
- Preserve exact decimals: 123.45 NOT 123.4 or 123.450
- Trailing zeros: "100.00" → 100.0 (preserve if shown)
- Round numbers: "100" → 100 (integer, not 100.0)

**Value Range Validation:**

Sanity checks for common fields:
- Year: 2020-2030 (report/registration years)
- Quantity (kg): 0.01 - 1,000,000 (typical range)
- GWP values: 1 - 15,000 (substance GWP range)
- Prices (USD): 0.1 - 1000 (per kg, typical)
- Temperature: -50 to 100°C

If value outside reasonable range:
1. Double-check reading
2. Verify it's not a typo/OCR error
3. **If truly outside range but clearly visible → Extract as-is**
4. **If unclear AND outside range → null**

### Line Wrap Detection (CRITICAL!)

Problem: Numbers split across lines in table cells

Rules:
1. ALWAYS check if cell has multiple lines
2. Concatenate ALL lines BEFORE parsing
3. Look for orphaned decimals (.00, .5) on next line

Line wrap ONLY when ALL of:
✓ Next line within SAME CELL BORDER (visual inspection)
✓ Next line starts with ONLY digits/decimal
✓ Next line is RIGHT-ALIGNED or INDENTED
✓ Previous line ends incompletely (e.g., "1,000" without decimal)

NOT line wrap when:
✗ Next row in table (has row separator/border)
✗ Next line has field labels
✗ Next line starts at left margin (new row)

Examples:
✓ "12,000" + "    .50" = 12000.50 (line wrap in same cell)
✗ "HFC-134a │ 1,000" + "HFC-32   │ 500" = separate rows

### Year Fields

year = Year of DATA being reported (NOT submission date)
- "Báo cáo năm 2023" submitted in 2024 → year = 2023
- "Đăng ký năm 2024" → year = 2024

Year range parsing:
- "2022-2024" → year_1=2022, year_2=2023, year_3=2024
- "2022~2024" → Same
- "2022 đến 2024" → Same

Table column years (year_1, year_2, year_3):
- Extract from merged header cells above quantity columns
- Ignore sub-headers like "(kg)", "(tấn CO2)"
- If only 2-digit: "22" → 2022 (assume 20XX)

### Business License Information Mapping (CRITICAL!)

These 3 fields are OFTEN CONFUSED - map EXACTLY:

1. business_id (Mã số doanh nghiệp):
   - Look for: "Mã số doanh nghiệp:", "MST DN:", "MSDN:"
   - Format: Usually 10-13 digits (e.g., "0800666682", "0123456789-001")
   - Location: Business info section, near organization name

   CRITICAL PRIORITY ORDER (use first match found):
   ① "Mã số doanh nghiệp:" → USE THIS (highest priority)
   ② "Số đăng ký doanh nghiệp:" → Use if ① not found
   ③ "Số ĐKKD:" → Use if ①② not found

   DO NOT USE (these are different fields):
   ✗ "Số, ký hiệu của giấy phép đăng ký kinh doanh..." (legacy license info - IGNORE)
   ✗ "Số giấy phép..." (industry-specific license - IGNORE)
   ✗ "Mã số thuế:" (Tax ID/MST - IGNORE)

   If document has BOTH "Mã số doanh nghiệp" AND "Số, ký hiệu của giấy phép...":
   → ALWAYS use "Mã số doanh nghiệp" (the official registration code)
   → IGNORE the legacy "Số giấy phép..." completely

2. business_license_date (Ngày đăng ký kinh doanh):
   - Look for: "Ngày đăng ký:", "Ngày cấp:", "Cấp ngày:", "Date of registration:", "Đăng ký lần đầu ngày", "Ngày cấp lần đầu"
   - Format: Date (DD/MM/YYYY or DD-MM-YYYY)
   - Location: Usually on same line or below business_id
   - Convert to: YYYY-MM-DD format in output
   - IMPORTANT: This is a DATE, not a number
   
   CRITICAL - Multiple Registration Dates:
   - If document shows MULTIPLE dates (e.g., "Đăng ký lần đầu", "Đăng ký thay đổi lần N")
   - ALWAYS take the FIRST/EARLIEST date ("Đăng ký lần đầu" or "Cấp lần đầu")
   - Ignore subsequent dates (amendments, changes, renewals)
   
   Examples:
   ✓ "Đăng ký lần đầu: 15/03/2020" + "Đăng ký thay đổi lần 3: 10/05/2023" → Use 2020-03-15
   ✓ "Cấp ngày: 01/01/2018" + "Thay đổi lần 5 ngày: 20/12/2024" → Use 2018-01-01
   ✗ Don't use: "Đăng ký thay đổi", "Cấp lại", "Điều chỉnh"

3. business_license_place (Nơi đăng ký kinh doanh):
   - Look for: "Nơi cấp:", "Cơ quan cấp:", "Issued by:", "Đăng ký lần đầu tại:"
   - Format: Text (e.g., "Sở Kế hoạch và Đầu tư TP Hồ Chí Minh")
   - Location: Usually below or after business_license_date

Visual layout example (typical document structure):

Example 1 (Modern format with "Mã số doanh nghiệp"):
┌──────────────────────────────────────────────────────┐
│ Mã số doanh nghiệp: 0800666682                       │ → business_id (USE THIS)
│ Số, ký hiệu của giấy phép đăng ký kinh doanh...     │
│ 04102300049; Ngày cấp: 27/05/2008; Nơi cấp: ...     │ → IGNORE (legacy license info)
└──────────────────────────────────────────────────────┘
Result: business_id = "0800666682"

Example 2 (Old format with "Số đăng ký doanh nghiệp"):
┌──────────────────────────────────────────────────────┐
│ Số đăng ký doanh nghiệp: 0123456789-001              │ → business_id
│ Ngày đăng ký: 15/03/2020                             │ → business_license_date (convert to 2020-03-15)
│ Nơi đăng ký: Sở Kế hoạch và Đầu tư TP Hồ Chí Minh   │ → business_license_place
└──────────────────────────────────────────────────────┘

Example 3 (Multiple registrations - TAKE FIRST DATE):
┌──────────────────────────────────────────────────────┐
│ Mã số doanh nghiệp: 0800666682                       │ → business_id
│ Đăng ký lần đầu: 15/03/2020                          │ → business_license_date (USE THIS: 2020-03-15)
│ Đăng ký thay đổi lần 3: 10/05/2023                   │ → IGNORE (amendment date)
│ Nơi đăng ký: Sở Kế hoạch và Đầu tư TP Hồ Chí Minh   │ → business_license_place
└──────────────────────────────────────────────────────┘

Example 4 (Confusing format - both codes present):
┌──────────────────────────────────────────────────────┐
│ Tên: CÔNG TY TNHH FORD VIỆT NAM                      │
│ Mã số doanh nghiệp: 0800666682                       │ → business_id (USE THIS!)
│ Mã số thuế: 0800666682                               │ → IGNORE (Tax ID)
│ Số, ký hiệu GPĐKKD: 04102300049                      │ → IGNORE (legacy license)
└──────────────────────────────────────────────────────┘
Result: business_id = "0800666682" (from "Mã số doanh nghiệp")

Common mistakes to AVOID:
✗ Putting date value in business_id field
✗ Putting number value in business_license_date field
✗ Using "Số giấy phép..." instead of "Mã số doanh nghiệp" (CRITICAL!)
✗ Confusing "Mã số doanh nghiệp" with "Mã số thuế" (Tax ID)
✗ Mixing up the 3 fields
✗ Using amendment date instead of initial registration date (CRITICAL!)

Other business-related fields (separate from above 3):
- organization_name: "Tên tổ chức/doanh nghiệp"
- Legal representative ≠ Contact person
- Contact phone ≠ Office phone

### HS Code Extraction

Extract exactly as shown in document:
- "2903.39.1000" → "2903.39.1000" (preserve format)
- "2903.39" → "2903.39"
- "29033910" → "29033910"

Return as string (preserve dots, don't convert to number)

### Negative Numbers

Allowed in: adjusted_quota_kg, adjusted_quota_co2, all quantity fields (for returns)

Formats:
- "-500" → -500
- "(500)" → -500 (accounting notation)
- "500-" → -500 (trailing minus)
"""


def get_quality_handling():
    """OCR accuracy and quality handling rules
    
    Returns:
        str: Quality handling prompt
    """
    return """
## QUALITY HANDLING

### OCR Accuracy Validation

Common misreading pairs:
- 0 (zero) vs O (letter O): "100" vs "1OO"
- 1 (one) vs l (lowercase L) vs I (uppercase i): "100" vs "l00"
- 2 vs Z, 5 vs S, 6 vs b, 8 vs B, 9 vs g

Validation rules:
1. Context check: Numeric fields MUST be pure digits (0-9) + decimal only
2. Range check: "5OOO" → likely "5000" (O misread as 0)
3. Pattern check: Years should be 20XX (2020-2030)
4. Consistency check: Similar values should be consistent

Self-validation checklist:
✓ All numeric fields are pure numbers (no letters)?
✓ Years fall in reasonable range (2020-2030)?
✓ Quantities make sense (not mixing 0/O or 1/l)?
✓ Prices are reasonable (typically 1-100 USD)?
✓ Similar values consistent across rows?

### Blurry/Unclear Text

- Substance name unclear → Check HS code column
- Number unclear → Check neighboring cells
- Missing data → Cross-reference other sections
- When truly unclear → null (don't guess)

### Handwritten Text

- "1" vs "7": Use context (unit, range)
- Messy writing: Look at stroke patterns
- When ambiguous: null (don't guess wrong)

### Activity Field Validation (CRITICAL!)

PRIORITY ORDER:
1. **PRIMARY: Visual checkboxes** (if ANY checkbox is ticked)
2. **SECONDARY: Table data inference** (ONLY if NO checkboxes are ticked)

Detection strategy:

**Step 1: Check for ticked checkboxes**
- Look for checkmarks (✓, ✔, X)
- Look for filled boxes (☑)
- Look for highlighting/shading
- Look for circled/underlined text

Decision:
- IF at least ONE checkbox is clearly ticked → Use ONLY ticked checkboxes
- IF NO checkboxes are ticked → Proceed to Step 2

**Step 2: Table data inference (ONLY if no checkboxes ticked)**

Only use when checkbox section is:
- Completely empty (no checkboxes ticked)
- Completely unclear/blurry
- Missing entirely

Infer from table data:

1. Table X.1 (substance_usage / quota_usage):
   - Has rows with usage_type="production" AND has data → Add "production"
   - Has rows with usage_type="import" AND has data → Add "import"
   - Has rows with usage_type="export" AND has data → Add "export"
   
   CRITICAL: Only add specific usage_type(s) with actual data!
   - Table has ONLY import data → Add ONLY "import"
   - Don't auto-add all 3 just because table exists!

2. Table X.2 (equipment_product / equipment_product_report):
   - Has rows with production_type="production" AND has data → Add "equipment_production"
   - Has rows with production_type="import" AND has data → Add "equipment_import"

3. Table X.3 (equipment_ownership / equipment_ownership_report):
   - Has rows with ownership_type="air_conditioner" AND has data → Add "ac_ownership"
   - Has rows with ownership_type="refrigeration" AND has data → Add "refrigeration_ownership"

4. Table X.4 (collection_recycling / collection_recycling_report):
   - Has ANY data rows → Add "collection_recycling"

**Step 3: Validation (sanity check)**
- If activity in codes but no table data → Suspicious but keep it (checkboxes take priority)
- If table has data but activity not in codes → OK (checkboxes take priority)

Self-validation checklist:
✓ If using checkboxes → Used ALL ticked checkboxes?
✓ If using table data → Only added activities with actual data rows?
✓ Didn't auto-add all activities just because table exists?

Example validation:

Scenario 1 (Checkboxes ticked):
- Visual: "Sản xuất" ✓, "Nhập khẩu" ✓
- Table: Only import has data, no production data
→ Use checkboxes: activity_field_codes = ["production", "import"]
→ Checkboxes take priority even if table doesn't match

Scenario 2 (No checkboxes ticked):
- Visual: All checkboxes empty
- Table 2.1: Only import section has data (5 rows), production/export empty
→ Use table data: activity_field_codes = ["import"]
→ Only add "import", NOT all 3!

Scenario 3 (Partial unclear):
- Visual: "Nhập khẩu" ✓ (clear), other boxes blurry
- Table: Has production + import + export data
→ Use checkboxes: activity_field_codes = ["import"]
→ At least one checkbox is clear, so use checkbox method
"""
