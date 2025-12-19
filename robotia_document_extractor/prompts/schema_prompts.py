# -*- coding: utf-8 -*-

"""
Schema prompts - Form-specific JSON schemas in compact table format
"""


def get_form_01_schema():
    """Form 01 JSON schema (compact table format)
    
    Returns:
        str: Form 01 schema prompt
    """
    return """
## FORM 01 OUTPUT SCHEMA

### Metadata Fields

| Field | Type | Extract From | Notes |
|-------|------|--------------|-------|
| year | int | Header "Đăng ký năm 2024" | Registration year |
| year_1 | int | Table 1.1 column header (1st year) | From merged cell |
| year_2 | int | Table 1.1 column header (2nd year) | From merged cell |
| year_3 | int | Table 1.1 column header (3rd year) | From merged cell |
| organization_name | str | "Tên tổ chức:" section | Must be specific |
| business_id | str | "Mã số doanh nghiệp:" | Không phải "Số ký hiệu của giấy phép đăng ký kinh doanh |
| business_license_date | str/null | "Ngày đăng ký giấy phép kinh doanh lần đầu" or "Đăng ký lần đầu:" | FIRST date if multiple, FORMAT (MUST HAVE): YYYY-MM-DD |
| business_license_place | str | "Nơi đăng ký:" | Full place name |
| legal_representative_name | str | Representative section | - |
| legal_representative_position | str | Representative section | - |
| contact_person_name | str | Contact section | - |
| contact_address | str | Contact section | Full address string |
| contact_phone | str | Contact section | - |
| contact_fax | str | Contact section | - |
| contact_email | str | Contact section | - |
| contact_country_code | str | Infer from address | VN, US, CN (2-letter) |
| contact_state_code | str/null | Lookup from address | VN-HN, VN-SG, etc. |
| activity_field_codes | array[str] | Infer from table data | Use table presence first |

### Table Presence Flags

| Field | Type | Condition |
|-------|------|-----------|
| has_table_1_1 | bool | any(production, import, export) checked |
| has_table_1_2 | bool | any(equipment_production, equipment_import) checked |
| has_table_1_3 | bool | any(ac_ownership, refrigeration_ownership) checked |
| has_table_1_4 | bool | collection_recycling checked |
| is_capacity_merged_table_1_2 | bool | Table 1.2: 1 column=true, 2 columns=false |
| is_capacity_merged_table_1_3 | bool | Table 1.3: 1 column=true, 2 columns=false |

### Table 1.1: substance_usage (array)

| Field | Type | Description |
|-------|------|-------------|
| is_title | bool | true=section header, false=data row |
| sequence | int | Row order (continuous across title+data) |
| usage_type | str | production/import/export |
| substance_name | str | Title: Vietnamese text. Data: standardized name |
| year_1_quantity_kg | float/null | Quantity (kg) for year_1 |
| year_1_quantity_co2 | float/null | CO2 equivalent for year_1 |
| year_2_quantity_kg | float/null | Quantity (kg) for year_2 |
| year_2_quantity_co2 | float/null | CO2 equivalent for year_2 |
| year_3_quantity_kg | float/null | Quantity (kg) for year_3 |
| year_3_quantity_co2 | float/null | CO2 equivalent for year_3 |
| avg_quantity_kg | float/null | Average quantity (kg) |
| avg_quantity_co2 | float/null | Average CO2 |
| notes | str/null | From column "Other information" |

### Table 1.2: equipment_product (array)

**IMPORTANT**: Check `is_capacity_merged_table_1_2` to know which capacity fields to fill.

| Field | Type | When to Use |
|-------|------|-------------|
| is_title | bool | Section header vs data row |
| sequence | int | Row order |
| product_type | str | Equipment model or section title |
| hs_code | str | HS code (8415.10, etc.) |
| capacity | str/null | ONLY if merged=TRUE. Combined "5 HP/3.5 kW" |
| cooling_capacity | str/null | ONLY if merged=FALSE. "5 HP" only |
| power_capacity | str/null | ONLY if merged=FALSE. "3.5 kW" only |
| quantity | float/null | Equipment quantity |
| substance_name | str | Standardized name (null if is_title=true) |
| substance_quantity_per_unit | str/null | Substance per unit (kg) - supports text values |
| substance_quantity_per_unit | str/null | Substance per unit (kg) - supports text values |
| notes | str/null | From column "Notes" |

### Table 1.3: equipment_ownership (array)

**IMPORTANT**: Check `is_capacity_merged_table_1_3` to know which capacity fields to fill.

| Field | Type | When to Use |
|-------|------|-------------|
| is_title | bool | Section header vs data row |
| sequence | int | Row order |
| equipment_type | str | Equipment model or section title |
| start_year | int/null | Year put into use |
| capacity | str/null | ONLY if merged=TRUE |
| cooling_capacity | str/null | ONLY if merged=FALSE |
| power_capacity | str/null | ONLY if merged=FALSE |
| equipment_quantity | int/null | Number of units |
| substance_name | str | Standardized name |
| refill_frequency | str/null | Tần suất nạp mới chất kiểm soát trên 1 năm |
| substance_quantity_per_refill | str/null | Lượng chất được nạp vào trên 1 lần |

### Table 1.4: collection_recycling (array)

| Field | Type | Notes |
|-------|------|-------|
| is_title | bool | Section header vs data |
| sequence | int | Row order |
| activity_type | str | collection/reuse/recycle/disposal |
| substance_name | str | Substance or section title |
| quantity_kg | float/null | Quantity in kg |
| quantity_co2 | float/null | CO2 equivalent |
| notes | str/null | From column "Other information" |

### JSON Output Template

{
  "year": 2024,
  "year_1": 2022,
  "year_2": 2023,
  "year_3": 2024,
  "organization_name": "...",
  "business_id": "...",
  "activity_field_codes": ["production", "import"],
  "has_table_1_1": true,
  "is_capacity_merged_table_1_2": false,
  "substance_usage": [
    {"is_title": true, "sequence": 1, "substance_name": "Sản xuất chất được kiểm soát", "usage_type": "production", ...},
    {"is_title": false, "sequence": 2, "substance_name": "HFC-134a", "usage_type": "production", ...}
  ],
  "equipment_product": [...],
  "equipment_ownership": [...],
  "collection_recycling": [...]
}

**OUTPUT REQUIREMENTS:**
1. Return ONLY valid JSON (no markdown, no explanations)
2. Use null for missing values
3. Preserve Vietnamese characters
4. Include ALL fields from tables above
"""


def get_form_02_schema():
    """Form 02 JSON schema (compact table format)
    
    Returns:
        str: Form 02 schema prompt
    """
    return """
## FORM 02 OUTPUT SCHEMA

### Metadata Fields

| Field | Type | Extract From | Notes |
|-------|------|--------------|-------|
| year | int | Header "Báo cáo năm 2024" | Report year |
| year_1 | int | Table 2.1 column header (1st year) | From merged cell |
| year_2 | int | Table 2.1 column header (2nd year) | From merged cell |
| year_3 | int | Table 2.1 column header (3rd year) | From merged cell |
| organization_name | str | "Tên tổ chức:" section | Must be specific |
| business_id | str | "Mã số doanh nghiệp:" | Không phải "Số ký hiệu của giấy phép đăng ký kinh doanh |
| business_license_date | str/null | "Ngày đăng ký giấy phép kinh doanh lần đầu" or "Đăng ký lần đầu:" | FIRST date if multiple, FORMAT (MUST HAVE): YYYY-MM-DD |
| business_license_place | str | "Nơi đăng ký:" | Full place name |
| legal_representative_name | str | Representative section | - |
| legal_representative_position | str | Representative section | - |
| contact_person_name | str | Contact section | - |
| contact_address | str | Contact section | Full address string |
| contact_phone | str | Contact section | - |
| contact_fax | str | Contact section | - |
| contact_email | str | Contact section | - |
| contact_country_code | str | Infer from address | VN, US, CN (2-letter) |
| contact_state_code | str/null | Lookup from address | VN-HN, VN-SG, etc. |
| activity_field_codes | array[str] | Infer from table data | Use table presence first |

### Table Presence Flags

| Field | Type | Condition |
|-------|------|-----------|
| has_table_2_1 | bool | any(production, import, export) checked |
| has_table_2_2 | bool | any(equipment_production, equipment_import) checked |
| has_table_2_3 | bool | any(ac_ownership, refrigeration_ownership) checked |
| has_table_2_4 | bool | collection_recycling checked |
| is_capacity_merged_table_2_2 | bool | Table 2.2: 1 column=true, 2 columns=false |
| is_capacity_merged_table_2_3 | bool | Table 2.3: 1 column=true, 2 columns=false |

### Table 2.1: quota_usage (array)

**CRITICAL EXTRACTION RULES FOR TABLE 2.1:**

⚠️ **COLUMN IDENTIFICATION - READ CAREFULLY:**

Table 2.1 has THREE separate quota column groups (6 columns total for quotas):

1. **Columns 4-5**: "Hạn ngạch được phân bổ phân bổ trong năm báo cáo" 
   - → `allocated_quota_kg` and `allocated_quota_co2`
   
2. **Columns 6-7**: "Hạn ngạch được điều chỉnh sung trong năm báo cáo"
   - → `adjusted_quota_kg` and `adjusted_quota_co2`
   
3. **Columns 8-9**: "Tổng hạn ngạch sử dụng trong năm báo cáo hết 31 tháng 12 của năm báo cáo"
   - → `total_quota_kg` and `total_quota_co2`

**⚠️ EMPTY CELL HANDLING - CRITICAL:**

- If a cell is EMPTY/BLANK → use `null`
- DO NOT copy values from one quota column to another
- DO NOT assume empty columns should have the same value as filled columns
- Each column group is INDEPENDENT - they can have different values or be empty

**Example:**
- If "Hạn ngạch được phân bổ" columns are EMPTY → `allocated_quota_kg: null, allocated_quota_co2: null`
- If "Tổng hạn ngạch" columns have values 2260/9006.1 → `total_quota_kg: 2260.0, total_quota_co2: 9006.1`
- DO NOT put 2260/9006.1 into allocated_quota fields!

| Field | Type | Description |
|-------|------|-------------|
| is_title | bool | true=section header, false=data row |
| sequence | int | Row order (continuous) |
| usage_type | str | production/import/export |
| substance_name | str | Title: Vietnamese text. Data: standardized name |
| hs_code | str | HS code from document |
| allocated_quota_kg | float/null | **Column 4** - Allocated quota (kg). null if empty! |
| allocated_quota_co2 | float/null | **Column 5** - Allocated CO2. null if empty! |
| adjusted_quota_kg | float/null | **Column 6** - Adjusted quota (can be negative). null if empty! |
| adjusted_quota_co2 | float/null | **Column 7** - Adjusted CO2 (can be negative). null if empty! |
| total_quota_kg | float/null | **Column 8** - Total quota (kg). null if empty! |
| total_quota_co2 | float/null | **Column 9** - Total CO2. null if empty! |
| average_price | str/null | Average price (USD) - supports text values |
| country_text | str | Country name from document |
| customs_declaration_number | str/null | Customs declaration number (preserve exact format) |
| next_year_quota_kg | float/null | Next year quota (kg) |
| next_year_quota_co2 | float/null | Next year CO2 |
| notes | str/null | From column "Other information" |

### Table 2.2: equipment_product_report (array)

**IMPORTANT**: Check `is_capacity_merged_table_2_2` to know which capacity fields to fill.

| Field | Type | When to Use |
|-------|------|-------------|
| is_title | bool | Section header vs data row |
| sequence | int | Row order |
| production_type | str | production/import |
| product_type | str | Equipment model or section title |
| hs_code | str | HS code |
| capacity | str/null | ONLY if merged=TRUE |
| cooling_capacity | str/null | ONLY if merged=FALSE |
| power_capacity | str/null | ONLY if merged=FALSE |
| quantity | float/null | Equipment quantity |
| substance_name | str | Standardized name |
| substance_quantity_per_unit | str/null | Substance per unit (kg) - supports text values |
| substance_quantity_per_unit | str/null | Substance per unit (kg) - supports text values |
| notes | str/null | From column "Notes" |

### Table 2.3: equipment_ownership_report (array)

**IMPORTANT**: Check `is_capacity_merged_table_2_3` to know which capacity fields to fill.

| Field | Type | When to Use |
|-------|------|-------------|
| is_title | bool | Section header vs data row |
| sequence | int | Row order |
| ownership_type | str | air_conditioner/refrigeration |
| equipment_type | str | Equipment model or section title |
| equipment_quantity | int/null | Number of units |
| substance_name | str | Standardized name |
| capacity | str/null | ONLY if merged=TRUE |
| cooling_capacity | str/null | ONLY if merged=FALSE |
| power_capacity | str/null | ONLY if merged=FALSE |
| start_year | int/null | Year put into use |
| refill_frequency | str/null | Tần suất nạp mới chất kiểm soát trên 1 năm |
| substance_quantity_per_refill | str/null | Lượng chất được nạp vào trên 1 lần |
| notes | str/null | Notes/remarks |

### Table 2.4: collection_recycling_report (array)

**IMPORTANT**: NO is_title field in this table. All rows are data rows.

| Field | Type | Description |
|-------|------|-------------|
| substance_name | str | Standardized substance name |
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

### JSON Output Template

{
  "year": 2024,
  "year_1": 2022,
  "year_2": 2023,
  "year_3": 2024,
  "organization_name": "...",
  "quota_usage": [
    {"is_title": true, "sequence": 1, "substance_name": "Sản xuất", "usage_type": "production", ...},
    {"is_title": false, "sequence": 2, "substance_name": "HFC-134a", "usage_type": "production", ...}
  ],
  "equipment_product_report": [...],
  "equipment_ownership_report": [...],
  "collection_recycling_report": [
    {"substance_name": "HFC-134a", "collection_quantity_kg": 100, ...}
  ]
}

**OUTPUT REQUIREMENTS:**
1. Return ONLY valid JSON (no markdown, no explanations)
2. Use null for missing values
3. Preserve Vietnamese characters
4. Include ALL fields from tables above
"""
