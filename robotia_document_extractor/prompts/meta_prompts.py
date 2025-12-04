# -*- coding: utf-8 -*-

"""
Meta prompts - Shared extraction rules applicable to all forms
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
- Placeholder text: +2 points
- Example markers: +3 points
- All numbers multiples of 100: +1 point
- Generic org name (no legal form): +2 points
- Gray/italic text: +1 point
- Brackets around values: +1 point

Decision:
- Score ≥5 points → TEMPLATE (skip entire form)
- Score 3-4 points → UNCERTAIN (extract but flag)
- Score ≤2 points → REAL DATA (extract normally)

Real Data Override (even if high score):
- Legal entity form present: -3 points
- Specific address with street numbers: -2 points
- Irregular numbers (123.45, 1789): -2 points
- Handwritten annotations: -3 points
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

### Business ID Mapping

CRITICAL: Map each field to EXACT location
- organization_name: "Tên tổ chức/doanh nghiệp"
- business_license_number: "Mã số doanh nghiệp" (NOT tax ID)
- Tax ID is separate field (if exists)

Avoid mixing:
- Business license ≠ Tax ID
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
"""
