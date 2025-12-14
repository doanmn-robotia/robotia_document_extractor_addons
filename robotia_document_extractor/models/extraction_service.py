# -*- coding: utf-8 -*-

from odoo import models, api
import json
import logging
import tempfile
import os
import time
from google import genai
from google.genai import types

# Import prompt modules
from odoo.addons.robotia_document_extractor.prompts import context_prompts, strategy_prompts

_logger = logging.getLogger(__name__)

        # Constants
GEMINI_POLL_INTERVAL_SECONDS = 2
GEMINI_MAX_POLL_RETRIES = 30  # 30 * 2s = 60s timeout

# Shared keyword mappings for activity codes
SUBSTANCE_KEYWORDS = {
    'Sản xuất': 'production',
    'Nhập khẩu': 'import',
    'Xuất khẩu': 'export'
}

EQUIPMENT_KEYWORDS = {
    'Sản xuất thiết bị': 'equipment_production',
    'Nhập khẩu thiết bị': 'equipment_import'
}

OWNERSHIP_KEYWORDS = {
    'Máy điều hòa': 'ac_ownership',
    'Thiết bị lạnh': 'refrigeration_ownership'
}

COLLECTION_KEYWORDS = {
    'Thu gom': 'collection_recycling',
    'Tái sử dụng': 'collection_recycling',
    'Tái chế': 'collection_recycling',
    'Xử lý': 'collection_recycling'
}

# Table-to-field mapping
TABLE_ACTIVITY_MAPPINGS = {
    'substance_usage': {'field_name': 'substance_name', 'keywords': SUBSTANCE_KEYWORDS},
    'quota_usage': {'field_name': 'substance_name', 'keywords': SUBSTANCE_KEYWORDS},
    'equipment_product': {'field_name': 'product_type', 'keywords': EQUIPMENT_KEYWORDS},
    'equipment_product_report': {'field_name': 'product_type', 'keywords': EQUIPMENT_KEYWORDS},
    'equipment_ownership': {'field_name': 'equipment_type', 'keywords': OWNERSHIP_KEYWORDS},
    'equipment_ownership_report': {'field_name': 'equipment_type', 'keywords': OWNERSHIP_KEYWORDS},
    'collection_recycling': {'field_name': 'activity_type', 'keywords': COLLECTION_KEYWORDS},
    'collection_recycling_report': {'field_name': 'substance_name', 'keywords': COLLECTION_KEYWORDS}
}


class DocumentExtractionService(models.AbstractModel):
    """
    AI-powered document extraction service using Google Gemini API

    This service extracts structured data from PDF documents
    using Google's Gemini with PDF understanding capability.
    """
    _name = 'document.extraction.service'
    _description = 'Document Extraction Service'

    def make_temp_file(self, data):
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf', prefix="hfc_ai_extraction") as tmp_file:
                tmp_file.write(data)
                tmp_file_path = tmp_file.name

        return tmp_file_path

    def upload_file_to_gemini(self, client, path):
        uploaded_file = client.files.upload(file=path)
        _logger.info(f"File uploaded to Gemini: {uploaded_file.name}")

        # Wait for file to be processed
        poll_count = 0
        while uploaded_file.state.name == "PROCESSING":
            if poll_count >= GEMINI_MAX_POLL_RETRIES:
                raise TimeoutError(f"Gemini file processing timeout after {GEMINI_MAX_POLL_RETRIES * GEMINI_POLL_INTERVAL_SECONDS}s")

            time.sleep(GEMINI_POLL_INTERVAL_SECONDS)
            uploaded_file = client.files.get(name=uploaded_file.name)
            poll_count += 1

        if uploaded_file.state.name == "FAILED":
            raise ValueError("File processing failed in Gemini")

        _logger.info(f"File processing completed: {uploaded_file.state.name}")

        return uploaded_file

    def generate_content(self, client, content):
        # Get max output tokens from config (default: 65536 for Gemini 2.0 Flash)
        # User can adjust this in Settings if needed
        GEMINI_MAX_TOKENS = int(
            self.env['ir.config_parameter'].sudo().get_param(
                'robotia_document_extractor.gemini_max_output_tokens',
                default='65536'
            )
        )

        # Get Gemini model from config (default: gemini-2.0-flash-exp)
        GEMINI_MODEL = self.env['ir.config_parameter'].sudo().get_param(
            'robotia_document_extractor.gemini_model',
            default='gemini-2.5-pro'
        )

        # Get Gemini generation parameters from config
        ICP = self.env['ir.config_parameter'].sudo()
        GEMINI_TEMPERATURE = float(ICP.get_param(
            'robotia_document_extractor.gemini_temperature',
            default='0.0'
        ))
        GEMINI_TOP_P = float(ICP.get_param(
            'robotia_document_extractor.gemini_top_p',
            default='0.95'
        ))
        GEMINI_TOP_K = int(ICP.get_param(
            'robotia_document_extractor.gemini_top_k',
            default='0'
        ))
        # Convert top_k=0 to None (no limit)
        GEMINI_TOP_K = None if GEMINI_TOP_K == 0 else GEMINI_TOP_K

        return client.models.generate_content(
            model=GEMINI_MODEL,
            contents=content,
            config=types.GenerateContentConfig(
                temperature=GEMINI_TEMPERATURE,
                max_output_tokens=GEMINI_MAX_TOKENS,
                response_mime_type='application/json',  # Force JSON output
                top_p=GEMINI_TOP_P,
                top_k=GEMINI_TOP_K
            )
        )

    def create_chat_session(self, client, system_instruction):
        """
        Create a Gemini chat session with system instruction
        
        Similar to generate_content but returns a chat session for multi-turn conversation.
        Uses same configuration parameters (temperature, top_p, top_k, max_tokens).
        
        Args:
            client: Gemini client instance
            system_instruction (str): System instruction for the chat
            
        Returns:
            Chat session object
        """
        # Get configuration (same as generate_content)
        ICP = self.env['ir.config_parameter'].sudo()
        
        GEMINI_MODEL = ICP.get_param(
            'robotia_document_extractor.gemini_model',
            default='gemini-2.5-pro'
        )
        
        GEMINI_MAX_TOKENS = int(ICP.get_param(
            'robotia_document_extractor.gemini_max_output_tokens',
            default='65536'
        ))
        
        GEMINI_TEMPERATURE = float(ICP.get_param(
            'robotia_document_extractor.gemini_temperature',
            default='0.0'
        ))
        
        GEMINI_TOP_P = float(ICP.get_param(
            'robotia_document_extractor.gemini_top_p',
            default='0.95'
        ))
        
        GEMINI_TOP_K = int(ICP.get_param(
            'robotia_document_extractor.gemini_top_k',
            default='0'
        ))
        GEMINI_TOP_K = None if GEMINI_TOP_K == 0 else GEMINI_TOP_K
        
        # Create chat session
        chat = client.chats.create(
            model=GEMINI_MODEL,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=GEMINI_TEMPERATURE,
                max_output_tokens=GEMINI_MAX_TOKENS,
                response_mime_type='application/json',
                top_p=GEMINI_TOP_P,
                top_k=GEMINI_TOP_K
            )
        )
        
        _logger.info(f"Created chat session with model {GEMINI_MODEL}")
        
        return chat

    def cleanup_temp_extraction_files(self):
        """
        Clean up all temporary extraction files with prefix 'hfc_ai_extraction'
        
        Removes stale temporary files from previous extraction attempts
        to prevent disk space issues. Should be called at the start of extraction.
        """
        import tempfile
        import glob
        
        temp_dir = tempfile.gettempdir()
        pattern = os.path.join(temp_dir, 'hfc_ai_extraction*')
        
        cleaned_count = 0
        for file_path in glob.glob(pattern):
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
                    cleaned_count += 1
                    _logger.debug(f"Cleaned up temp file: {file_path}")
            except Exception as e:
                _logger.warning(f"Failed to cleanup temp file {file_path}: {e}")
        
        if cleaned_count > 0:
            _logger.info(f"Cleaned up {cleaned_count} temporary extraction files")

    def _build_pdf_from_pages(self, pdf_binary, page_indexes):
        """
        Build a new PDF from selected pages of original PDF
        
        Args:
            pdf_binary (bytes): Original PDF binary
            page_indexes (list): List of 1-based page indexes to extract (e.g., [1, 2, 3])
            
        Returns:
            str: Path to temporary PDF file containing only selected pages
            
        Raises:
            ImportError: If PyMuPDF is not installed
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise ImportError(
                "PyMuPDF is not installed. Please install it with: pip install PyMuPDF"
            )
        
        # Open original PDF
        doc = fitz.open(stream=pdf_binary, filetype="pdf")
        new_doc = fitz.open()  # Create new empty PDF
        
        # Insert selected pages (convert 1-indexed to 0-indexed)
        for page_num in page_indexes:
            page_idx = page_num - 1
            if 0 <= page_idx < len(doc):
                new_doc.insert_pdf(doc, from_page=page_idx, to_page=page_idx)
            else:
                _logger.warning(f"Page {page_num} out of range, skipping")
        
        # Save to temp file with hfc_ai_extraction prefix
        tmp_file = tempfile.NamedTemporaryFile(
            delete=False, 
            suffix='.pdf', 
            prefix='hfc_ai_extraction_category_'
        )
        new_doc.save(tmp_file.name)
        
        doc.close()
        new_doc.close()
        tmp_file.close()
        
        _logger.info(f"Created category PDF with {len(page_indexes)} pages: {tmp_file.name}")
        
        return tmp_file.name

    def _build_markdown_from_ocr(self, ocr_data):
        """
        Build complete markdown from LlamaParse OCR result
        
        Args:
            ocr_data: LlamaParse JSON result (list or dict)
            
        Returns:
            str: Complete markdown text with page separators
        """
        # Handle different OCR data structures
        pages = []
        if isinstance(ocr_data, list) and len(ocr_data) > 0:
            if isinstance(ocr_data[0], dict) and 'pages' in ocr_data[0]:
                pages = ocr_data[0].get('pages', [])
        
        markdown_parts = []
        for page in pages:
            page_md = page.get('md', '')
            if page_md:
                markdown_parts.append(page_md)
        
        full_markdown = "\n\n---\n\n".join(markdown_parts)
        
        _logger.debug(f"Built markdown from {len(pages)} pages: {len(full_markdown)} chars")
        
        return full_markdown

    def _build_category_extraction_prompt(self, category, markdown, document_type):
        """
        Build extraction prompt for specific category
        
        Args:
            category (str): Category key (metadata, substance_usage, etc.)
            markdown (str): Markdown content from LlamaParse
            document_type (str): '01' or '02'
            
        Returns:
            str: Extraction prompt for Gemini chat
        """
        # Get schema from schema_prompts
        from odoo.addons.robotia_document_extractor.prompts import schema_prompts
        
        if document_type == '01':
            schema = schema_prompts.get_form_01_schema()
        else:
            schema = schema_prompts.get_form_02_schema()
        
        if category == 'metadata':
            return f"""
NHIỆM VỤ: Trích xuất metadata từ tài liệu

CATEGORY: metadata

⚠️ **LƯU Ý QUAN TRỌNG**: Metadata được extract SAU CÙNG, do đó bạn có thể nhìn lại TOÀN BỘ LỊCH SỬ ĐỘI THOẠI để suy luận các cờ (flags).

MARKDOWN CONTENT:
{markdown}

EXTRACTION RULES:
{schema}

HƯỚNG DẪN TRÍCH XUẤT:

1. **THÔNG TIN CƠ BẢN** (organization_name, business_license, contact info):
   - Trích xuất từ markdown
   - Bảo toàn ký tự tiếng Việt

2. **CỜ HAS_TABLE (Table Presence Flags)**:
   - **XEM LẠI LỊCH SỬ CHAT**: Bạn đã được yêu cầu extract những category nào?

   **MAPPING CATEGORY → FLAG (Form 01):**
   - Nếu đã extract `substance_usage` → `has_table_1_1 = true`
   - Nếu đã extract `equipment_product` → `has_table_1_2 = true`
   - Nếu đã extract `equipment_ownership` → `has_table_1_3 = true`
   - Nếu đã extract `collection_recycling` → `has_table_1_4 = true`

   **MAPPING CATEGORY → FLAG (Form 02):**
   - Nếu đã extract `quota_usage` → `has_table_2_1 = true`
   - Nếu đã extract `equipment_product_report` → `has_table_2_2 = true`
   - Nếu đã extract `equipment_ownership_report` → `has_table_2_3 = true`
   - Nếu đã extract `collection_recycling_report` → `has_table_2_4 = true`

3. **YEAR FIELDS**:
   - `year`: Năm báo cáo (từ header như "Đăng ký năm 2024" hoặc "Báo cáo năm 2024")
   - `year_1, year_2, year_3`: **QUAN TRỌNG** - Lấy từ column headers của Bảng 1.1 (substance_usage) hoặc Bảng 2.1 (quota_usage)
     * Xem lại response của category `substance_usage` hoặc `quota_usage` trong lịch sử chat
     * Tìm 3 cột năm trong bảng đó (thường là năm hiện tại và 2 năm trước)
     * Ví dụ: năm 2024 → year_1=2022, year_2=2023, year_3=2024

4. **IS_CAPACITY_MERGED FLAGS**:
   - Xem lại dữ liệu bảng `equipment_product` hoặc `equipment_product_report` trong lịch sử:
     * Nếu có trường `capacity` (1 cột gộp) → `is_capacity_merged_table_1_2 = true`
     * Nếu có `cooling_capacity` và `power_capacity` riêng (2 cột) → `is_capacity_merged_table_1_2 = false`
   - Tương tự cho `equipment_ownership` → `is_capacity_merged_table_1_3`

5. **ACTIVITY_FIELD_CODES** (Suy luận thông minh):

   **Ưu tiên 1**: Tìm trong markdown checkbox/tick đánh dấu lĩnh vực

   **Ưu tiên 2**: Nếu không tìm thấy, SUY LUẬN từ has_table flags:

   **Form 01 Mapping:**
   - `has_table_1_1 = true` → Xem bảng substance_usage có dòng data (is_title=false) không?
     * Nếu có dòng với usage_type="production" → thêm "production" vào activity_field_codes
     * Nếu có dòng với usage_type="import" → thêm "import"
     * Nếu có dòng với usage_type="export" → thêm "export"
   - `has_table_1_2 = true` → Xem bảng equipment_product có dòng data thực không?
     * Nếu có → thêm "equipment_production" hoặc "equipment_import" tùy product_type
   - `has_table_1_3 = true` → Xem bảng equipment_ownership có dòng data thực không?
     * Nếu có → thêm "ac_ownership" hoặc "refrigeration_ownership" tùy equipment_type
   - `has_table_1_4 = true` → Xem bảng collection_recycling có dòng data thực không?
     * Nếu có → thêm "collection_recycling"

   **Nguyên tắc**: Chỉ coi là "có" nếu bảng có **ÍT NHẤT 1 DÒNG DATA** (is_title=false với giá trị thực tế)

OUTPUT: JSON object với TẤT CẢ metadata fields kể cả flags
"""
        else:
            return f"""
NHIỆM VỤ: Trích xuất bảng dữ liệu từ tài liệu

CATEGORY: {category}

MARKDOWN CONTENT:
{markdown}

EXTRACTION RULES:
{schema}

HƯỚNG DẪN:
- Trích xuất bảng {category} thành JSON array
- Mỗi dòng trong bảng là 1 object trong array
- Bảo toàn tất cả dữ liệu, không bỏ sót
- Giữ nguyên số liệu (kg, CO2e), không làm tròn
- Bảo toàn ký tự tiếng Việt

QUY TẮC XỬ LÝ DÒNG:
1. **DÒNG TIÊU ĐỀ/PHÂN LOẠI (GIỮ LẠI):**
   - Dòng có tên phân loại rõ ràng (VD: "Sản xuất chất được kiểm soát", "Nhập khẩu chất được kiểm soát")
   - Có các dòng dữ liệu con bên dưới
   - Các trường số liệu có thể là null
   - Set is_title=true

2. **DÒNG TRỐNG/PLACEHOLDER (LOẠI BỎ):**
   - Chứa "...", gạch ngang "-", ký tự placeholder
   - Tên chất/mã HS không rõ ràng hoặc không có ý nghĩa
   - Loại bỏ hoàn toàn khỏi kết quả

3. **DÒNG DỮ LIỆU TRÙNG:**
   - Có thể trùng mã chất nhưng khác lĩnh vực/năm/giao dịch
   - Trả về đầy đủ TẤT CẢ các dòng, không gộp

OUTPUT FORMAT: {{"{category}": [...]}}
"""

    def _merge_category_data(self, extracted_datas):
        """
        Merge all category extraction results into single object
        
        Args:
            extracted_datas (list): List of dicts from category extractions
            
        Returns:
            dict: Merged data
        """
        merged = {}
        
        for data in extracted_datas:
            if not data:
                continue
            
            for key, value in data.items():
                if key not in merged:
                    merged[key] = value
                elif isinstance(value, list):
                    # For arrays (tables), extend
                    if isinstance(merged[key], list):
                        merged[key].extend(value)
                    else:
                        merged[key] = value
                else:
                    # For scalars, keep first non-null value
                    if not merged[key] and value:
                        merged[key] = value
        
        _logger.info(f"Merged {len(extracted_datas)} category results into {len(merged)} fields")
        
        return merged

    def _validate_and_fix_metadata_flags(self, extracted_data, document_type):
        """
        Validate and fix metadata flags based on actual extracted data
        
        This method uses regex and data analysis instead of relying on AI inference.
        It analyzes the extracted tables to determine:
        - has_table_x_y flags (based on category presence)
        - year_1, year_2, year_3 (from table column headers)
        - is_capacity_merged flags (from table structure)
        - activity_field_codes (from title rows and data rows)
        
        Args:
            extracted_data (dict): Merged extracted data
            document_type (str): '01' or '02'
            
        Returns:
            dict: Fixed extracted data with correct flags
        """
        _logger.info("Validating and fixing metadata flags...")
        
        # Step 1: Fix has_table flags based on key presence
        if document_type == '01':
            extracted_data['has_table_1_1'] = 'substance_usage' in extracted_data and len(extracted_data.get('substance_usage', [])) > 0
            extracted_data['has_table_1_2'] = 'equipment_product' in extracted_data and len(extracted_data.get('equipment_product', [])) > 0
            extracted_data['has_table_1_3'] = 'equipment_ownership' in extracted_data and len(extracted_data.get('equipment_ownership', [])) > 0
            extracted_data['has_table_1_4'] = 'collection_recycling' in extracted_data and len(extracted_data.get('collection_recycling', [])) > 0
        else:  # '02'
            extracted_data['has_table_2_1'] = 'quota_usage' in extracted_data and len(extracted_data.get('quota_usage', [])) > 0
            extracted_data['has_table_2_2'] = 'equipment_product_report' in extracted_data and len(extracted_data.get('equipment_product_report', [])) > 0
            extracted_data['has_table_2_3'] = 'equipment_ownership_report' in extracted_data and len(extracted_data.get('equipment_ownership_report', [])) > 0
            extracted_data['has_table_2_4'] = 'collection_recycling_report' in extracted_data and len(extracted_data.get('collection_recycling_report', [])) > 0
        
        try:
            # Step 2: Extract year_1, year_2, year_3 from substance_usage or quota_usage
            self._extract_years_from_tables(extracted_data, document_type)
        except Exception as err:
            _logger.error("INFER YEAR ERROR --- %s", err)
        try:
            # Step 3: Determine is_capacity_merged flags from table structure
            self._determine_capacity_merged_flags(extracted_data, document_type)
        except Exception as err:
            _logger.error("INFER CAPACITY MERGE ERROR --- %s", err)
        
        try:
            # Step 4: Infer activity_field_codes from table data
            self._infer_activity_field_codes(extracted_data)
        except Exception as err:
            _logger.error("INFER ACTIVIY ERROR --- %s", err)
        
        _logger.info("Metadata flags validation completed")
        
        return extracted_data
    
    def _extract_years_from_tables(self, extracted_data, document_type):
        """
        Extract year_1, year_2, year_3 from table headers

        Logic: AI should extract these years directly from table column headers.
        If not extracted, fallback to current_year - 2, -1, 0
        """
        # Check if AI already extracted years from headers
        if extracted_data.get('year_1') and extracted_data.get('year_2') and extracted_data.get('year_3'):
            _logger.info(f"Years already extracted: {extracted_data['year_1']}, {extracted_data['year_2']}, {extracted_data['year_3']}")
            return

        # Fallback: infer from current year (year - 2, year - 1, year)
        current_year = extracted_data.get('year')
        if current_year:
            extracted_data['year_1'] = current_year - 2
            extracted_data['year_2'] = current_year - 1
            extracted_data['year_3'] = current_year
            _logger.info(f"Inferred years from current year: {extracted_data['year_1']}, {extracted_data['year_2']}, {extracted_data['year_3']}")
        else:
            _logger.warning("Cannot extract or infer year_1, year_2, year_3")
    
    def _determine_capacity_merged_flags(self, extracted_data, document_type):
        """
        Determine is_capacity_merged flags by checking table structure
        
        Logic:
        - If table has 'capacity' field (1 merged column) → is_capacity_merged = True
        - If table has 'cooling_capacity' and 'power_capacity' (2 separate) → is_capacity_merged = False
        """
        if document_type == '01':
            # Check table 1.2 (equipment_product)
            equipment_product = extracted_data.get('equipment_product', [])
            if equipment_product:
                first_row = equipment_product[0]
                has_capacity = 'capacity' in first_row
                has_separate = 'cooling_capacity' in first_row or 'power_capacity' in first_row
                extracted_data['is_capacity_merged_table_1_2'] = has_capacity and not has_separate
            
            # Check table 1.3 (equipment_ownership)
            equipment_ownership = extracted_data.get('equipment_ownership', [])
            if equipment_ownership:
                first_row = equipment_ownership[0]
                has_capacity = 'capacity' in first_row
                has_separate = 'cooling_capacity' in first_row or 'power_capacity' in first_row
                extracted_data['is_capacity_merged_table_1_3'] = has_capacity and not has_separate
        
        else:  # '02'
            # Check table 2.2 (equipment_product_report)
            equipment_product_report = extracted_data.get('equipment_product_report', [])
            if equipment_product_report:
                first_row = equipment_product_report[0]
                has_capacity = 'capacity' in first_row
                has_separate = 'cooling_capacity' in first_row or 'power_capacity' in first_row
                extracted_data['is_capacity_merged_table_2_2'] = has_capacity and not has_separate
            
            # Check table 2.3 (equipment_ownership_report)
            equipment_ownership_report = extracted_data.get('equipment_ownership_report', [])
            if equipment_ownership_report:
                first_row = equipment_ownership_report[0]
                has_capacity = 'capacity' in first_row
                has_separate = 'cooling_capacity' in first_row or 'power_capacity' in first_row
                extracted_data['is_capacity_merged_table_2_3'] = has_capacity and not has_separate
    
    def _infer_activity_field_codes(self, extracted_data):
        """
        Infer activity_field_codes by checking all tables in extracted_data

        No need for document_type - just loop through all possible tables
        and use TABLE_ACTIVITY_MAPPINGS to extract codes.
        """
        activity_codes = set()
        
        # Loop through all table mappings
        for table_key, config in TABLE_ACTIVITY_MAPPINGS.items():
            table_data = extracted_data.get(table_key)
            if not table_data:
                continue
            
            # Extract codes from title-data pairs
            codes = self._extract_activity_codes_from_table(
                table_data,
                field_name=config['field_name'],
                mappings=config['keywords']
            )
            activity_codes.update(codes)
        
        # Store result
        extracted_data['activity_field_codes'] = sorted(list(activity_codes)) if activity_codes else extracted_data.get('activity_field_codes', [])
        
        if activity_codes:
            _logger.info(f"Inferred activity_field_codes: {extracted_data['activity_field_codes']}")
    
    def _extract_activity_codes_from_table(self, table_data, field_name, mappings):
        """
        Extract activity codes from a table by tracking title-data relationships

        Logic:
        1. Create dict to track which titles have data after them: {title_index: {'title': text, 'has_data': False}}
        2. Loop through rows:
           - If is_title=True: Add to dict with index, set current_title_idx
           - If is_title=False: Mark current_title_idx as has_data=True
        3. After loop: Check all titles that have data, match keywords (case-insensitive + regex)

        Args:
            table_data (list): Table rows
            field_name (str): Field name to check in title rows
            mappings (dict): Keyword (regex pattern) → activity code mapping

        Returns:
            set: Activity codes found
        """
        import re

        # Track which titles have data after them
        title_data = {}  # {index: {'title': text, 'has_data': False}}
        current_title_idx = None

        for idx, row in enumerate(table_data):
            if row.get('is_title'):
                # Found a title row
                title_text = row.get(field_name) or row.get('substance_name') or row.get('product_type') or row.get('equipment_type') or row.get('activity_type') or ''
                title_data[idx] = {'title': title_text, 'has_data': False}
                current_title_idx = idx
            else:
                # Data row - mark current title as having data
                if current_title_idx is not None:
                    title_data[current_title_idx]['has_data'] = True

        # Extract codes from titles that have data
        codes = set()
        for info in title_data.values():
            if info['has_data']:
                title_lower = info['title'].lower()
                for keyword, code in mappings.items():
                    # Match using both methods for maximum flexibility:
                    # 1. Case-insensitive substring match
                    # 2. Regex match with IGNORECASE (escape keyword to handle special chars)
                    if keyword.lower() in title_lower or re.search(keyword, info['title'], re.IGNORECASE):
                        codes.add(code)

        return codes
    
    def _has_valid_data_rows(self, table_data):
        """
        Check if table has at least one valid data row (not title, not empty)
        
        Args:
            table_data (list): Table rows
            
        Returns:
            bool: True if has valid data rows
        """
        for row in table_data:
            if not row.get('is_title'):
                # Check if row has any meaningful data (not all null)
                has_data = any(
                    v is not None and v != '' and v != 0
                    for k, v in row.items()
                    if k not in ['is_title', 'sequence']
                )
                if has_data:
                    return True
        return False


    @api.model
    def _get_vietnamese_provinces_list(self):
        """
        Get Vietnamese provinces/cities list from database

        Returns:
            str: Formatted list of province codes and names
        """
        states = self.env['res.country.state'].search([
            ('country_id.code', '=', 'VN')
        ], order='code')

        provinces = [f"{state.code}: {state.name}" for state in states]
        return "\n".join(provinces)

    def _initialize_default_prompts(self):
        """
        Initialize default extraction prompts in system parameters
        Called during module installation via XML data file
        """
        params = self.env['ir.config_parameter'].sudo()

        # Set Form 01 default prompt if not exists
        if not params.get_param('robotia_document_extractor.extraction_prompt_form_01'):
            params.set_param(
                'robotia_document_extractor.extraction_prompt_form_01',
                self._get_default_prompt_form_01()
            )

        # Set Form 02 default prompt if not exists
        if not params.get_param('robotia_document_extractor.extraction_prompt_form_02'):
            params.set_param(
                'robotia_document_extractor.extraction_prompt_form_02',
                self._get_default_prompt_form_02()
            )

    def extract_pdf(self, pdf_binary, document_type, log_id=None):
        """
        Extract structured data from PDF using configurable extraction strategy

        Available Strategies (configured in Settings):
        - ai_native: 100% AI (Gemini processes PDF directly)
        - text_extract: Text Extraction + AI (PyMuPDF extracts text, then AI structures)

        Args:
            pdf_binary (bytes): Binary PDF data
            document_type (str): '01' for Registration, '02' for Report
            log_id (int, optional): Extraction log ID for saving OCR data

        Returns:
            dict: Structured data extracted from PDF

        Raises:
            ValueError: If API key not configured or extraction fails
        """
        _logger.info(f"Starting AI extracting document (Type: {document_type})")

        # Clean up stale temp files first
        self.cleanup_temp_extraction_files()

        # Get configuration
        ICP = self.env['ir.config_parameter'].sudo()
        api_key = ICP.get_param('robotia_document_extractor.gemini_api_key')
        strategy = ICP.get_param('robotia_document_extractor.extraction_strategy', default='ai_native')

        if not api_key:
            raise ValueError(
                "Gemini API key not configured. "
                "Please configure it in Settings > Document Extractor > Configuration"
            )

        # Configure Gemini
        client = genai.Client(api_key=api_key)

        _logger.info(f"Using extraction strategy: {strategy}")

        # Route to appropriate strategy
        if strategy == 'ai_native':
            # Strategy 1: 100% AI (Gemini processes PDF directly)
            return self._extract_with_ai_native(client, pdf_binary, document_type)

        elif strategy == 'text_extract':
            # Strategy 2: Text Extract + AI (PyMuPDF → AI)
            return self._extract_with_text_extract(client, pdf_binary, document_type)

        else:
            _logger.warning(f"Unknown strategy '{strategy}', falling back to ai_native")
            return self._extract_with_ai_native(client, pdf_binary, document_type)

    def _extract_with_ai_native(self, client, pdf_binary, document_type):
        """
        Strategy: 100% AI (Gemini processes PDF directly)

        Primary method with automatic fallback to 2-step if needed.
        """
        # Try direct PDF → JSON extraction
        try:
            _logger.info("=" * 70)
            _logger.info("AI NATIVE: Direct PDF → JSON extraction")
            _logger.info("=" * 70)
            extracted_data = self._extract_direct_pdf_to_json(client, pdf_binary, document_type)
            _logger.info("✓ AI Native succeeded")
            return extracted_data

        except Exception as e:
            _logger.warning("✗ Direct extraction failed")
            _logger.warning(f"Error: {type(e).__name__}: {str(e)}")

            # Check if fallback is allowed
            ICP = self.env['ir.config_parameter'].sudo()
            allow_fallback = ICP.get_param('robotia_document_extractor.gemini_allow_fallback', default='True')
            allow_fallback = allow_fallback.lower() in ('true', '1', 'yes')

            if not allow_fallback:
                _logger.error("✗ Fallback disabled - failing immediately")
                raise ValueError(f"Direct extraction failed and fallback is disabled. Error: {str(e)}")

            _logger.info("→ Fallback enabled, trying 2-step extraction...")

            # Fallback: 2-step extraction (PDF → Text → JSON) using Gemini
            try:
                _logger.info("=" * 70)
                _logger.info("FALLBACK: 2-Step extraction (Gemini PDF → Text → JSON)")
                _logger.info("=" * 70)

                extracted_text = self._extract_pdf_to_text(client, pdf_binary, document_type)
                _logger.info(f"✓ Step 1 complete - Extracted {len(extracted_text)} chars")

                extracted_data = self._convert_text_to_json(client, extracted_text, document_type)
                _logger.info("✓ Step 2 complete - JSON conversion successful")

                _logger.info("✓ Fallback succeeded")
                return extracted_data

            except Exception as e2:
                _logger.error("✗ All AI Native strategies failed")
                raise ValueError(f"AI Native extraction failed. Error: {str(e2)}")

    def _extract_with_text_extract(self, client, pdf_binary, document_type, filename):
        """
        Strategy: Text Extract + AI (PyMuPDF → Gemini)

        Extracts text using PyMuPDF, then structures with AI.
        Falls back to AI Native if PyMuPDF fails.
        """
        try:
            _logger.info("=" * 70)
            _logger.info("TEXT EXTRACT: PyMuPDF → AI structuring")
            _logger.info("=" * 70)

            # Step 1: Extract text using PyMuPDF
            _logger.info("Step 1/2: Extracting text with PyMuPDF...")
            extracted_text = self._extract_pdf_to_text_pymupdf(pdf_binary, filename)
            _logger.info(f"✓ Step 1 complete - Extracted {len(extracted_text)} chars")

            # Check if extraction produced meaningful text
            if len(extracted_text.strip()) < 100:
                _logger.warning("PyMuPDF produced too little text, falling back to AI Native")
                return self._extract_with_ai_native(client, pdf_binary, document_type, filename)

            # Step 2: Structure with AI
            _logger.info("Step 2/2: Structuring with AI...")
            extracted_data = self._convert_text_to_json(client, extracted_text, document_type)
            _logger.info("✓ Step 2 complete - JSON conversion successful")

            _logger.info("✓ Text Extract strategy succeeded")
            return extracted_data

        except Exception as e:
            _logger.warning(f"✗ Text Extract strategy failed: {str(e)}")
            _logger.info("Falling back to AI Native...")
            return self._extract_with_ai_native(client, pdf_binary, document_type, filename)

    def _extract_pdf_to_text_pymupdf(self, pdf_binary, filename):
        """
        Extract text from PDF using PyMuPDF (fast, good for digital PDFs)

        Args:
            pdf_binary (bytes): Binary PDF data
            filename (str): Original filename for logging

        Returns:
            str: Extracted text with page markers

        Raises:
            ImportError: If PyMuPDF is not installed
            Exception: If PDF extraction fails
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise ImportError(
                "PyMuPDF is not installed. Please install it with: pip install PyMuPDF"
            )

        try:
            # Open PDF from binary data
            doc = fitz.open(stream=pdf_binary, filetype="pdf")
            total_pages = len(doc)

            _logger.info(f"PyMuPDF: Processing {total_pages} pages...")

            full_text = ""

            # Extract text from each page
            for page_num in range(total_pages):
                page = doc[page_num]

                # Add page marker
                full_text += f"\n{'='*70}\n"
                full_text += f"PAGE {page_num + 1}\n"
                full_text += f"{'='*70}\n"

                # Extract text with layout preservation
                page_text = page.get_text("text")
                full_text += page_text

                _logger.debug(f"Page {page_num + 1}: Extracted {len(page_text)} characters")

            doc.close()

            _logger.info(f"PyMuPDF: Successfully extracted {len(full_text)} total characters")

            return full_text

        except Exception as e:
            _logger.error(f"PyMuPDF extraction failed: {str(e)}")
            raise

    def _extract_direct_pdf_to_json(self, client, pdf_binary, document_type):
        """
        Strategy 1: Direct PDF → JSON extraction (original method)

        Args:
            client: Gemini client instance
            pdf_binary (bytes): Binary PDF data
            document_type (str): '01' or '02'
            filename (str): Original filename for logging

        Returns:
            dict: Extracted and cleaned data

        Raises:
            ValueError: If extraction fails after all retries
        """
        # Build extraction prompt based on document type
        prompt = self._build_extraction_prompt(document_type)

        _logger.info(f"Calling Gemini API for extraction (PDF size: {len(pdf_binary)} bytes)")

        # Upload PDF file to Gemini
        # Note: Gemini requires file upload for large documents

        # Get max retries from config (default: 3)
        GEMINI_MAX_RETRIES = int(
            self.env['ir.config_parameter'].sudo().get_param(
                'robotia_document_extractor.gemini_max_retries',
                default='3'
            )
        )

        tmp_file_path = None
        uploaded_file = None

        try:
            tmp_file_path = self.make_temp_file(pdf_binary)

            _logger.info(f"Created temp file: {tmp_file_path}")

            # Upload file to Gemini
            uploaded_file = self.upload_file_to_gemini(client, tmp_file_path)

            # Build mega prompt context (substances list + mapping rules)
            mega_context = self._build_mega_prompt_context()

            # Generate content with retry logic for incomplete responses
            extracted_text = None
            last_error = None

            for retry_attempt in range(GEMINI_MAX_RETRIES):
                try:
                    _logger.info(f"Gemini API call attempt {retry_attempt + 1}/{GEMINI_MAX_RETRIES}")

                    # Generate content with mega context + uploaded file + prompt
                    response = self.generate_content(client, mega_context + [uploaded_file, prompt])

                    # Get response text
                    extracted_text = response.text

                    # Check finish_reason to detect truncation
                    finish_reason = None
                    if hasattr(response, 'candidates') and response.candidates:
                        candidate = response.candidates[0]
                        finish_reason = candidate.finish_reason if hasattr(candidate, 'finish_reason') else None

                        # Log finish reason for debugging
                        _logger.info(f"Gemini finish_reason: {finish_reason}")

                        # Check if response was cut off due to token limit
                        if finish_reason and str(finish_reason) in ['MAX_TOKENS', 'LENGTH']:
                            _logger.warning(
                                f"Response was truncated due to {finish_reason}. "
                                f"Response length: {len(extracted_text)} chars. "
                                f"This attempt will likely fail validation."
                            )

                    _logger.info(f"Gemini API response received (length: {len(extracted_text)} chars)")

                    # Validate that response is complete (can be parsed as JSON)
                    # This will throw JSONDecodeError if incomplete
                    try:
                        self._parse_json_response(extracted_text)
                        _logger.info(f"Response validation successful on attempt {retry_attempt + 1}")
                        break  # Success - exit retry loop
                    except json.JSONDecodeError:
                        # Re-raise to be caught by outer except block
                        raise

                except json.JSONDecodeError as e:
                    last_error = e
                    _logger.warning(f"Attempt {retry_attempt + 1} returned incomplete JSON: {str(e)}")
                    if retry_attempt < GEMINI_MAX_RETRIES - 1:
                        _logger.info(f"Retrying immediately...")
                    else:
                        # Last attempt failed - will be caught below
                        _logger.error("All retry attempts failed - response still incomplete")
                except Exception as e:
                    last_error = e
                    _logger.warning(f"Attempt {retry_attempt + 1} failed: {type(e).__name__}: {str(e)}")
                    if retry_attempt < GEMINI_MAX_RETRIES - 1:
                        _logger.info(f"Retrying immediately...")
                    else:
                        raise

            # Check if we got a valid response after all retries
            if not extracted_text:
                raise ValueError(f"Failed to get complete response after {GEMINI_MAX_RETRIES} attempts: {last_error}")

        except Exception as e:
            _logger.exception(f"Extraction failed during Gemini API call")
            raise ValueError(f"Extraction failed: {type(e).__name__}: {str(e)}")

        finally:
            # ALWAYS cleanup temporary file
            if tmp_file_path and os.path.exists(tmp_file_path):
                try:
                    os.unlink(tmp_file_path)
                    _logger.info(f"Cleaned up temp file: {tmp_file_path}")
                except Exception as e:
                    _logger.warning(f"Failed to cleanup temp file {tmp_file_path}: {e}")

            # ALWAYS cleanup Gemini uploaded file
            if uploaded_file:
                try:
                    client.files.delete(name=uploaded_file.name)
                    _logger.info(f"Deleted Gemini file: {uploaded_file.name}")
                except Exception as e:
                    _logger.warning(f"Failed to delete Gemini file: {e}")

        # Parse JSON from response using helper method
        try:
            extracted_data = self._parse_json_response(extracted_text)
            _logger.info("Successfully parsed JSON response")

        except json.JSONDecodeError as e:
            _logger.error(f"Failed to parse JSON: {e}\nResponse preview: {extracted_text[:500]}...")
            _logger.error(f"Response tail (last 500 chars): ...{extracted_text[-500:]}")
            raise ValueError(
                f"Failed to parse AI response as JSON. "
                f"Response may be incomplete (length: {len(extracted_text)} chars). "
                f"Error: {e}"
            )

        # Validate and clean extracted data
        cleaned_data = self._clean_extracted_data(extracted_data, document_type)

        return cleaned_data

    def _build_mega_prompt_context(self):
        """
        Build mega prompt context with all controlled substances from database

        Returns a list of types.Part.from_text objects that serve as system context for AI extraction.
        This context includes:
        - List of all controlled substances with names, codes, and GWP values
        - Standardization rules for substance name mapping
        - Examples of common format variations

        Returns:
            list: List containing types.Part.from_text with mega prompt context
                  Can be extended with additional context prompts in the future
        """
        # Query all active controlled substances from database
        substances = self.env['controlled.substance'].search([
            ('active', '=', True)
        ], order='code')

        # Query all active activity fields from database
        activity_fields = self.env['activity.field'].search([
            ('active', '=', True)
        ], order='sequence')

        # Get Vietnamese provinces/cities list
        provinces_list = self._get_vietnamese_provinces_list()

        # Build context prompts using new prompt functions
        substance_prompt = context_prompts.get_substance_mapping_prompt(substances)
        activity_prompt = context_prompts.get_activity_fields_prompt(activity_fields)
        province_prompt = context_prompts.get_province_lookup_prompt(provinces_list)

        # Return as list of types.Part.from_text
        return [
            types.Part.from_text(text=substance_prompt),
            types.Part.from_text(text=activity_prompt),
            types.Part.from_text(text=province_prompt)
        ]

    def _build_extraction_prompt(self, document_type):
        """
        Build structured extraction prompt based on document type

        Reads prompt from system parameters, falls back to default if not configured

        Args:
            document_type (str): '01' or '02'

        Returns:
            str: Extraction prompt for Gemini
        """
        # Read prompt from system parameters
        param_key = f'robotia_document_extractor.extraction_prompt_form_{document_type}'
        custom_prompt = self.env['ir.config_parameter'].sudo().get_param(param_key)

        if custom_prompt:
            return custom_prompt

        # Fallback to default prompts
        if document_type == '01':
            return self._get_default_prompt_form_01()
        else:
            return self._get_default_prompt_form_02()

    def _build_text_extraction_prompt(self, document_type):
        """
        Build simple text extraction prompt (Strategy 2 - Step 1)

        This prompt asks AI to extract PDF content as plain text,
        without JSON structure. Simpler = less likely to be truncated.

        Args:
            document_type (str): '01' or '02'

        Returns:
            str: Text extraction prompt
        """
        return strategy_prompts.get_text_extract_prompt(document_type)

    def _build_text_to_json_prompt(self, document_type, extracted_text):
        """
        Build prompt to convert text to JSON (Strategy 2 - Step 2)

        This prompt takes the plain text and asks AI to structure it as JSON.

        Args:
            document_type (str): '01' or '02'
            extracted_text (str): Plain text from Step 1

        Returns:
            str: JSON conversion prompt
        """
        return strategy_prompts.get_text_to_json_prompt(document_type, extracted_text)

    def _get_default_prompt_form_01(self):
        """
        Get default extraction prompt for Form 01 (Registration)

        Returns:
            str: Default Form 01 extraction prompt
        """
        return strategy_prompts.get_ai_native_prompt('01')

    def _get_default_prompt_form_02(self):
        """
        Get default extraction prompt for Form 02 (Report)

        Returns:
            str: Default Form 02 extraction prompt
        """
        return strategy_prompts.get_ai_native_prompt('02')

    def _parse_json_response(self, response_text):
        """
        Robust JSON parser that handles multiple response formats from Gemini

        Args:
            response_text (str): Raw response text from Gemini API

        Returns:
            dict: Parsed JSON data

        Raises:
            json.JSONDecodeError: If response cannot be parsed as valid JSON
        """
        if not response_text or not response_text.strip():
            raise json.JSONDecodeError("Empty response", "", 0)

        text = response_text.strip()

        # Strategy 1: Try parsing as-is (when response_mime_type='application/json')
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass  # Try other strategies

        # Strategy 2: Extract from markdown code block ```json ... ```
        if '```json' in text:
            try:
                json_start = text.find('```json') + 7
                json_end = text.find('```', json_start)
                if json_end == -1:
                    # Closing ``` not found - response is incomplete
                    raise json.JSONDecodeError(
                        "Incomplete markdown JSON block - missing closing ```",
                        text,
                        json_start
                    )
                json_str = text[json_start:json_end].strip()
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass  # Try next strategy

        # Strategy 3: Extract from generic code block ``` ... ```
        if '```' in text:
            try:
                json_start = text.find('```') + 3
                # Skip language identifier if present (e.g., ```javascript)
                newline_pos = text.find('\n', json_start)
                if newline_pos != -1 and newline_pos - json_start < 20:
                    json_start = newline_pos + 1

                json_end = text.find('```', json_start)
                if json_end == -1:
                    # Closing ``` not found - response is incomplete
                    raise json.JSONDecodeError(
                        "Incomplete markdown code block - missing closing ```",
                        text,
                        json_start
                    )
                json_str = text[json_start:json_end].strip()
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass  # Try next strategy

        # Strategy 4: Find JSON object boundaries { ... }
        if '{' in text and '}' in text:
            try:
                json_start = text.find('{')
                json_end = text.rfind('}') + 1
                json_str = text[json_start:json_end]
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass

        # All strategies failed - raise detailed error
        preview_len = min(200, len(text))
        raise json.JSONDecodeError(
            f"Could not parse response as JSON. Tried multiple strategies. "
            f"Response preview: {text[:preview_len]}...",
            text,
            0
        )

    def _extract_pdf_to_text(self, client, pdf_binary, document_type):
        """
        Strategy 2 - Step 1: Extract PDF content to plain text

        This is a simpler extraction that focuses on getting raw text data
        without worrying about JSON structure. Less likely to be truncated.

        Args:
            client: Gemini client instance
            pdf_binary (bytes): Binary PDF data
            document_type (str): '01' or '02'

        Returns:
            str: Plain text extracted from PDF

        Raises:
            ValueError: If extraction fails
        """

        # Build simple text extraction prompt
        prompt = self._build_text_extraction_prompt(document_type)

        tmp_file_path = None
        uploaded_file = None

        try:
            # Create temporary file
            tmp_file_path = self.make_temp_file(pdf_binary) 
            _logger.info(f"Created temp file for text extraction: {tmp_file_path}")
            # Upload file to Gemini
            uploaded_file = self.upload_file_to_gemini(client, tmp_file_path)
            # Build mega prompt context
            mega_context = self._build_mega_prompt_context()

            # Generate text content with mega context (using higher token limit for text)
            response = self.generate_content(client, mega_context + [uploaded_file, prompt])

            extracted_text = response.text.strip()
            _logger.info(f"Text extraction successful (length: {len(extracted_text)} chars)")

            return extracted_text

        except Exception as e:
            _logger.exception(f"Text extraction failed")
            raise ValueError(f"Text extraction failed: {type(e).__name__}: {str(e)}")

        finally:
            # Cleanup temporary file
            if tmp_file_path and os.path.exists(tmp_file_path):
                try:
                    os.unlink(tmp_file_path)
                    _logger.info(f"Cleaned up temp file: {tmp_file_path}")
                except Exception as e:
                    _logger.warning(f"Failed to cleanup temp file: {e}")

            # Cleanup Gemini uploaded file
            if uploaded_file:
                try:
                    client.files.delete(name=uploaded_file.name)
                    _logger.info(f"Deleted Gemini file: {uploaded_file.name}")
                except Exception as e:
                    _logger.warning(f"Failed to delete Gemini file: {e}")

    def _convert_text_to_json(self, client, extracted_text, document_type):
        """
        Strategy 2 - Step 2: Convert plain text to structured JSON

        Takes the plain text from Step 1 and converts it to structured JSON.
        This is lighter weight than direct PDF→JSON extraction.

        Args:
            client: Gemini client instance
            extracted_text (str): Plain text from Step 1
            document_type (str): '01' or '02'

        Returns:
            dict: Structured data

        Raises:
            ValueError: If conversion fails
        """
        # Build JSON conversion prompt
        prompt = self._build_text_to_json_prompt(document_type, extracted_text)

        # Get Gemini model and generation parameters from config
        ICP = self.env['ir.config_parameter'].sudo()

        # Get max retries from config (default: 3)
        GEMINI_MAX_RETRIES = int(
            ICP.get_param(
                'robotia_document_extractor.gemini_max_retries',
                default='3'
            )
        )

        extracted_json = None
        last_error = None

        # Build mega prompt context
        mega_context = self._build_mega_prompt_context()

        for retry_attempt in range(GEMINI_MAX_RETRIES):
            try:
                _logger.info(f"JSON conversion attempt {retry_attempt + 1}/{GEMINI_MAX_RETRIES}")

                # Generate JSON from text with mega context (no file upload needed)
                response = self.generate_content(client, mega_context + [prompt])

                extracted_json = response.text

                # Validate JSON
                try:
                    parsed_data = self._parse_json_response(extracted_json)
                    _logger.info(f"JSON conversion successful on attempt {retry_attempt + 1}")

                    # Clean and return
                    cleaned_data = self._clean_extracted_data(parsed_data, document_type)
                    return cleaned_data

                except json.JSONDecodeError:
                    raise

            except json.JSONDecodeError as e:
                last_error = e
                _logger.warning(f"Attempt {retry_attempt + 1} returned incomplete JSON: {str(e)}")
                if retry_attempt < GEMINI_MAX_RETRIES - 1:
                    _logger.info(f"Retrying immediately...")
                else:
                    _logger.error("All JSON conversion attempts failed")

            except Exception as e:
                last_error = e
                _logger.warning(f"Attempt {retry_attempt + 1} failed: {type(e).__name__}: {str(e)}")
                if retry_attempt < GEMINI_MAX_RETRIES - 1:
                    _logger.info(f"Retrying immediately...")
                else:
                    raise

        # All retries failed
        raise ValueError(f"JSON conversion failed after {GEMINI_MAX_RETRIES} attempts: {last_error}")

    def _clean_extracted_data(self, data, document_type):
        """
        Clean and validate extracted data

        Args:
            data (dict): Raw extracted data
            document_type (str): '01' or '02'

        Returns:
            dict: Cleaned and validated data
        """
        # Ensure all expected keys exist with default values
        cleaned = {
            'year': data.get('year'),
            'year_1': data.get('year_1'),
            'year_2': data.get('year_2'),
            'year_3': data.get('year_3'),
            'organization_name': data.get('organization_name', ''),
            'business_license_number': data.get('business_license_number', ''),
            'business_license_date': data.get('business_license_date'),
            'business_license_place': data.get('business_license_place', ''),
            'legal_representative_name': data.get('legal_representative_name', ''),
            'legal_representative_position': data.get('legal_representative_position', ''),
            'contact_person_name': data.get('contact_person_name', ''),
            'contact_address': data.get('contact_address', ''),
            'contact_phone': data.get('contact_phone', ''),
            'contact_fax': data.get('contact_fax', ''),
            'contact_email': data.get('contact_email', ''),
            'contact_country_code': data.get('contact_country_code', ''),
            'contact_state_code': data.get('contact_state_code', ''),
            'activity_field_codes': data.get('activity_field_codes', []),
        }

        # Add table data based on document type
        if document_type == '01':
            cleaned.update({
                'has_table_1_1': data.get('has_table_1_1', False),
                'has_table_1_2': data.get('has_table_1_2', False),
                'has_table_1_3': data.get('has_table_1_3', False),
                'has_table_1_4': data.get('has_table_1_4', False),
                'is_capacity_merged_table_1_2': data.get('is_capacity_merged_table_1_2', True),
                'is_capacity_merged_table_1_3': data.get('is_capacity_merged_table_1_3', True),
                'substance_usage': data.get('substance_usage', []),
                'equipment_product': data.get('equipment_product', []),
                'equipment_ownership': data.get('equipment_ownership', []),
                'collection_recycling': data.get('collection_recycling', []),
            })
        else:  # '02'
            cleaned.update({
                'has_table_2_1': data.get('has_table_2_1', False),
                'has_table_2_2': data.get('has_table_2_2', False),
                'has_table_2_3': data.get('has_table_2_3', False),
                'has_table_2_4': data.get('has_table_2_4', False),
                'is_capacity_merged_table_2_2': data.get('is_capacity_merged_table_2_2', True),
                'is_capacity_merged_table_2_3': data.get('is_capacity_merged_table_2_3', True),
                'quota_usage': data.get('quota_usage', []),
                'equipment_product_report': data.get('equipment_product_report', []),
                'equipment_ownership_report': data.get('equipment_ownership_report', []),
                'collection_recycling_report': data.get('collection_recycling_report', []),
            })

        _logger.info(f"Data cleaned successfully (Type: {document_type})")
        return cleaned
