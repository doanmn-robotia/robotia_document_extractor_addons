# -*- coding: utf-8 -*-

"""
Context prompts - Database-driven prompts for substances, activities, and provinces
"""


def get_substance_mapping_prompt(substances):
    """Build substance mapping prompt with database data
    
    Args:
        substances: Recordset of controlled.substance
        
    Returns:
        str: Substance mapping prompt with database table
    """
    # Build substance table
    lines = []
    for s in substances:
        # Get HS codes
        hs_codes = []
        if s.hs_code_id:
            hs_codes.append(s.hs_code_id.code)
        if s.sub_hs_code_ids:
            hs_codes.extend([c.code for c in s.sub_hs_code_ids])
        hs_str = ', '.join(hs_codes) if hs_codes else 'N/A'
        
        lines.append(
            f"{s.id:4d} | {s.name:20s} | {s.code:12s} | {hs_str:25s} | {s.gwp}"
        )
    
    table = '\n'.join(lines)
    
    return f"""
## SUBSTANCE DATABASE MAPPING

You have access to {len(substances)} controlled substances from our database.

Database Table:
ID   | Name                 | Code         | HS Codes                  | GWP
{table}

### Matching Rules

Priority (try in order):
1. Exact name/code match → Use it (100% confidence)
2. Fuzzy name match (>80% similarity) → Use it
3. HS code match + generic/unclear name → Return [UNKNOWN] + HS code
4. HS code conflict (multiple substances) → Return [UNKNOWN] + HS code
5. No match → Return [UNKNOWN] + original text

### Vietnamese Name Handling

Strip Vietnamese prefixes before matching:
- "Chất lạnh R-410A" → "R-410A"
- "Môi chất HFC-134a" → "HFC-134a"
- "Chất HFC-32" → "HFC-32"

Prefixes to strip: "Chất lạnh", "Môi chất", "Chất", "Loại", "Nhóm"

### HS Code Prefix Matching

If exact HS code not found, try prefix matching:
1. Try exact: "2903.39.1100" = "2903.39.1100" ✓
2. Try 8-digit: "2903.39.1100" → "2903.39.11"
3. Try 6-digit: "2903.39.1100" → "2903.39"
4. Try 4-digit: "2903.39.1100" → "2903"

If multiple matches at same level → Return [UNKNOWN] + HS code

### Output Format

For matched substances:
- substance_name: EXACT name from database (e.g., "HFC-134a")
- substance_id: Database ID (integer)
- hs_code: HS code from document (string, may differ from DB)

For unmatched:
- substance_name: "[UNKNOWN] <original text>"
- substance_id: null
- hs_code: Extract from document if available

### Examples

| Document Text | Matched Name | DB ID | Notes |
|---------------|--------------|-------|-------|
| "HFC-134a" | HFC-134a | 123 | Exact match |
| "HFC134a" | HFC-134a | 123 | Missing hyphen |
| "R-134a" | HFC-134a | 123 | Code to name |
| "Chất lạnh R-410A" | R-410A | 456 | Vietnamese prefix stripped |
| "HFC" + HS "2903.39" | [UNKNOWN] HFC | null | HS code conflict |
| "XYZ-999" | [UNKNOWN] XYZ-999 | null | Not in database |
"""


def get_activity_fields_prompt(activity_fields):
    """Build activity fields mapping prompt
    
    Args:
        activity_fields: Recordset of activity.field
        
    Returns:
        str: Activity fields prompt with mapping table
    """
    # Build activity table
    table = '\n'.join([
        f"{f.code:23s} | {f.name}"
        for f in activity_fields
    ])
    
    return f"""
## ACTIVITY FIELDS MAPPING

You have access to {len(activity_fields)} activity fields from our database.

Activity Codes Table:
Code                    | Activity Field Name
{table}

### Extraction Rules

1. Identify checked/selected activities from document
   - Form 01: Section "2. Nội dung đăng ký"
   - Form 02: Section "b) Thông tin về lĩnh vực hoạt động"

2. Match each checked activity to EXACT code from table above

3. Return ONLY the codes in "activity_field_codes" array

4. If activity doesn't match any official field → skip it (don't create unknown codes)

### Visual Indicators for Checked Boxes

Checked:
✓ Checkmark (✓, ✔)
✓ X mark
✓ Filled/shaded box (☑)
✓ Circled text
✓ Underlined text
✓ Handwritten mark inside box

NOT checked:
✗ Empty box (☐)
✗ Faint/gray placeholder
✗ No mark at all

### Examples

Document shows (checked):
- "Sản xuất chất được kiểm soát" ✓
- "Sở hữu máy điều hòa không khí" ✓

Extract:
"activity_field_codes": ["production", "ac_ownership"]

### Cross-Validation with Tables

Use activity codes to validate table presence:
- If any(production, import, export) → expect Table X.1
- If any(equipment_production, equipment_import) → expect Table X.2
- If any(ac_ownership, refrigeration_ownership) → expect Table X.3
- If collection_recycling → expect Table X.4
"""


def get_province_lookup_prompt(provinces_list):
    """Build province/city lookup prompt
    
    Args:
        provinces_list: Formatted province list string (from _get_vietnamese_provinces_list)
        
    Returns:
        str: Province lookup prompt
    """
    return f"""
## VIETNAMESE PROVINCE/CITY LOOKUP

You have access to the official list of Vietnamese provinces and cities.

Province Codes Table:
Code        | Province/City Name
{provinces_list}

### Lookup Rules

**BEFORE RETURNING FINAL RESULT**, you MUST:
1. Look at the `contact_address` field you extracted
2. Identify the province/city name from address (usually at the end)
3. Match it to the EXACT code from the table above
4. Set `contact_state_code` to the matching code
5. If no match or address outside Vietnam → set `contact_state_code` = null

### Matching Strategy

Handle variations intelligently:
- "TP.HCM", "TPHCM", "Sài Gòn", "Hồ Chí Minh" → "TP Hồ Chí Minh" → "VN-SG"
- "Hà Nội", "Ha Noi", "HN" → "Hà Nội" → "VN-HN"
- "Đà Nẵng", "Da Nang", "DN" → "Đà Nẵng" → "VN-DN"

Common abbreviations:
- "TP" = "Thành phố"
- "Tx" = "Thị xã"
- "Q." = "Quận"
- "P." = "Phường"

### Examples

| Address | Province/City | Code |
|---------|---------------|------|
| "123 Nguyễn Huệ, Q.1, TP.HCM" | TP Hồ Chí Minh | VN-SG |
| "45 Lê Lợi, Hải Châu, Đà Nẵng" | Đà Nẵng | VN-DN |
| "10 Trần Hưng Đạo, Ba Đình, Hà Nội" | Hà Nội | VN-HN |
| "Khu CN, Bình Dương" | Bình Dương | VN-57 |
| "789 Main St, California, USA" | (outside Vietnam) | null |

### Important Notes

- ONLY use codes from the official table above
- DO NOT guess or create codes not in this list
- Always set contact_country_code = "VN" when contact_state_code is set
- If address contains district/ward but no province → try to infer from context
"""
