# -*- coding: utf-8 -*-

"""
Category-specific JSON schemas.
Each function returns ONLY the schema needed for that category.
"""


def get_metadata_schema(form_type):
    """
    Schema for metadata category (organization info, year, activity fields).

    Args:
        form_type: '01' or '02'

    Returns:
        str: Compact metadata schema
    """

    # Build table presence flags section based on form type
    if form_type == '01':
        table_flags_section = """| has_table_1_1 | bool | True if substance_usage table has data rows |
| has_table_1_2 | bool | True if equipment_product table has data rows |
| has_table_1_3 | bool | True if equipment_ownership table has data rows |
| has_table_1_4 | bool | True if collection_recycling table has data rows |
| is_capacity_merged_table_1_2 | bool | True if Table 1.2 has 1 capacity column (merged) |
| is_capacity_merged_table_1_3 | bool | True if Table 1.3 has 1 capacity column (merged) |"""

        example_flags = """"has_table_1_1": true,
  "has_table_1_2": true,
  "has_table_1_3": false,
  "has_table_1_4": false,
  "is_capacity_merged_table_1_2": false,
  "is_capacity_merged_table_1_3": false,"""
    else:  # '02'
        table_flags_section = """| has_table_2_1 | bool | True if quota_usage table has data rows |
| has_table_2_2 | bool | True if equipment_product_report table has data rows |
| has_table_2_3 | bool | True if equipment_ownership_report table has data rows |
| has_table_2_4 | bool | True if collection_recycling_report table has data rows |
| is_capacity_merged_table_2_2 | bool | True if Table 2.2 has 1 capacity column (merged) |
| is_capacity_merged_table_2_3 | bool | True if Table 2.3 has 1 capacity column (merged) |"""

        example_flags = """"has_table_2_1": true,
  "has_table_2_2": false,
  "has_table_2_3": false,
  "has_table_2_4": false,
  "is_capacity_merged_table_2_2": false,
  "is_capacity_merged_table_2_3": false,"""

    return f"""## METADATA SCHEMA

Extract organization information and document metadata.

⚠️ **CRITICAL**: Metadata is extracted LAST, so you can LOOK BACK at ENTIRE CHAT HISTORY to infer flags.

### Required Fields

| Field | Type | Extract From |
|-------|------|--------------|
| year | int | **LOOK BACK in chat history**: Extract from table column headers (merged cells "Năm ..."). If table has 3 years → year = middle year (year_2). If table has 1 year → year = that year. |
| year_1 | int/null | **LOOK BACK**: First year from table headers (only if table has 3 year columns) |
| year_2 | int/null | **LOOK BACK**: Second year from table headers (= year, only if table has 3 year columns) |
| year_3 | int/null | **LOOK BACK**: Third year from table headers (only if table has 3 year columns) |
| organization_name | str | "Tên tổ chức:" (must be specific, not placeholder) |
| business_id | str | "Mã số doanh nghiệp:" (NOT "Số giấy phép...") |
| business_license_date | str | "Ngày đăng ký lần đầu:" → YYYY-MM-DD (FIRST date only!) |
| business_license_place | str | "Nơi đăng ký:" |
| legal_representative_name | str | Representative section |
| legal_representative_position | str | Representative section |
| contact_person_name | str | Contact section |
| contact_address | str | Full address |
| contact_phone | str | Phone number |
| contact_fax | str | Fax (null if missing) |
| contact_email | str | Email (null if missing) |
| contact_country_code | str | Infer from address ("VN", "US", etc.) |
| contact_state_code | str/null | Lookup from province table ("VN-SG", "VN-HN", etc.) |
| activity_field_codes | array[str] | Infer from checkboxes OR table presence |
{table_flags_section}

### CRITICAL: Year Extraction Logic

**MUST LOOK BACK at chat history** to find years from table column headers:

**For tables with 3 year columns** (Bảng 1.1 or Bảng 2.1):
- Table headers: "Năm 2021" | "Năm 2022" | "Năm 2023"
- year_1 = 2021 (first year)
- year_2 = 2022 (middle year, **this is also "year"**)
- year_3 = 2023 (third year)
- **year = year_2** (the middle/main reporting year)

**For tables with 1 year column** (other tables):
- Table header: "Năm 2022"
- **year = 2022**
- year_1, year_2, year_3 = null (not applicable)

**If no years found in chat history** (fallback):
- Infer from document title or context
- Set year_1 = year - 1, year_2 = year, year_3 = year + 1

### CRITICAL: Table Presence Flags (has_table_x_x)

**LOOK BACK at chat history** to see which categories were extracted:

- If extracted `substance_usage` → has_table_1_1 = true (Form 01)
- If extracted `equipment_product` → has_table_1_2 = true (Form 01)
- If extracted `equipment_ownership` → has_table_1_3 = true (Form 01)
- If extracted `collection_recycling` → has_table_1_4 = true (Form 01)
- If extracted `quota_usage` → has_table_2_1 = true (Form 02)
- If extracted `equipment_product_report` → has_table_2_2 = true (Form 02)
- If extracted `equipment_ownership_report` → has_table_2_3 = true (Form 02)
- If extracted `collection_recycling_report` → has_table_2_4 = true (Form 02)

### CRITICAL: Capacity Merged Flags (is_capacity_merged_table_x_x)

**LOOK BACK at equipment table responses** in chat history:

- Check if equipment table has field `capacity` (1 column) → is_capacity_merged = true
- Check if equipment table has `cooling_capacity` + `power_capacity` (2 columns) → is_capacity_merged = false

### Activity Field Codes Inference

**Priority 1**: Extract from checkboxes/ticks in document

**Priority 2**: If no checkboxes, infer from has_table flags:
- has_table_1_1 = true → Check substance_usage data rows for usage_type (production/import/export)
- has_table_1_2 = true → Add equipment_production or equipment_import
- has_table_1_3 = true → Add ac_ownership or refrigeration_ownership
- has_table_1_4 = true → Add collection_recycling

**Rule**: Only add activity if table has at LEAST 1 DATA ROW (is_title=false with actual values)

### EXAMPLE JSON Output

{{
  "year": 2022,
  "year_1": 2021,
  "year_2": 2022,
  "year_3": 2023,
  "organization_name": "CÔNG TY TNHH ABC",
  "business_id": "0800666682",
  "business_license_date": "2020-03-15",
  "business_license_place": "Sở Kế hoạch và Đầu tư TP Hồ Chí Minh",
  "legal_representative_name": "Nguyễn Văn A",
  "legal_representative_position": "Giám đốc",
  "contact_person_name": "Trần Thị B",
  "contact_address": "123 Nguyễn Huệ, Q.1, TP.HCM",
  "contact_phone": "028-12345678",
  "contact_fax": null,
  "contact_email": "contact@abc.com",
  "contact_country_code": "VN",
  "contact_state_code": "VN-SG",
  "activity_field_codes": ["production", "import", "export"],
  {example_flags}
}}
"""


def get_substance_usage_schema(form_type):
    """
    Schema for substance_usage category (Table 1.1 - Form 01).

    Args:
        form_type: '01' or '02'

    Returns:
        str: Substance usage schema
    """
    if form_type != '01':
        return ""  # Not applicable for Form 02

    return """## SUBSTANCE USAGE SCHEMA (Table 1.1)

Extract substance usage data with multi-year quantities.

### Table Structure Detection

**CRITICAL:** Extract year_1, year_2, year_3 from merged column headers.

Example header:
| Substance | HS Code | 2022 (kg) | 2022 (CO2) | 2023 (kg) | 2023 (CO2) | 2024 (kg) | 2024 (CO2) | Avg (kg) | Avg (CO2) |

→ year_1 = 2022, year_2 = 2023, year_3 = 2024

### Data Rows

| Field | Type | Notes |
|-------|------|-------|
| is_title | bool | true = section header (e.g., "Sản xuất chất kiểm soát") |
| sequence | int | Continuous row number (title + data rows) |
| usage_type | str | production / import / export |
| substance_name | str | Title row: Vietnamese text. Data row: standardized from DB |
| substance_id | int/null | Database ID (null if [UNKNOWN]) |
| hs_code | str/null | HS code from document |
| year_1_quantity_kg | float/null | Quantity (kg) for year_1 |
| year_1_quantity_co2 | float/null | CO2 equivalent for year_1 |
| year_2_quantity_kg | float/null | Quantity (kg) for year_2 |
| year_2_quantity_co2 | float/null | CO2 equivalent for year_2 |
| year_3_quantity_kg | float/null | Quantity (kg) for year_3 |
| year_3_quantity_co2 | float/null | CO2 equivalent for year_3 |
| avg_quantity_kg | float/null | Average quantity |
| avg_quantity_co2 | float/null | Average CO2 |
| notes | str/null | From "Other information" column |

### EXAMPLE JSON Output

{
  "year_1": 2022,
  "year_2": 2023,
  "year_3": 2024,
  "has_table_1_1": true,
  "substance_usage": [
    {
      "is_title": true,
      "sequence": 1,
      "usage_type": "production",
      "substance_name": "Sản xuất chất được kiểm soát",
      "substance_id": null,
      "hs_code": null,
      "year_1_quantity_kg": null,
      "year_1_quantity_co2": null
    },
    {
      "is_title": false,
      "sequence": 2,
      "usage_type": "production",
      "substance_name": "HFC-134a",
      "substance_id": 123,
      "hs_code": "2903.39.1100",
      "year_1_quantity_kg": 150.5,
      "year_1_quantity_co2": 215.215
    }
  ]
}
"""


def get_equipment_product_schema(form_type):
    """Schema for equipment_product category (Table 1.2)."""
    if form_type != '01':
        return ""

    return """## EQUIPMENT PRODUCT SCHEMA (Table 1.2)

Extract equipment/product manufacturing data.

### Capacity Columns Detection (CRITICAL!)

**Check table structure:**
- **1 capacity column** → Set is_capacity_merged_table_1_2 = true
  - Use field: `capacity` (combined "5 HP / 3.5 kW")
- **2 capacity columns** → Set is_capacity_merged_table_1_2 = false
  - Use fields: `cooling_capacity` ("5 HP"), `power_capacity` ("3.5 kW")

### Data Rows

| Field | Type | When to Use |
|-------|------|-------------|
| is_title | bool | Section header vs data |
| sequence | int | Continuous row number |
| production_type | str | production / import |
| product_type | str | Equipment model or section title |
| hs_code | str/null | HS code |
| capacity | str/null | ONLY if is_capacity_merged = true |
| cooling_capacity | str/null | ONLY if is_capacity_merged = false |
| power_capacity | str/null | ONLY if is_capacity_merged = false |
| quantity | float/null | Equipment quantity |
| substance_name | str/null | Standardized substance name |
| substance_id | int/null | Database ID |
| substance_quantity_per_unit | str/null | Substance per unit (supports text like "0.5-1.0") |
| notes | str/null | Notes column |

### EXAMPLE JSON Output

{
  "has_table_1_2": true,
  "is_capacity_merged_table_1_2": false,
  "equipment_product": [
    {
      "is_title": true,
      "sequence": 1,
      "production_type": "production",
      "product_type": "Sản xuất thiết bị"
    },
    {
      "is_title": false,
      "sequence": 2,
      "production_type": "production",
      "product_type": "Điều hòa không khí gia dụng",
      "hs_code": "8415.10",
      "cooling_capacity": "9000 BTU",
      "power_capacity": "2.5 kW",
      "quantity": 1000,
      "substance_name": "HFC-32",
      "substance_id": 45,
      "substance_quantity_per_unit": "0.65"
    }
  ]
}
"""


def get_equipment_ownership_schema(form_type):
    """Schema for equipment_ownership category (Table 1.3)."""
    if form_type != '01':
        return ""

    return """## EQUIPMENT OWNERSHIP SCHEMA (Table 1.3)

Extract owned equipment inventory data.

### Capacity Columns Detection

Same as Table 1.2:
- 1 column → is_capacity_merged_table_1_3 = true → Use `capacity`
- 2 columns → is_capacity_merged_table_1_3 = false → Use `cooling_capacity` + `power_capacity`

### Data Rows

| Field | Type | When to Use |
|-------|------|-------------|
| is_title | bool | Section header vs data |
| sequence | int | Continuous row number |
| ownership_type | str | air_conditioner / refrigeration |
| equipment_type | str | Equipment model or section title |
| start_year | int/null | Year put into use |
| capacity | str/null | ONLY if is_capacity_merged = true |
| cooling_capacity | str/null | ONLY if is_capacity_merged = false |
| power_capacity | str/null | ONLY if is_capacity_merged = false |
| equipment_quantity | int/null | Number of units |
| substance_name | str/null | Standardized substance name |
| substance_id | int/null | Database ID |
| refill_frequency | str/null | Refill frequency (e.g., "2 lần/năm") |
| substance_quantity_per_refill | str/null | Quantity per refill (e.g., "5.5 kg") |

### EXAMPLE JSON Output

{
  "has_table_1_3": true,
  "is_capacity_merged_table_1_3": false,
  "equipment_ownership": [...]
}
"""


def get_collection_recycling_schema(form_type):
    """Schema for collection_recycling category (Table 1.4)."""
    if form_type != '01':
        return ""

    return """## COLLECTION/RECYCLING SCHEMA (Table 1.4)

Extract collection, reuse, recycling, disposal data.

### Data Rows

| Field | Type | Notes |
|-------|------|-------|
| is_title | bool | Section header vs data |
| sequence | int | Continuous row number |
| activity_type | str | collection / reuse / recycle / disposal |
| substance_name | str | Substance or section title |
| substance_id | int/null | Database ID |
| quantity_kg | float/null | Quantity (kg) |
| quantity_co2 | float/null | CO2 equivalent |
| notes | str/null | Other information |

### EXAMPLE JSON Output

{
  "has_table_1_4": true,
  "collection_recycling": [...]
}
"""


def get_quota_usage_schema(form_type):
    """Schema for quota_usage category (Table 2.1 - Form 02)."""
    if form_type != '02':
        return ""

    return """## QUOTA USAGE SCHEMA (Table 2.1 - Form 02)

Extract quota usage and customs declaration data.

### CRITICAL: 3 Separate Quota Column Groups

**Columns 4-5:** "Hạn ngạch được phân bổ" → allocated_quota_kg, allocated_quota_co2
**Columns 6-7:** "Hạn ngạch được điều chỉnh" → adjusted_quota_kg, adjusted_quota_co2
**Columns 8-9:** "Tổng hạn ngạch" → total_quota_kg, total_quota_co2

⚠️ **EMPTY CELLS → null**
DO NOT copy values between quota columns!

### Data Rows

| Field | Type | Notes |
|-------|------|-------|
| is_title | bool | Section header vs data |
| sequence | int | Continuous row number |
| usage_type | str | production / import / export |
| substance_name | str | Standardized substance name |
| substance_id | int/null | Database ID |
| hs_code | str/null | HS code |
| allocated_quota_kg | float/null | Column 4 - null if empty! |
| allocated_quota_co2 | float/null | Column 5 - null if empty! |
| adjusted_quota_kg | float/null | Column 6 - can be negative |
| adjusted_quota_co2 | float/null | Column 7 - can be negative |
| total_quota_kg | float/null | Column 8 - null if empty! |
| total_quota_co2 | float/null | Column 9 - null if empty! |
| average_price | str/null | Price (USD) - supports text |
| country_text | str/null | Country name |
| customs_declaration_number | str/null | Preserve exact format |
| next_year_quota_kg | float/null | Next year quota (kg) |
| next_year_quota_co2 | float/null | Next year CO2 |
| notes | str/null | Other information |

### EXAMPLE JSON Output

{
  "year_1": 2024,
  "has_table_2_1": true,
  "quota_usage": [...]
}
"""


def get_equipment_product_report_schema(form_type):
    """Schema for equipment_product_report category (Table 2.2 - Form 02)."""
    if form_type != '02':
        return ""

    return """## EQUIPMENT PRODUCT REPORT SCHEMA (Table 2.2 - Form 02)

Extract equipment/product report data.

### Capacity Columns Detection

Same as Table 1.2:
- 1 column → is_capacity_merged_table_2_2 = true
- 2 columns → is_capacity_merged_table_2_2 = false

### Data Rows (same structure as Table 1.2)

| Field | Type | Notes |
|-------|------|-------|
| is_title | bool | Section header vs data |
| sequence | int | Continuous row number |
| production_type | str | production / import |
| product_type | str | Equipment model or section title |
| hs_code | str/null | HS code |
| capacity | str/null | ONLY if merged = true |
| cooling_capacity | str/null | ONLY if merged = false |
| power_capacity | str/null | ONLY if merged = false |
| quantity | float/null | Equipment quantity |
| substance_name | str/null | Standardized substance name |
| substance_id | int/null | Database ID |
| substance_quantity_per_unit | str/null | Substance per unit |
| notes | str/null | Notes column |

### EXAMPLE JSON Output

{
  "has_table_2_2": true,
  "is_capacity_merged_table_2_2": false,
  "equipment_product_report": [...]
}
"""


def get_equipment_ownership_report_schema(form_type):
    """Schema for equipment_ownership_report category (Table 2.3 - Form 02)."""
    if form_type != '02':
        return ""

    return """## EQUIPMENT OWNERSHIP REPORT SCHEMA (Table 2.3 - Form 02)

Extract owned equipment report data.

### Capacity Columns Detection

Same as Table 1.3:
- 1 column → is_capacity_merged_table_2_3 = true
- 2 columns → is_capacity_merged_table_2_3 = false

### Data Rows (same structure as Table 1.3)

| Field | Type | Notes |
|-------|------|-------|
| is_title | bool | Section header vs data |
| sequence | int | Continuous row number |
| ownership_type | str | air_conditioner / refrigeration |
| equipment_type | str | Equipment model or section title |
| equipment_quantity | int/null | Number of units |
| substance_name | str/null | Standardized substance name |
| substance_id | int/null | Database ID |
| capacity | str/null | ONLY if merged = true |
| cooling_capacity | str/null | ONLY if merged = false |
| power_capacity | str/null | ONLY if merged = false |
| start_year | int/null | Year put into use |
| refill_frequency | str/null | Refill frequency |
| substance_quantity_per_refill | str/null | Quantity per refill |
| notes | str/null | Notes/remarks |

### EXAMPLE JSON Output

{
  "has_table_2_3": true,
  "is_capacity_merged_table_2_3": false,
  "equipment_ownership_report": [...]
}
"""


def get_collection_recycling_report_schema(form_type):
    """Schema for collection_recycling_report category (Table 2.4 - Form 02)."""
    if form_type != '02':
        return ""

    return """## COLLECTION/RECYCLING REPORT SCHEMA (Table 2.4 - Form 02)

Extract collection/recycling report data.

### Data Rows with Title Support

⚠️ IMPORTANT: This table supports TITLE ROWS for section headers.
- If row is title: `is_title=true`, `title_name="section text"`, other fields null
- If row is data: `is_title=false`, `title_name=null`, substance_name and data fields populated

| Field | Type | Description |
|-------|------|-------------|
| is_title | bool | True for section title rows, False for data rows |
| title_name | str/null | Title text for section headers (only if is_title=true) |
| sequence | int | Row sequence number for ordering |
| substance_name | str/null | Standardized substance name (only if is_title=false) |
| collection_quantity_kg | float/null | Collection quantity (kg) |
| collection_location | str/null | Collection location |
| storage_location | str/null | Storage location |
| reuse_quantity_kg | float/null | Reuse quantity (kg) |
| reuse_technology | str/null | Reuse technology |
| recycle_quantity_kg | float/null | Recycle quantity (kg) |
| recycle_technology | str/null | Recycle technology |
| recycle_usage_location | str/null | Recycle usage location |
| disposal_quantity_kg | float/null | Disposal quantity (kg) |
| disposal_technology | str/null | Disposal technology |
| disposal_facility | str/null | Disposal facility |
| notes | str/null | From column "Other information" |

### EXAMPLE JSON Output

{
  "has_table_2_4": true,
  "collection_recycling_report": [
    {
      "is_title": true,
      "sequence": 1,
      "title_name": "Thu gom chất được kiểm soát",
      "substance_name": null
    },
    {
      "is_title": false,
      "sequence": 2,
      "title_name": null,
      "substance_name": "HFC-134a",
      "collection_quantity_kg": 100,
      "collection_location": "TP.HCM"
    }
  ]
}
"""


def get_schema_for_category(category, form_type):
    """
    Get schema for specific category.

    Args:
        category: 'metadata', 'substance_usage', 'equipment_product', etc.
        form_type: '01' or '02'

    Returns:
        str: Schema prompt for that category
    """
    schema_map = {
        'metadata': get_metadata_schema,
        'substance_usage': get_substance_usage_schema,
        'equipment_product': get_equipment_product_schema,
        'equipment_ownership': get_equipment_ownership_schema,
        'collection_recycling': get_collection_recycling_schema,
        'quota_usage': get_quota_usage_schema,
        'equipment_product_report': get_equipment_product_report_schema,
        'equipment_ownership_report': get_equipment_ownership_report_schema,
        'collection_recycling_report': get_collection_recycling_report_schema,
    }

    schema_func = schema_map.get(category)
    if schema_func:
        return schema_func(form_type)
    return ""
