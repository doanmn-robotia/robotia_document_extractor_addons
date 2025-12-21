from odoo import models, api, _
from odoo.modules.registry import Registry
from google import genai
import logging
from odoo import models
from google import genai
from llama_cloud_services import LlamaParse
import math
import json

_logger = logging.getLogger(__name__)


class ExtractionService(models.AbstractModel):
    _inherit = "document.extraction.service"

    def extract_pdf(self, pdf_binary, document_type, log_id=None,
                    job_id=None, resume_from_step=None):
        """
        Extract structured data from PDF using LlamaIndex OCR + Gemini AI

        This method implements the 'llama_extract' strategy which combines:
        1. LlamaParse OCR to extract markdown with layout preservation
        2. Document splitting by categories (metadata, tables)
        3. Gemini AI to structure markdown into JSON per category

        Args:
            job_id (int, optional): extraction.job ID for step-based checkpointing
            resume_from_step (str, optional): Step key to resume from (e.g., 'llama_ocr', 'ai_batch_processing')

        Workflow:
        - Clean up stale temp files (inherited from base class)
        - Upload PDF to Gemini and extract category mapping
        - Parse each category with LlamaParse to get markdown
        - Use Gemini chat to convert markdown → structured JSON
        - Merge all category data into final result

        Args:
            pdf_binary (bytes): Binary PDF data
            document_type (str): '01' for Registration Form, '02' for Report Form
            log_id (record, optional): document.extraction.log record for OCR logging

        Returns:
            dict: Structured extraction data matching document schema

        Raises:
            ValueError: If API keys not configured or extraction fails
        """

        ICP = self.env["ir.config_parameter"].sudo()
        api_key = ICP.get_param("robotia_document_extractor.gemini_api_key")
        strategy = ICP.get_param(
            "robotia_document_extractor.extraction_strategy", default="ai_native"
        )
        if strategy == "llama_split":
            client = genai.Client(api_key=api_key)
            return self._extract_with_llama_extract(
                client, pdf_binary, document_type, log_id,
                job_id=job_id, resume_from_step=resume_from_step
            )

        return super().extract_pdf(pdf_binary, document_type, log_id,
                                   job_id=job_id, resume_from_step=resume_from_step)

    def get_category_by_document_type(self, document_type):

        table1_key = ''
        table2_key = ''
        table3_key = ''
        table4_key = ''

        table1_description = ''
        table2_description = ''
        table3_description = ''
        table4_description = ''

        if document_type == "01":
            table1_key = 'substance_usage'
            table2_key = 'equipment_product'
            table3_key = 'equipment_ownership'
            table4_key = 'collection_recycling'

            table1_description = 'Bảng 1.1 - Sử dụng chất kiểm soát (Sản xuất, Nhập khẩu, Xuất khẩu). Chứa tên chất, khối lượng (kg), CO2e cho 3 năm.'
            table2_description = 'Bảng 1.2 - Sản xuất/Nhập khẩu thiết bị, sản phẩm. Chứa loại sản phẩm, mã HS, công suất, số lượng, chất sử dụng.'
            table3_description = 'Bảng 1.3 - Sở hữu/Sử dụng thiết bị điều hòa, làm lạnh. Chứa loại thiết bị, năm đưa vào sử dụng, công suất, tần suất nạp.'
            table4_description = 'Bảng 1.4 - Thu gom, Tái sử dụng, Tái chế, Chuyển đổi, Tiêu hủy. Chứa loại hoạt động, tên chất, khối lượng (kg, CO2e).'
        else:
            table1_key = 'quota_usage'
            table2_key = 'equipment_product_report'
            table3_key = 'equipment_ownership_report'
            table4_key = 'collection_recycling_report'

            table1_description = 'Bảng 2.1 - Hạn ngạch sử dụng chất kiểm soát. Chứa hạn ngạch được phân bổ, điều chỉnh, tổng hạn ngạch (kg, CO2e), mã HS, tờ khai HQ.'
            table2_description = 'Bảng 2.2 - Báo cáo sản xuất/lắp ráp thiết bị. Chứa loại sản xuất, loại sản phẩm, mã HS, công suất, số lượng, chất sử dụng.'
            table3_description = 'Bảng 2.3 - Báo cáo sở hữu/sử dụng thiết bị. Chứa loại sở hữu, loại thiết bị, số lượng, công suất, tần suất nạp.'
            table4_description = 'Bảng 2.4 - Báo cáo thu gom, tái chế. Chứa chất, khối lượng thu gom, địa điểm, công nghệ tái sử dụng/tái chế/tiêu hủy.'

        return [
            {
                "name": "metadata",
                "description": "Các thông tin chung của doanh nghiệp (Tên, Mã số doanh nghiệp, Người đại diện, Địa chỉ, Lĩnh vực hoạt động). (Phần này CÓ dữ liệu, vì các trường thông tin cơ bản đã được điền đầy đủ).",
            },
            {
                "name": table1_key,
                "description": table1_description,
            },
            {
                "name": table2_key,
                "description": table2_description,
            },
            {
                "name": table3_key,
                "description": table3_description,
            },
            {
                "name": table4_key,
                "description": table4_description,
            }
        ]

    def get_llama_category_prompt(self, category):
        """
        Build LlamaParse system prompt for specific category

        Args:
            category (str): Category key (metadata, substance_usage, etc.)

        Returns:
            str: System prompt for LlamaParse OCR
        """

        if category == 'metadata':
            return """
Trích xuất MARKDOWN từ phần thông tin chung của doanh nghiệp:
- Tên tổ chức, mã số doanh nghiệp
- Người đại diện pháp luật, chức vụ
- Thông tin liên hệ (địa chỉ, điện thoại, email)
- Lĩnh vực hoạt động

Giữ nguyên định dạng bảng nếu có. Bảo toàn ký tự tiếng Việt.
"""

        elif category in ['substance_usage', 'quota_usage']:
            return """
Trích xuất MARKDOWN từ bảng sử dụng chất kiểm soát.
Bảng chứa:
- Cột tên chất (HFC, HCFC, etc.)
- Cột khối lượng (kg)
- Cột CO2 tương đương
- Cột mã HS (nếu có)

Giữ CHÍNH XÁC cấu trúc bảng. Không bỏ sót dòng nào.
Bảo toàn số liệu, không làm tròn.
"""

        elif category in ['equipment_product', 'equipment_product_report']:
            return """
Trích xuất MARKDOWN từ bảng thiết bị/sản phẩm.
Bảng chứa:
- Loại sản phẩm/thiết bị
- Mã HS
- Công suất (HP, kW)
- Số lượng
- Chất sử dụng
- Khối lượng chất trên 1 đơn vị

Giữ CHÍNH XÁC cấu trúc bảng với tất cả các cột.
"""

        elif category in ['equipment_ownership', 'equipment_ownership_report']:
            return """
Trích xuất MARKDOWN từ bảng sở hữu/sử dụng thiết bị.
Bảng chứa:
- Loại thiết bị
- Năm đưa vào sử dụng
- Công suất
- Số lượng thiết bị
- Chất sử dụng
- Tần suất nạp mới
- Lượng chất nạp mỗi lần

Giữ nguyên cấu trúc bảng. Bảo toàn tất cả dòng dữ liệu.
"""

        elif category in ['collection_recycling', 'collection_recycling_report']:
            return """
Trích xuất MARKDOWN từ bảng thu gom, tái chế.
Bảng chứa:
- Loại hoạt động (Thu gom, Tái sử dụng, Tái chế, Tiêu hủy)
- Tên chất
- Khối lượng (kg, CO2e)
- Địa điểm, công nghệ (nếu có)

Giữ cấu trúc bảng với các phần con. Không bỏ sót dữ liệu.
"""

        else:
            return "Trích xuất toàn bộ nội dung dưới dạng MARKDOWN, bảo toàn cấu trúc bảng."

    def parse_categories_with_llama(self, categories, pdf_data, log_id):
        """
        Parse each category using LlamaParse

        Args:
            categories (dict): Category mapping {category_name: [page_indexes]}
            pdf_data (bytes): Original PDF binary
            log_id: Extraction log record (optional)

        Returns:
            list: Parse results with ocr_data for each category
        """

        category_files = {}

        for category, indexes in categories.items():
            if not indexes:
                continue
            # STEP 1: indexes already contains page numbers (1-based)
            # No need to use _pdf_to_images, we work directly with PDF pages

            # STEP 2: Build PDF file from selected pages using base class method
            file_path = self._build_pdf_from_pages(pdf_data, indexes)

            # STEP 3: Get system prompt for this category
            prompt = self.get_llama_category_prompt(category)

            # STEP 4: Append to category_files
            category_files[category] = {
                "file": file_path,
                "prompt": prompt,
                "page_count": len(indexes)
            }

        parse_results = []

        for category, category_data in category_files.items():

            system_prompt = category_data.get('prompt')

            # TODO: Call llama by using 
            parser = LlamaParse(
                # See how to get your API key at https://developers.llamaindex.ai/python/cloud/general/api_key/
                api_key=self.env['ir.config_parameter'].get_param('robotia_document_extractor.llama_cloud_api_key', ''),
                system_prompt_append=system_prompt,
                # The parsing mode
                parse_mode="parse_page_with_agent",
                # The model to use
                model="openai-gpt-4-1-mini",
                # Whether to use high resolution OCR (Slow)
                high_res_ocr=True,
                # Adaptive long table. LlamaParse will try to detect long table and adapt the output
                adaptive_long_table=True,
                # Whether to try to extract outlined tables
                outlined_table_extraction=True,
                # Whether to output tables as HTML in the markdown output
                output_tables_as_HTML=True,
                # Whether to use precise bounding box extraction (experimental)
                precise_bounding_box=True,
                # Whether to merge tables across pages in markdown
                merge_tables_across_pages_in_markdown=True,
                language="vi",
                # The page separator
                page_separator="\n\n---\n\n",
            )

            parse_result = parser.get_json_result(category_data.get('file'))

            parse_results.append({
                "file": category_data.get('file'),
                "ocr_data": parse_result,
                "category": category,
                "page_count": category_data.get('page_count', 0)
            })

        return parse_results

    def indexing_pages_in_ocr_response(self, parse_results):
        """
        Index pages from LlamaParse results for logging

        Args:
            parse_results (list): List of parse results from LlamaParse

        Returns:
            list: OCR log data with page indexing
        """

        ocr_log_result = []
        page_index = 1

        for result in parse_results:
            ocr_data = result.get('ocr_data', [])

            # Handle LlamaParse response structure: [{'pages': [...]}]
            if isinstance(ocr_data, list) and len(ocr_data) > 0:
                result_obj = ocr_data[0]
                if isinstance(result_obj, dict):
                    pages = result_obj.get('pages', [])

                    for page in pages:
                        ocr_log_result.append({
                            "page": page_index,
                            "md": page.get('md', ''),
                            "items": page.get('items', []),
                            "width": page.get('width', 0),
                            "height": page.get('height', 0)
                        })
                        page_index += 1

        return ocr_log_result
        

    def _extract_with_llama_extract(self, client, pdf_binary, document_type, log_id,
                                     job_id=None, resume_from_step=None):
        """
        Extract using LlamaIndex OCR + Gemini Chat with step-based progress

        Strategy (5 steps):
        1. Upload & Validate: Upload PDF to Gemini, validate file
        2. Category Mapping: Extract category mapping (metadata, substance_usage, etc.)
        3. Llama OCR: Parse each category with LlamaParse -> markdown
        4. AI Batch Processing: Gemini Chat converts markdown -> JSON (batched per category)
        5. Merge & Validate: Merge all category JSONs, validate metadata flags

        Checkpointing:
        - Each step saves result to extraction.job JSON fields
        - On retry, reuses checkpoint data if available (no re-extraction)
        - If checkpoint missing, executes extraction logic normally

        Args:
            client: Gemini client instance
            pdf_binary (bytes): Binary PDF data
            document_type (str): '01' or '02'
            log_id: Extraction log record
            job_id (int, optional): Extraction job ID for checkpointing
            resume_from_step (str, optional): Step to resume from

        Returns:
            dict: Extracted structured data

        Raises:
            ValueError: If extraction fails
        """

        new_env = None
        uploaded_file = None
        llama_json = None

        try:
            # Create separate cursor for bus.bus notifications only
            new_cr = Registry(self.env.cr.dbname).cursor()
            new_env = api.Environment(new_cr, 1, {})

            # Get job record from MAIN env (for checkpoint loading and updates)
            # IMPORTANT: Use self.env, NOT new_env - job updates must be in main transaction
            job = self.env['extraction.job'].browse(job_id) if job_id else None

            # ===== STEP 1: UPLOAD & VALIDATE =====
            uploaded_file = self._step_upload_validate(client, pdf_binary, new_env, job, resume_from_step)

            # ===== STEP 2: CATEGORY MAPPING =====
            categories = self._step_category_mapping(client, uploaded_file, document_type, new_env, job, resume_from_step)

            # ===== STEP 3: LLAMA OCR =====
            llama_json = self._step_llama_ocr(categories, pdf_binary, log_id, new_env, job, resume_from_step)

            # ===== STEP 4: AI BATCH PROCESSING =====
            extracted_datas = self._step_ai_batch_processing(client, llama_json, document_type, new_env, job, resume_from_step)

            # ===== STEP 5: MERGE & VALIDATE =====
            extracted_data = self._step_merge_validate(extracted_datas, document_type, new_env, job)

            return extracted_data

        except Exception as error:
            _logger.error(f"Llama extraction failed at step {job.current_step if job else 'unknown'}: {str(error)}", exc_info=True)

            # Update job with error state (will be committed by main transaction)
            if job:
                try:
                    job.write({
                        'state': 'error',
                        'error_message': f"Step {job.current_step if job else 'unknown'} failed: {str(error)}"
                    })
                except:
                    pass

            # Update log if exists
            if log_id:
                try:
                    log_id.write({
                        'status': 'error',
                        'error_message': f"Llama extraction failed: {str(error)}"
                    })
                except:
                    pass

            raise ValueError(f"Llama extraction failed: {str(error)}")

        finally:
            if new_env:
                new_env.cr.close()

            # Save OCR log if available
            if log_id:
                try:
                    # Check if llama_json exists (from Step 3)
                    if llama_json:
                        ocr_log_result = self.indexing_pages_in_ocr_response(llama_json)
                        log_id.write({
                            "ocr_response_json": json.dumps(ocr_log_result, ensure_ascii=False, indent=2)
                        })
                except:
                    pass

            # Clean up uploaded file from Gemini
            if uploaded_file:
                try:
                    client.files.delete(name=uploaded_file.name)
                    _logger.info(f"Deleted Gemini file: {uploaded_file.name}")
                except Exception as e:
                    _logger.warning(f"Failed to delete Gemini file: {e}")

    def _extract_categories(self, client, uploaded_file, document_type):

        prompt = f"""
            Bạn là một công cụ ánh xạ dữ liệu chuyên nghiệp.
            Nhiệm vụ của bạn là phân tích Dữ liệu JSON đầu vào (chứa tên các mục/category) và Dữ liệu Tài liệu (chứa nội dung được phân tách theo trang), sau đó xác định chính xác các chỉ mục trang (index) tương ứng với mỗi mục.

            ---

            ### ⚠️ **ĐIỀU KIỆN TIÊN QUYẾT BẮT BUỘC VỀ DỮ LIỆU VÀ CHỈ MỤC TRANG:**

            1   **Chỉ mục Trang Lặp lại**: Một trang có thể chứa nhiều phần dữ liệu (metadata hoặc các bảng khác). Các chỉ mục trang trong MẢNG kết quả **ĐƯỢC PHÉP LẶP LẠI** giữa các mục (`category`).
            * **NHẤN MẠNH**: Hãy lấy TẤT CẢ các trang có chứa nội dung của một mục. Một mục (ví dụ: một bảng) có thể trải dài qua nhiều trang, và một trang có thể được chia sẻ bởi nhiều mục khác nhau.

            2   **Dữ liệu Bảng Chi tiết**: Chỉ đưa vào kết quả JSON các mục bảng (ví dụ: "Bảng 2.1") nếu bảng đó có chứa **DỮ LIỆU CHI TIẾT CÓ Ý NGHĨA** đã được điền (như khối lượng (kg), số lượng, số tờ khai HQ, tên chất cụ thể, v.v.).

            3   **Loại bỏ Bảng Trống**: Nếu bảng chỉ có tiêu đề, cấu trúc, hoặc các dòng mô tả hoạt động **nhưng không có các giá trị định lượng cụ thể** được điền vào các cột dữ liệu, thì bảng đó phải bị **LOẠI BỎ HOÀN TOÀN** khỏi đầu ra JSON.
            * *Ví dụ Loại bỏ*: "Bảng 2.2", "Bảng 2.3", và "Bảng 2.4" nếu KHÔNG có dữ liệu chi tiết, sẽ không được đưa vào kết quả.

            4   **Metadata**: Mục "metadata" luôn được đưa vào nếu thông tin chung của doanh nghiệp có đầy đủ.

            ---

            Đầu ra BẮT BUỘT phải là một đối tượng JSON và chỉ duy nhất đối tượng JSON đó, KHÔNG được kèm theo bất kỳ lời giải thích hay văn bản nào khác.

            Cấu trúc JSON đầu ra phải tuân thủ nghiêm ngặt theo định dạng sau:
            {{
            "[Tên mục/Category (name từ JSON đầu vào)]": [List các số nguyên là chỉ mục trang]
            }}

            Lưu ý về định dạng Giá trị (Value):
            - Giá trị phải là một MẢNG (LIST) chứa các số nguyên (integer) đại diện cho chỉ mục trang.

            Dữ liệu đầu vào JSON (Tên các mục cần tìm):
            
            {self.get_category_by_document_type(document_type)}

            Dữ liệu Tài liệu (Nội dung PDF được phân tích theo trang) sẽ được chỉ định ở file đính kèm.

            Ví dụ về đầu ra JSON duy nhất được chấp nhận, KHÔNG được giải thích gì thêm (Lưu ý: Ví dụ này sử dụng tên mục giả định để minh họa sự lặp lại của chỉ mục trang):
            {{
            "metadata": [1, 2, ..],
            "category_x": [3,...],
            "category_y": [3,4, ....]
            }}
        """


        result = self.generate_content(client, [prompt, uploaded_file])

        categories = self._parse_json_response(result.text)

        return categories

    # ========== STEP HELPER METHODS (FOR CHECKPOINTING) ==========

    def _step_upload_validate(self, client, pdf_binary, new_env, job, resume_from_step):
        """
        Step 1: Upload PDF to Gemini and validate

        Returns:
            uploaded_file: Gemini file object
        """
        # Check if resuming and checkpoint exists
        if resume_from_step and job and job.gemini_file_name:
            try:
                uploaded_file = client.files.get(name=job.gemini_file_name)
                _logger.info(f"[RESUME] Reusing Gemini file: {uploaded_file.name}")
                return uploaded_file
            except Exception as e:
                _logger.warning(f"[RESUME] Failed to fetch Gemini file, re-uploading: {e}")
                # Fall through to upload

        # Execute upload logic
        self.update_progress(new_env, 'upload_validate', _('Uploading PDF to Gemini...'), job.id if job else None)

        tmp_file_path = self.make_temp_file(pdf_binary)
        uploaded_file = self.upload_file_to_gemini(client, tmp_file_path)

        # Save checkpoint (will be committed by main transaction)
        if job:
            job.write({'gemini_file_name': uploaded_file.name})

        return uploaded_file

    def _step_category_mapping(self, client, uploaded_file, document_type, new_env, job, resume_from_step):
        """
        Step 2: Extract category mapping from Gemini

        Returns:
            categories: dict {category_name: [page_indexes]}
        """
        # Check checkpoint
        if job and job.category_mapping_json:
            try:
                categories = json.loads(job.category_mapping_json)
                _logger.info(f"[RESUME] Reusing categories: {list(categories.keys())}")
                return categories
            except Exception as e:
                _logger.warning(f"[RESUME] Failed to load categories, re-extracting: {e}")

        # Execute extraction
        self.update_progress(new_env, 'category_mapping', _('Categorizing pages...'), job.id if job else None)

        categories = self._extract_categories(client, uploaded_file, document_type)

        # Save checkpoint (will be committed by main transaction)
        if job:
            job.write({
                'category_mapping_json': json.dumps(categories, ensure_ascii=False),
                'last_completed_step': 'category_mapping',
                'current_step': 'category_mapping',
                'progress': 20,
                'progress_message': _('Đã hoàn thành phân loại trang')
            })

        return categories

    def _step_llama_ocr(self, categories, pdf_binary, log_id, new_env, job, resume_from_step):
        """
        Step 3: Llama OCR extraction

        Returns:
            llama_json: list of category OCR results
        """
        # Check checkpoint
        if job and job.llama_ocr_json:
            try:
                llama_json = json.loads(job.llama_ocr_json)
                _logger.info(f"[RESUME] Reusing Llama OCR ({len(llama_json)} categories)")
                return llama_json
            except Exception as e:
                _logger.warning(f"[RESUME] Failed to load Llama OCR, re-extracting: {e}")

        # Execute OCR
        self.update_progress(new_env, 'llama_ocr', _('Extracting markdown with Llama...'), job.id if job else None)

        llama_json = self.parse_categories_with_llama(categories, pdf_binary, log_id)

        # Save checkpoint (will be committed by main transaction)
        if job:
            job.write({
                'llama_ocr_json': json.dumps(llama_json, ensure_ascii=False),
                'last_completed_step': 'llama_ocr',
                'current_step': 'llama_ocr',
                'progress': 40,
                'progress_message': _('Đã hoàn thành OCR với Llama')
            })

        return llama_json

    def _step_ai_batch_processing(self, client, llama_json, document_type, new_env, job, resume_from_step):
        """
        Step 4: AI batch processing (Gemini Chat)

        Returns:
            extracted_datas: list of category extraction results
        """
        # Check checkpoint
        if job and job.ai_extracted_json:
            try:
                extracted_datas = json.loads(job.ai_extracted_json)
                _logger.info(f"[RESUME] Reusing AI extracted data ({len(extracted_datas)} categories)")
                return extracted_datas
            except Exception as e:
                _logger.warning(f"[RESUME] Failed to load AI data, re-extracting: {e}")

        # Execute AI processing
        self.update_progress(new_env, 'ai_batch_processing', _('Processing with AI...'), job.id if job else None)

        # Create chat session
        system_instruction = """
Bạn là trợ lý AI chuyên trích xuất dữ liệu có cấu trúc từ tài liệu tiếng Việt.

NHIỆM VỤ:
- Người dùng sẽ cung cấp: MARKDOWN content, CATEGORY key (Loại dữ liệu cần trích xuất), EXTRACTION RULES (Các quy tắc trích xuất cụ thể) và JSON SCHEMA (Cấu trúc đầu ra mong muốn).
- Bạn phải trích xuất dữ liệu từ markdown theo đúng category, rules, và schema.
- Trả về **JSON HỢP LỆ** (Valid JSON) làm đầu ra duy nhất.

⚠️ **QUAN TRỌNG - GHI NHỚ CONTEXT:**
- Bạn sẽ được yêu cầu extract NHIỀU CATEGORY khác nhau theo thứ tự (substance_usage, equipment_product, equipment_ownership, collection_recycling, v.v.)
- **CATEGORY "metadata" SẼ LUÔN ĐƯỢC EXTRACT SAU CÙNG**
- Khi extract metadata, bạn CẦN NHÌN LẠI TOÀN BỘ LỊCH SỬ ĐỐI THOẠI để:
  1. Xác định đã extract những category nào → set flags has_table_x_y = true
  2. Lấy thông tin year_1, year_2, year_3 từ response của category substance_usage hoặc quota_usage
  3. Xác định is_capacity_merged từ structure của bảng equipment
  4. Suy luận activity_field_codes từ dữ liệu các bảng đã extract

QUY TẮC:
1. **Chỉ trả về JSON**, không giải thích, không thêm bất kỳ văn bản nào khác.
2. Chỉ trích xuất dữ liệu thuộc category được yêu cầu.
3. **Bảo toàn ký tự tiếng Việt** và dấu câu chính xác.
4. **Giữ nguyên số liệu**, không làm tròn, và giữ nguyên định dạng số (bao gồm cả dấu thập phân nếu có).
5. **XỬ LÝ BẢNG PHÂN TÁN (Table Splitting):** Các bảng dữ liệu bị ngắt quãng giữa các dòng hoặc bị cắt ngang bởi các trang phải được nối (join) lại một cách thông minh:
    * Khi đang trích xuất cho Bảng X, nếu gặp các dòng bị ngắt quãng hoặc không xác định có cấu trúc số cột tương tự, hãy gộp chúng vào Bảng X.
    * Việc trích xuất cho Bảng X sẽ dừng lại ngay khi gặp tiêu đề của Bảng tiếp theo (Bảng Y), hoặc gặp một tiêu đề/đoạn văn bản không có cấu trúc cột tương tự.
6. **XỬ LÝ DỮ LIỆU THIẾU (Missing Data):** Nếu một trường (key) trong JSON SCHEMA được yêu cầu nhưng không tìm thấy dữ liệu tương ứng trong tài liệu, hãy gán giá trị **null** cho trường đó.
7. **PHÂN BIỆT DÒNG TIÊU ĐỀ vs DÒNG TRỐNG:**
    ** Dòng tổng cộng, dòng không xác định...
    * **DÒNG TIÊU ĐỀ/PHÂN LOẠI** (GIỮ LẠI): Là dòng có tên phân loại rõ ràng (ví dụ: "Sản xuất chất được kiểm soát", "Nhập khẩu chất được kiểm soát", "Xuất khẩu chất được kiểm soát") và có các dòng dữ liệu con bên dưới. Dòng này có thể có hầu hết trường số liệu là null nhưng phải được giữ lại để phân nhóm dữ liệu. Set trường is_title=true cho dòng này.
    * **DÒNG TRỐNG/PLACEHOLDER** (LOẠI BỎ): Là dòng không có thông tin có ý nghĩa: chứa "...", gạch ngang "-", ký tự placeholder, hoặc trường tên chất/mã HS không rõ ràng, không phải là dòng TỔNG CỘNG. Dòng này phải bị loại bỏ hoàn toàn khỏi kết quả JSON.
8. **XỬ LÝ DỮ LIỆU TRÙNG MÃ CHẤT:** Dữ liệu có thể bị trùng về mã chất giữa các bảng nhưng chúng là những dòng khác nhau (ví dụ: cùng chất nhưng khác lĩnh vực hoạt động, khác năm, khác giao dịch). Bạn phải tôn trọng dữ liệu đó và trả về đầy đủ TẤT CẢ các dòng, không được gộp hoặc loại bỏ.
"""
        chat = self.create_chat_session(client, system_instruction)

        # Build and send mega context
        mega_context_parts = self._build_mega_prompt_context()
        mega_context_text = "\n\n".join([part.text for part in mega_context_parts])
        chat.send_message(f"CONTEXT:\n{mega_context_text}\n\nĐã hiểu. Sẵn sàng trích xuất dữ liệu.")

        # Reorder: metadata last
        meta_category = None
        llama_json_normalized = []
        for category_result in llama_json:
            if category_result.get('category') == 'metadata':
                meta_category = category_result
            else:
                llama_json_normalized.append(category_result)
        if meta_category:
            llama_json_normalized.append(meta_category)

        # Process each category
        extracted_datas = []
        for idx, category_result in enumerate(llama_json_normalized):
            category = category_result.get('category')
            page_count = category_result.get('page_count')

            batch_responses = self._process_category_batches(
                chat, category_result, category, document_type, page_count
            )

            extracted_datas.append({
                category: batch_responses
            } if category != 'metadata' else batch_responses)

            # Progress update per category
            category_progress_message = _(f'Processed {idx+1}/{len(llama_json_normalized)} categories')
            self.update_progress(new_env, 'ai_batch_processing', category_progress_message, job.id if job else None)

        # Save checkpoint (will be committed by main transaction)
        if job:
            job.write({
                'ai_extracted_json': json.dumps(extracted_datas, ensure_ascii=False),
                'last_completed_step': 'ai_batch_processing',
                'current_step': 'ai_batch_processing',
                'progress': 80,
                'progress_message': _('Đã hoàn thành xử lý AI')
            })

        return extracted_datas

    def _process_category_batches(self, chat, category_result, category, document_type, page_count):
        """
        Process a single category with batch support (helper for Step 4)

        Returns:
            batch_responses: list or dict depending on category
        """
        ocr_data = category_result.get('ocr_data')

        if not ocr_data:
            _logger.warning(f"No OCR data for category {category}, skipping")
            return [] if category != 'metadata' else {}

        pages_processed = 0
        batch_responses = []
        batch_num = 0
        total_batches = math.ceil(page_count / 7) if page_count else 1

        while True:
            batch_num += 1
            page_start = pages_processed + 1
            page_end = min(pages_processed + 7, page_count)

            markdown = self._build_markdown_from_ocr(ocr_data, pages_processed)
            if not markdown:
                break
            if len(markdown.strip()) < 10:
                pages_processed += 7
                continue

            category_prompt = self._build_category_extraction_prompt(category, markdown, document_type)

            if total_batches > 1:
                batch_context = f"""
⚠️ **BATCH PROCESSING INFO**:
- This is batch {batch_num} of {total_batches} batches for category "{category}"
- You are extracting pages {page_start}-{page_end} of {page_count} total pages
"""
                category_prompt = batch_context + category_prompt

            try:
                response = chat.send_message(category_prompt)
                response_json = self._parse_json_response(response.text)

                if isinstance(response_json, list):
                    batch_responses.extend(response_json)
                elif isinstance(response_json, dict) and category == "metadata":
                    batch_responses = response_json
                    break
                elif isinstance(response_json, dict) and response_json.get(category):
                    batch_responses.extend(response_json[category])
            except Exception as e:
                _logger.error(f"Batch {batch_num} failed: {str(e)}", exc_info=True)

            pages_processed += 7
            if category == "metadata":
                break

        return batch_responses

    def _step_merge_validate(self, extracted_datas, document_type, new_env, job):
        """
        Step 5: Merge and validate

        Returns:
            extracted_data: final validated dict
        """
        self.update_progress(new_env, 'merge_validate', _('Merging and validating...'), job.id if job else None)

        extracted_data = self._merge_category_data(extracted_datas)
        extracted_data = self._validate_and_fix_metadata_flags(extracted_data, document_type)

        # Save checkpoint (will be committed by main transaction)
        if job:
            job.write({
                'final_result_json': json.dumps(extracted_data, ensure_ascii=False),
                'last_completed_step': 'merge_validate',
                'current_step': 'merge_validate',
                'progress': 95,
                'progress_message': _('Đã hoàn thành gộp và kiểm tra')
            })

        return extracted_data

