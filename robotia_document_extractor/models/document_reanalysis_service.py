# -*- coding: utf-8 -*-

import json
import logging
import tempfile
import os
import time

from odoo import models, api

try:
    from google import genai
    from google.genai import types
except ImportError:
    raise ValueError("Google Generative AI library not installed")

_logger = logging.getLogger(__name__)


class DocumentReanalysisService(models.AbstractModel):
    """AI-powered document re-analysis service"""
    _name = 'document.reanalysis.service'
    _description = 'Document Re-analysis Service'

    @api.model
    def verify_and_suggest_corrections(self, pdf_binary, current_data, document_type, filename):
        """
        Verify current data against PDF and suggest corrections

        Args:
            pdf_binary (bytes): PDF binary data
            current_data (dict): Current form state as JSON
            document_type (str): '01' or '02'
            filename (str): PDF filename

        Returns:
            dict: {
                "changes": {...},  # Delta changes (only incorrect fields)
                "analysis": "..."   # Verification report in Vietnamese
            }
        """
        _logger.info(f"Starting verification for {filename}")

        # Get config
        ICP = self.env['ir.config_parameter'].sudo()
        api_key = ICP.get_param('robotia_document_extractor.gemini_api_key')
        if not api_key:
            raise ValueError("Gemini API key not configured")

        client = genai.Client(api_key=api_key)

        # Build verification prompt (includes extraction rules summary)
        prompt = self._build_verification_prompt(
            current_data=current_data,
            document_type=document_type
        )

        # Get model config
        GEMINI_MODEL = ICP.get_param('robotia_document_extractor.gemini_model', default='gemini-2.5-pro')
        GEMINI_MAX_TOKENS = int(ICP.get_param('robotia_document_extractor.gemini_max_output_tokens', default='65536'))

        tmp_file_path = None
        uploaded_file = None

        try:
            # Create temp file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                tmp_file.write(pdf_binary)
                tmp_file_path = tmp_file.name

            # Upload to Gemini
            uploaded_file = client.files.upload(file=tmp_file_path)
            _logger.info(f"File uploaded: {uploaded_file.name}")

            # Wait for processing
            poll_count = 0
            while uploaded_file.state.name == "PROCESSING":
                if poll_count >= 30:
                    raise TimeoutError("Gemini processing timeout")
                time.sleep(2)
                uploaded_file = client.files.get(name=uploaded_file.name)
                poll_count += 1

            if uploaded_file.state.name == "FAILED":
                raise ValueError("Gemini processing failed")

            # Generate content
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[uploaded_file, prompt],
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=GEMINI_MAX_TOKENS,
                    response_mime_type='application/json',
                )
            )

            delta_text = response.text
            _logger.info(f"Response received ({len(delta_text)} chars)")

            # Parse JSON
            delta_changes = json.loads(delta_text)
            return delta_changes

        finally:
            # Cleanup
            if tmp_file_path and os.path.exists(tmp_file_path):
                os.unlink(tmp_file_path)
            if uploaded_file:
                client.files.delete(name=uploaded_file.name)

    def _build_verification_prompt(self, current_data, document_type):
        """Build verification prompt with extraction rules summary"""
        form_name = "Form 01 (Đăng ký)" if document_type == '01' else "Form 02 (Báo cáo)"

        # Get extraction rules summary from original prompts
        extraction_rules = self._get_extraction_rules_summary(document_type)

        return f"""
# DOCUMENT VERIFICATION SPECIALIST

Bạn là chuyên gia kiểm tra tài liệu {form_name} tiếng Việt về chất có kiểm soát.

## NHIỆM VỤ

Bạn có 2 inputs:
1. **PDF gốc** (đính kèm) - tài liệu cần verify
2. **Current data** (dữ liệu form hiện tại - xem bên dưới)

Nhiệm vụ của bạn:
1. **Đọc PDF** với OCR tốt nhất
2. **Verify** từng field trong current data có đúng với PDF không
3. **Chỉ trả về** các field SAI hoặc THIẾU (delta changes)
4. **KHÔNG** trả về field đã đúng

## CURRENT DATA (Cần verify)

```json
{json.dumps(current_data, ensure_ascii=False, indent=2)}
```

## QUY TẮC TRÍCH XUẤT (Context quan trọng)

{extraction_rules}

## OUTPUT FORMAT

Chỉ trả về các field SAI hoặc THIẾU:

```json
{{
  "changes": {{
    "year": 2024,  // Chỉ nếu sai so với PDF
    "organization_name": "Tên đúng từ PDF",

    "substance_usage_ids": [
      {{
        "id": 42,  // Match bằng ID (ưu tiên)
        "year_1_quantity_kg": 150.5  // Giá trị đúng từ PDF
      }},
      {{
        "sequence": 5,  // Match bằng sequence (fallback)
        "substance_name": "R-410A"
      }},
      {{
        "_action": "create",  // Record thiếu trong current data
        "_insert_after_sequence": 5,
        "substance_name": "HFC-32",
        "year_1_quantity_kg": 120.0
      }}
    ]
  }},
  "analysis": "BÁO CÁO KIỂM TRA:\\n\\n1. ĐÚNG: organization_name, year, year_1\\n2. SAI: year_1_quantity_kg của HFC-134a - PDF ghi 150.5 kg nhưng form có 100.0 kg\\n3. THIẾU: Chất HFC-32 có trong PDF nhưng chưa có trong form\\n\\nKẾT LUẬN: Tìm thấy 2 lỗi cần sửa."
}}
```

## LƯU Ý QUAN TRỌNG

1. **CHỈ** trả về field SAI hoặc THIẾU
2. **KHÔNG** trả về field đã đúng
3. Nếu current data 100% chính xác: trả về `{{"changes": {{}}, "analysis": "Tất cả dữ liệu đã chính xác. Không cần thay đổi."}}`
4. Analysis phải chi tiết: liệt kê field đúng, field sai, lý do
5. Match One2many: ID → sequence → create new
6. Sử dụng substance standardization (HFC-134a, R-410A, v.v.)

BẮT ĐẦU VERIFICATION. Chỉ trả về JSON (không markdown).
"""

    def _get_extraction_rules_summary(self, document_type):
        """
        Get summary of extraction rules from original prompts

        Returns:
            str: Concise extraction rules for context
        """
        common_rules = """
**Quy tắc chung:**
- Substance names: Chuẩn hóa theo danh sách chính thức (HFC-134a, R-410A, HCFC-22, v.v.)
- Numbers: Loại bỏ thousands separator, dùng dấu chấm cho decimal
- Line wrap: Số bị xuống dòng phải ghép lại (VD: "300.0" + "00" = 300000, KHÔNG phải 30000)
- Template data: BỎ QUA placeholder text, example markers, instruction text
- Title rows: is_title=True cho section headers, is_title=False cho data rows

**Year fields:**
- year: Năm đăng ký/báo cáo (từ document header)
- year_1, year_2, year_3: Năm từ table column headers (merged cells trên cột số liệu)

**Activity fields:**
- Mapping: "Sản xuất chất" → production, "Nhập khẩu chất" → import, v.v.
- Chỉ lấy activity được check/đánh dấu

**Capacity fields (Table 1.2, 1.3, 2.2, 2.3):**
- Nếu 1 cột merged "Năng suất lạnh/Công suất điện": lưu nguyên vào capacity
- Nếu 2 cột riêng: cooling_capacity (HP/BTU/TR/RT) và power_capacity (kW/W)
"""

        if document_type == '01':
            return common_rules + """
**Form 01 đặc thù:**
- Table 1.1: Substance usage (production, import, export)
- Table 1.2: Equipment/Product (sản xuất/nhập khẩu thiết bị)
- Table 1.3: Equipment ownership (sở hữu thiết bị)
- Table 1.4: Collection/Recycling (thu gom, tái chế, tái sử dụng, tiêu hủy)
  → Mỗi row PDF tạo 4 records (collection, reuse, recycle, disposal) với activity_type khác nhau
"""
        else:
            return common_rules + """
**Form 02 đặc thù:**
- Table 2.1: Quota usage (hạn ngạch sản xuất/nhập/xuất)
  → Có allocated_quota, adjusted_quota, total_quota, country_text, customs_declaration_number
- Table 2.2: Equipment/Product report (báo cáo sản xuất/nhập khẩu thiết bị)
- Table 2.3: Equipment ownership report (báo cáo sở hữu thiết bị)
- Table 2.4: Collection/Recycling report (báo cáo thu gom, tái chế)
  → KHÔNG có title rows, mỗi row = 1 substance với tất cả activities
"""
