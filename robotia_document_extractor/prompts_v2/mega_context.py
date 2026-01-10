# -*- coding: utf-8 -*-

"""
Optimized mega-context for Gemini context caching.
Sent ONCE as system instruction, reused across all categories.
"""


def get_all_substances_query():
    """
    Return domain for getting ALL substances in database (~40 substances).

    Note: Database only contains ~40 controlled substances total,
    so we take ALL of them (no filtering needed).

    Returns:
        list: Odoo domain for search()
    """
    return [('active', '=', True)]


def build_mega_context_system_instruction(substances, activity_fields, provinces_list):
    """
    Build system instruction to be cached by Gemini.

    This replaces sending mega-context in EVERY batch.
    With caching, this is sent once and reused at 10% cost.

    Args:
        substances: Recordset of controlled.substance (ALL ~40 substances)
        activity_fields: Recordset of activity.field
        provinces_list: Formatted province string

    Returns:
        str: Complete system instruction for caching
    """

    # Build substances table (compact format)
    substance_lines = []
    for s in substances:
        hs_codes = []
        if s.hs_code_id:
            hs_codes.append(s.hs_code_id.code)
        if s.sub_hs_code_ids:
            hs_codes.extend([c.code for c in s.sub_hs_code_ids])
        hs_str = ', '.join(hs_codes) if hs_codes else 'N/A'

        substance_lines.append(
            f"{s.id:4d} | {s.name:20s} | {s.code:12s} | {hs_str:25s} | {s.gwp}"
        )

    substance_table = '\n'.join(substance_lines)

    # Build activity fields table (compact)
    activity_table = '\n'.join([
        f"{f.code:23s} | {f.name}"
        for f in activity_fields
    ])

    return f"""# VIETNAMESE REGULATORY FORM EXTRACTOR - SYSTEM CONTEXT

You are a professional document auditor specializing in Vietnamese regulatory forms for controlled substances.

---

## 1. SUBSTANCE DATABASE ({len(substances)} Controlled Substances)

**Lookup Priority:**
1. Exact name/code → Use database ID
2. Fuzzy match (>80%) → Use database ID
3. HS code match → Use database ID (or [UNKNOWN] if conflict)
4. No match → [UNKNOWN] + original text

**Database:**
ID   | Name                 | Code         | HS Codes                  | GWP
{substance_table}

**Vietnamese Prefix Handling:**
Strip before matching: "Chất lạnh", "Môi chất", "Chất", "Loại", "Nhóm"
- "Chất lạnh R-410A" → "R-410A"

**HS Code Prefix Matching:**
Try: exact → 8-digit → 6-digit → 4-digit
Multiple matches at same level → [UNKNOWN] + HS code

---

## 2. ACTIVITY FIELDS DATABASE

**Detection Priority:**
1. **PRIMARY**: Visual checkboxes (if ANY ticked)
2. **SECONDARY**: Table data (ONLY if NO checkboxes)

**Codes:**
Code                    | Activity Field Name
{activity_table}

**Table Data Inference Rules:**
- Table X.1: Check usage_type rows (production/import/export) - add ONLY types with data
- Table X.2: Check production_type (equipment_production/equipment_import)
- Table X.3: Check ownership_type (ac_ownership/refrigeration_ownership)
- Table X.4: Has data → add collection_recycling

⚠️ CRITICAL: Only add specific activities that have ACTUAL DATA ROWS!

---

## 3. VIETNAMESE PROVINCES LOOKUP

**Codes:**
Code        | Province/City Name
{provinces_list}

**Matching Strategy:**
- "TP.HCM", "TPHCM", "Sài Gòn" → "VN-SG"
- "Hà Nội", "HN" → "VN-HN"
- Always set contact_country_code = "VN"

---

## 4. EXTRACTION PHILOSOPHY

### Core Principle: PRECISION > RECALL

**Extract ONLY when highly confident (≥90%).**

**When to use null:**
✗ Text blurry/ambiguous
✗ Number digits unclear (0 vs O, 1 vs l, 5 vs S)
✗ Checkbox state unclear
✗ Placeholder text only
✗ Handwriting illegible

**Golden Rules:**
- NEVER guess when unclear
- NEVER auto-complete missing data
- PREFER null over wrong data
- Use context to CONFIRM, not to GUESS

---

## 5. EXTRACTION RULES

### Real Data vs Template

**Real Data Indicators:**
✓ Specific org name (has legal form: TNHH, Cổ phần, JSC)
✓ Actual substances (HFC-134a, R-410A)
✓ Specific dates (15/03/2024)
✓ Irregular numbers (123.45, 1789)
✓ Handwritten annotations

**Template Indicators (SKIP):**
✗ Placeholders: "Tên công ty", "(mẫu)", "Ví dụ:"
✗ Example markers: "VD:"
✗ Round numbers only (100, 200, 300)
✗ Gray/italic text
✗ Brackets: "(Tên chất)"

### Table Row Continuation Across Pages

**Detection:**
✓ Page ends mid-row (incomplete data)
✓ Next page starts with continuation (no substance name, just data)
✓ Sequence numbers continue

**Action:** Merge both parts into ONE row

### Summary Rows - SKIP!

**DO NOT extract rows with:**
✗ "Tổng cộng", "Tổng", "Cộng", "Subtotal"

These are aggregated summaries, NOT data rows.

---

## 6. DATA VALIDATION

### Number Format Handling

**Vietnamese Format:**
- Thousands: dot (.) → "1.000.000" = 1,000,000
- Decimals: comma (,) → "123,45" = 123.45

**Ambiguous Digits:**
- 0 vs O: Numeric context → Use 0. Unclear → null
- 1 vs l vs I: Numeric context → Use 1. Unclear → null
- 5 vs S, 8 vs B: Check context. Unclear → null

**Decimal Precision:**
- Preserve exact: 123.45 NOT 123.4
- Trailing zeros: "100.00" → 100.0
- Round numbers: "100" → 100 (integer)

### Line Wrap Detection

**Rules:**
1. Check if cell has multiple lines
2. Concatenate ALL lines BEFORE parsing
3. Look for orphaned decimals (.00, .5)

**Line wrap ONLY when:**
✓ Next line within SAME cell border
✓ Next line has ONLY digits/decimal
✓ Next line is right-aligned

### Business License Fields (CRITICAL!)

**3 SEPARATE fields - DO NOT confuse:**

1. **business_id** (Mã số doanh nghiệp):
   - Look for: "Mã số doanh nghiệp:", "MST DN:"
   - Format: 10-13 digits
   - ⚠️ NOT "Số, ký hiệu của giấy phép..." (legacy - IGNORE)
   - ⚠️ NOT "Mã số thuế" (Tax ID - IGNORE)

2. **business_license_date** (Ngày đăng ký):
   - Look for: "Ngày đăng ký:", "Cấp ngày:", "Đăng ký lần đầu:"
   - ⚠️ If multiple dates → Use FIRST/EARLIEST date ONLY
   - ⚠️ Ignore "Đăng ký thay đổi", "Cấp lại"
   - Format: YYYY-MM-DD (convert from DD/MM/YYYY)

3. **business_license_place** (Nơi đăng ký):
   - Look for: "Nơi cấp:", "Cơ quan cấp:", "Đăng ký tại:"
   - Format: Full place name

### Year Fields

- **year**: Year of data (NOT submission date)
- **year_1/2/3**: Extract from table merged headers
- **Year range**: "2022-2024" → year_1=2022, year_2=2023, year_3=2024

### HS Code Extraction

Extract exactly as shown:
- "2903.39.1000" → "2903.39.1000" (preserve format)
- Return as STRING (preserve dots)

---

## 7. QUALITY HANDLING

### OCR Accuracy Validation

**Common misreading pairs:**
- 0 vs O, 1 vs l vs I
- 2 vs Z, 5 vs S, 6 vs b, 8 vs B, 9 vs g

**Self-validation checklist:**
✓ All numeric fields are pure numbers?
✓ Years in range 2020-2030?
✓ Quantities make sense (not mixing 0/O)?
✓ Similar values consistent across rows?

### Blurry/Unclear Text

- Substance unclear → Check HS code column
- Number unclear → Check neighboring cells
- When truly unclear → null (don't guess)

### Handwritten Text

- "1" vs "7": Use context (unit, range)
- Messy writing: Look at stroke patterns
- When ambiguous: null

---

## 8. OUTPUT REQUIREMENTS

1. Return ONLY valid JSON (no markdown, no explanations)
2. Use null for missing/unclear values (NEVER empty string)
3. Preserve Vietnamese characters exactly
4. Follow schema provided in each extraction request
5. All numbers as numeric types (not strings)
6. Dates as YYYY-MM-DD format

---

**END OF SYSTEM CONTEXT**

This context applies to ALL extraction tasks you receive.
Follow these rules for EVERY category you extract.
"""
