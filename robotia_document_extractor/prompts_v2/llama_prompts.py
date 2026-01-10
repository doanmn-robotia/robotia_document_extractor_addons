# -*- coding: utf-8 -*-

"""
Category-specific prompts for LlamaParse OCR.
Each category gets a tailored prompt for better OCR accuracy.
"""


def get_llama_category_prompt(category, form_type):
    """
    Get LlamaParse system prompt for specific category.

    LlamaParse uses these prompts to guide GPT-4 mini during OCR.
    More specific prompts = better table structure preservation.

    Args:
        category: Category name
        form_type: '01' or '02'

    Returns:
        str: LlamaParse system_prompt_append
    """

    # COMMON RULES for all table categories
    common_table_rules = """
⚠️ **CRITICAL - MERGED CELL HANDLING (APPLIES TO ALL TABLES):**

**GOAL**: Preserve table structure with merged cells information for accurate AI extraction.

**APPROACH 1 (Preferred): HTML Table with colspan/rowspan**

Use HTML `<table>` with `colspan` and `rowspan` attributes to preserve merged cell structure:

Example - Header with merged year columns:
```html
<thead>
  <tr>
    <th rowspan="2">STT</th>
    <th rowspan="2">Tên chất</th>
    <th colspan="2">2022</th>
    <th colspan="2">2023</th>
    <th colspan="2">2024</th>
  </tr>
  <tr>
    <th>kg</th>
    <th>CO2e</th>
    <th>kg</th>
    <th>CO2e</th>
    <th>kg</th>
    <th>CO2e</th>
  </tr>
</thead>
```

**APPROACH 2 (Fallback): Markdown + Text Annotations**

If HTML table cannot preserve structure, use Markdown table WITH text annotations:

```markdown
## Table Header Structure

**Header Row 1 (with merged cells):**
- Columns 1-2: "STT", "Tên chất" (span 2 rows)
- Columns 3-4: "Năm 2022" (merged, spans 2 columns)
- Columns 5-6: "Năm 2023" (merged, spans 2 columns)
- Columns 7-8: "Năm 2024" (merged, spans 2 columns)

**Header Row 2 (sub-headers):**
- Column 3: "Lượng (kg)"
- Column 4: "Lượng (tấn CO2tđ)"
- Column 5: "Lượng (kg)"
- Column 6: "Lượng (tấn CO2tđ)"
- Column 7: "Lượng (kg)"
- Column 8: "Lượng (tấn CO2tđ)"

| STT | Tên chất | kg | CO2e | kg | CO2e | kg | CO2e |
|-----|----------|-------|--------|-------|--------|-------|--------|
| 1   | R-410A   | 100.5 | 209.04 | 120.0 | 249.60 | 150.0 | 312.00 |
```

**APPROACH 3 (Last Resort): Plain Text with Clear Formatting**

If neither HTML nor Markdown table works, output as structured text:

```
=== BẢNG 1.1: SỬ DỤNG CHẤT KIỂM SOÁT ===

[HEADER STRUCTURE]
Row 1 (merged): STT | Tên chất | Năm 2022 (2 cols) | Năm 2023 (2 cols) | Năm 2024 (2 cols) | Trung bình (2 cols)
Row 2 (sub):    -   |    -     | kg | CO2e         | kg | CO2e         | kg | CO2e         | kg | CO2e

[DATA ROWS]
1. Sản xuất chất được kiểm soát (TITLE ROW)
2 | R-410A | 100.5 | 209.040 | 120.0 | 249.600 | 150.0 | 312.000 | 123.5 | 256.880
3 | HFC-32 | 80.0  | 54.400  | 90.0  | 61.200  | 100.0 | 68.000  | 90.0  | 61.200
```

**DETECTION RULES:**

1. **Visual Merged Cells**: Look for cells spanning multiple columns/rows
   - Horizontal merge: Text centered over multiple columns
   - Vertical merge: Text spans multiple rows (usually on left side)

2. **Text Hints**: Header text like "Năm ...", "Hạn ngạch ...", "Thông tin về ..."
   - Usually indicates merged cell grouping

3. **Sub-headers**: Second header row with "kg", "CO2e", "Công nghệ", etc.
   - Indicates parent headers are merged

**MANDATORY REQUIREMENTS:**

✓ **ALWAYS preserve merged cell information** (use colspan/rowspan OR text annotations)
✓ **Count columns correctly** - Include ALL columns even if merged
✓ **Preserve raw text** if table structure is unclear - better to have text than lose data
✓ **Document structure** - Add comments/annotations about merged cells
✓ **Never guess** - If cell boundaries unclear, describe what you see in text format

**EXAMPLES FROM VIETNAMESE REGULATORY FORMS:**

Common merged patterns in these documents:
- **Year groups**: "Năm 2022", "Năm 2023", "Năm 2024" each spanning (kg, CO2e) columns
- **Quota groups**: "Hạn ngạch phân bổ", "Điều chỉnh", "Tổng hạn ngạch" each spanning (kg, CO2e)
- **Activity groups**: "Thu gom", "Tái sử dụng", "Tái chế" each spanning multiple detail columns
- **Section titles**: Full-width merged cells for "Sản xuất chất được kiểm soát", "Nhập khẩu chất được kiểm soát"

---
"""

    prompts = {
        'metadata': """Trích xuất MARKDOWN từ phần thông tin chung của doanh nghiệp.

Tập trung vào:
- Năm đăng ký/báo cáo (tìm text: "trong năm ...", "năm báo cáo: ...")
- Tên tổ chức/doanh nghiệp
- Mã số doanh nghiệp (KHÔNG phải "Số ký hiệu của giấy phép...")
- Ngày đăng ký lần đầu (nếu có nhiều ngày, lấy ngày SỚM NHẤT)
- Nơi đăng ký
- Người đại diện pháp luật
- Thông tin liên hệ (địa chỉ, điện thoại, fax, email)
- Các checkbox lĩnh vực hoạt động (production, import, export, etc.)

Giữ nguyên:
- Tất cả dấu tiếng Việt
- Số điện thoại, fax (có dấu '-' và '()')
- Định dạng ngày tháng
- Tên riêng (không viết hoa toàn bộ nếu không cần thiết)

BỎ QUA: Header, footer, logo, chữ ký, con dấu.""",

        'substance_usage': f"""Trích xuất bảng sử dụng chất kiểm soát (Bảng {"1.1" if form_type == '01' else "2.1"}).

{common_table_rules}

**TABLE-SPECIFIC NOTES:**

Bảng này có đặc điểm:
- **Multi-year structure**: 3 năm (year_1, year_2, year_3) với merged headers
- **Paired columns**: Each year has (kg, CO2e) pair
- **Section titles**: "Sản xuất chất kiểm soát", "Nhập khẩu chất kiểm soát", "Xuất khẩu chất kiểm soát"
- **Summary rows**: Skip "Tổng cộng", "Tổng", "Cộng"

Expected column structure:
STT | Tên chất | Mã HS | Year1(kg) | Year1(CO2e) | Year2(kg) | Year2(CO2e) | Year3(kg) | Year3(CO2e) | Avg(kg) | Avg(CO2e) | Ghi chú

Output: HTML table with colspan/rowspan OR Markdown with structure annotations OR plain text with clear formatting.""",

        'equipment_product': f"""Trích xuất bảng thiết bị/sản phẩm (Bảng {"1.2" if form_type == '01' else "2.2"}).

{common_table_rules}

**TABLE-SPECIFIC NOTES:**

Bảng này có 2 POSSIBLE capacity structures:
- **Option A**: 1 merged capacity column "Công suất" containing "5 HP / 3.5 kW"
- **Option B**: 2 separate columns "Công suất thiết kế" (5) + "Công suất thực tế" (3.5) + "Đơn vị" (HP / kW)

**CRITICAL**: Detect and preserve exact structure (merged vs separate)

Output: HTML table OR Markdown with structure annotations OR plain text.""",

        'equipment_ownership': f"""Trích xuất bảng thiết bị sở hữu (Bảng {"1.3" if form_type == '01' else "2.3"}).

{common_table_rules}

**TABLE-SPECIFIC NOTES:**

Similar to Bảng 1.2:
- Capacity structure: merged (1 column) OR separate (2-3 columns)
- Detect and preserve exact structure

Special fields:
- "Tần suất nạp mới": Keep format like "2 lần/năm", "6 tháng/lần"
- "Năm đưa vào sử dụng": 4-digit year

Output: HTML table OR Markdown with structure annotations OR plain text.""",

        'collection_recycling': f"""Trích xuất bảng thu gom/tái chế (Bảng {"1.4" if form_type == '01' else "2.4"}).

{common_table_rules}

**TABLE-SPECIFIC NOTES:**

Bảng này có section title rows (full-width merged):
- "Thu gom chất được kiểm soát"
- "Tái sử dụng chất được kiểm soát sau thu gom"
- "Tái chế chất sau thu gom"
- "Xử lý chất được kiểm soát"

Use colspan for title rows, sequence numbers continue across sections.

Output: HTML table OR Markdown with structure annotations OR plain text.""",

        'quota_usage': f"""Trích xuất bảng hạn ngạch (Bảng 2.1 - Form 02).

{common_table_rules}

**TABLE-SPECIFIC NOTES:**

Bảng này có NHIỀU merged column groups (5 groups):
1. "Hạn ngạch được phân bổ" (2 cols: kg, CO2e)
2. "Hạn ngạch được điều chỉnh, bổ sung" (2 cols: kg, CO2e)
3. "Tổng lượng hạn ngạch" (6 cols: kg, CO2e, Giá trung bình, Nơi XK/NK, Số hiệu tờ khai HQ, and sub-headers)
4. "Đã sử dụng" (implied)
5. "Còn lại" (implied)

**CRITICAL**: Each quota group has SEPARATE values - DO NOT copy between groups!

Total columns ≈ 14

Output: HTML table with colspan OR Markdown with detailed structure annotations OR plain text.""",

        'equipment_product_report': f"""Trích xuất bảng báo cáo thiết bị/sản phẩm (Bảng 2.2 - Form 02).

{common_table_rules}

**TABLE-SPECIFIC NOTES:**

Cấu trúc GIỐNG Bảng 1.2:
- Capacity structure: merged (1 column) OR separate (2-3 columns)
- Detect and preserve exact structure

Output: HTML table OR Markdown with structure annotations OR plain text.""",

        'equipment_ownership_report': f"""Trích xuất bảng báo cáo thiết bị sở hữu (Bảng 2.3 - Form 02).

{common_table_rules}

**TABLE-SPECIFIC NOTES:**

Cấu trúc GIỐNG Bảng 1.3:
- Capacity structure: merged (1 column) OR separate (2-3 columns)
- Detect and preserve exact structure

Output: HTML table OR Markdown with structure annotations OR plain text.""",

        'collection_recycling_report': f"""Trích xuất bảng báo cáo thu gom/tái chế (Bảng 2.4 - Form 02).

{common_table_rules}

**TABLE-SPECIFIC NOTES:**

Bảng này có cấu trúc PHỨC TẠP với TITLE ROWS và merged headers:
- TITLE ROWS: Có thể có các dòng tiêu đề phân nhóm (vd: "Thu gom chất được kiểm soát", "Tái sử dụng", "Tái chế", "Tiêu hủy")
- MERGED HEADERS: Các cột được nhóm theo hoạt động:
  * "Thu gom" (merged cho 3 columns: Khối lượng, Địa điểm thu gom, Địa điểm lưu giữ)
  * "Tái sử dụng" (merged cho 2 columns: Khối lượng, Công nghệ)
  * "Tái chế" (merged cho 3 columns: Khối lượng, Công nghệ, Nơi sử dụng)
  * "Tiêu hủy" (merged cho 3 columns: Khối lượng, Công nghệ, Cơ sở xử lý)

CRITICAL: Preserve TITLE ROWS exactly - they structure the data!
Each substance = 1 row with MANY columns under its section

Output: HTML table with colspan OR Markdown with structure annotations OR plain text.
Mark title rows clearly if present.""",
    }

    return prompts.get(category, "Trích xuất MARKDOWN từ tài liệu.")
