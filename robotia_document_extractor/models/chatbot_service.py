# -*- coding: utf-8 -*-

from odoo import models, api
import json
import logging

try:
    from google import genai
    from google.genai import types
except ImportError:
    raise ValueError("Google Generative AI library not installed.")

_logger = logging.getLogger(__name__)

class ChatbotService(models.AbstractModel):
    """
    AI-powered chatbot service using Google Gemini Chat API
    """
    _name = 'chatbot.service'
    _description = 'Chatbot AI Service'

    def get_response(self, user_message, conversation_id=None):
        """
        Get AI response for user message using Gemini Chat API

        Args:
            user_message (str): User's message
            conversation_id (int): Optional conversation ID for context

        Returns:
            dict: {
                'message': str,           # AI response text
                'action': dict or None,   # Optional action to execute
                'suggestions': list       # Quick reply suggestions
            }
        """
        _logger.info(f"Processing chatbot message: {user_message[:50]}...")

        # 1. Get conversation history
        history = self._get_conversation_history(conversation_id)

        # 2. Build context from database (RAG)
        rag_context = self._build_rag_context(user_message)

        # 3. Build system prompt
        system_instruction = self._build_system_instruction(rag_context)

        # 4. Call Gemini Chat API
        ai_response = self._call_gemini_chat(system_instruction, history, user_message)

        # 5. Parse response and extract actions
        parsed_response = self._parse_response(ai_response)

        return parsed_response

    def _get_conversation_history(self, conversation_id):
        """
        Get conversation history in Gemini Chat format

        Returns:
            list: List of Content objects for Gemini Chat API
        """
        if not conversation_id:
            return []

        conversation = self.env['chatbot.conversation'].browse(conversation_id)
        if not conversation.exists():
            return []

        # Get last 20 messages for context (Gemini can handle it well)
        messages = conversation.message_ids[-20:]

        history = []
        for msg in messages:
            # Convert to Gemini Chat Content format
            role = 'user' if msg.role == 'user' else 'model'
            history.append(
                types.Content(
                    role=role,
                    parts=[types.Part(text=msg.content)]
                )
            )

        return history

    def _build_rag_context(self, user_message):
        """
        Build context from database using RAG approach
        Query relevant data based on user message
        """
        context_parts = []
        message_lower = user_message.lower()

        # 1. Search controlled substances if mentioned
        if any(keyword in message_lower for keyword in ['chất', 'substance', 'hfc', 'cfc', 'gwp', 'r-', 'r32', 'r410']):
            substances = self.env['controlled.substance'].search([], limit=15, order='name')
            if substances:
                substance_info = ["DANH SÁCH CHẤT KIỂM SOÁT:"]
                for s in substances:
                    substance_info.append(f"  • {s.name} ({s.formula}): GWP = {s.gwp_value}, Type = {s.substance_type}")
                context_parts.append("\n".join(substance_info))

        # 2. Get recent documents if asked
        if any(keyword in message_lower for keyword in ['gần đây', 'recent', 'mới nhất', 'latest', 'lịch sử', 'history']):
            docs = self.env['document.extraction'].search([], limit=10, order='create_date desc')
            if docs:
                doc_info = ["TÀI LIỆU GẦN ĐÂY:"]
                for d in docs:
                    org_name = d.organization_id.name if d.organization_id else 'N/A'
                    doc_info.append(f"  • {d.document_type_display} - {org_name} - Năm {d.year} - Ngày tạo: {d.create_date.strftime('%d/%m/%Y')}")
                context_parts.append("\n".join(doc_info))

        # 3. Get statistics if asked
        if any(keyword in message_lower for keyword in ['thống kê', 'statistics', 'tổng', 'total', 'số lượng', 'count']):
            total_docs = self.env['document.extraction'].search_count([])
            total_substances = self.env['controlled.substance'].search_count([])
            total_companies = self.env['res.partner'].search_count([('is_company', '=', True)])

            stats = [
                "THỐNG KÊ HỆ THỐNG:",
                f"  • Tổng số tài liệu: {total_docs}",
                f"  • Tổng số chất kiểm soát: {total_substances}",
                f"  • Tổng số công ty: {total_companies}"
            ]
            context_parts.append("\n".join(stats))

        # 4. Search companies if mentioned
        if any(keyword in message_lower for keyword in ['công ty', 'company', 'tổ chức', 'organization', 'doanh nghiệp']):
            companies = self.env['res.partner'].search([('is_company', '=', True)], limit=10)
            if companies:
                company_info = ["CÁC CÔNG TY/TỔ CHỨC:"]
                for c in companies:
                    company_info.append(f"  • {c.name}")
                context_parts.append("\n".join(company_info))

        # 5. Equipment types if mentioned
        if any(keyword in message_lower for keyword in ['thiết bị', 'equipment', 'máy', 'machine']):
            equipment_types = self.env['equipment.type'].search([], limit=10)
            if equipment_types:
                eq_info = ["LOẠI THIẾT BỊ:"]
                for eq in equipment_types:
                    eq_info.append(f"  • {eq.name}")
                context_parts.append("\n".join(eq_info))

        return "\n\n".join(context_parts) if context_parts else ""

    def _build_system_instruction(self, rag_context):
        """
        Build system instruction for Gemini Chat API
        This is separate from conversation history
        """

        system_instruction = """Bạn là Trợ lý AI chuyên nghiệp về hệ thống quản lý chất kiểm soát theo Nghị định thư Montreal.

🎯 NHIỆM VỤ CHÍNH:
- Hỗ trợ người dùng về Mẫu 01 (Đăng ký) và Mẫu 02 (Báo cáo)
- Giải thích về các chất kiểm soát (HFC, CFC, HCFC, Halons, v.v.)
- Hướng dẫn sử dụng hệ thống trích xuất tài liệu tự động
- Trả lời câu hỏi về thống kê, phân tích dữ liệu
- Thực hiện các hành động (mở dashboard, tìm kiếm, xem báo cáo)

📚 KIẾN THỨC NỀN TẢNG:
• Form 01 (Mẫu 01): Đăng ký sử dụng chất kiểm soát cho năm TIẾP THEO (dự kiến)
• Form 02 (Mẫu 02): Báo cáo sử dụng chất kiểm soát thực tế của năm VỪA QUA
• Hệ thống sử dụng AI (Google Gemini) để tự động trích xuất dữ liệu từ PDF
• Upload PDF → AI trích xuất → Xem trước → Chỉnh sửa nếu cần → Lưu vào database
• Các chất kiểm soát có giá trị GWP (Global Warming Potential) khác nhau

📊 CÁC DASHBOARD TRONG HỆ THỐNG:
• Main Dashboard: Tổng quan, upload tài liệu, thống kê tổng thể
• HFC Dashboard: Phân tích chuyên sâu về HFC (hydrofluorocarbons)
• Substance Dashboard: Phân tích theo từng chất kiểm soát
• Company Dashboard: Phân tích theo công ty/tổ chức
• Equipment Dashboard: Phân tích thiết bị sử dụng chất
• Recovery Dashboard: Phân tích thu gom & tái chế

⚡ ACTIONS BẠN CÓ THỂ THỰC HIỆN:
Khi người dùng yêu cầu hành động cụ thể, trả về JSON format như sau:

```json
{
  "message": "Đây là câu trả lời của bạn cho người dùng...",
  "action": {
    "type": "ACTION_TYPE",
    "params": {...}
  },
  "suggestions": ["Gợi ý 1", "Gợi ý 2", "Gợi ý 3"]
}
```

CÁC LOẠI ACTION HỢP LỆ:

1. Mở Dashboard:
{
  "type": "open_dashboard",
  "params": {"dashboard": "hfc"}  // Giá trị: main, hfc, substance, company, equipment, recovery
}

2. Xem chi tiết chất kiểm soát:
{
  "type": "view_substance",
  "params": {"substance_id": 1}
}

3. Tìm kiếm tài liệu:
{
  "type": "search_documents",
  "params": {
    "domain": [["year", "=", 2024]],  // Odoo domain format
    "context": {}
  }
}

4. Upload form:
{
  "type": "upload_form",
  "params": {"form_type": "01"}  // 01 hoặc 02
}

💡 NGUYÊN TẮC TRẢ LỜI:
✓ Ngắn gọn, dễ hiểu, thân thiện, chuyên nghiệp
✓ Sử dụng tiếng Việt tự nhiên, dễ đọc
✓ Khi không chắc chắn, hỏi lại người dùng để làm rõ
✓ Đề xuất action phù hợp khi người dùng có ý định rõ ràng
✓ Luôn cung cấp 2-3 suggestions (gợi ý nhanh) cho câu hỏi tiếp theo
✓ Dùng bullet points, emoji tiết chế để dễ đọc
✓ Nếu câu hỏi mơ hồ, đưa ra các options để user chọn

⚠️ QUAN TRỌNG:
- Chỉ trả về JSON khi người dùng yêu cầu HÀNH ĐỘNG CỤ THỂ (mở trang, tìm kiếm, xem...)
- Với câu hỏi thông thường, chỉ cần trả lời text bình thường, KHÔNG cần JSON
- Dựa vào DỮ LIỆU TỪ DATABASE bên dưới để trả lời chính xác
"""

        # Append RAG context if available
        if rag_context:
            system_instruction += f"\n\n📦 DỮ LIỆU TỪ DATABASE (sử dụng để trả lời câu hỏi):\n{rag_context}"

        return system_instruction

    def _call_gemini_chat(self, system_instruction, history, user_message):
        """
        Call Gemini Chat API with conversation history

        Args:
            system_instruction (str): System prompt
            history (list): List of Content objects
            user_message (str): Current user message

        Returns:
            str: AI response text
        """

        # Get API key
        api_key = self.env['ir.config_parameter'].sudo().get_param('robotia_document_extractor.gemini_api_key')
        if not api_key:
            raise ValueError(
                "Gemini API key chưa được cấu hình. "
                "Vui lòng cấu hình tại: Settings > Document Extractor > Configuration"
            )

        # Initialize Gemini client
        client = genai.Client(api_key=api_key)

        try:
            # Create chat with history and system instruction
            chat = client.chats.create(
                model='gemini-2.0-flash-exp',
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.7,  # Balance between creativity and consistency
                    max_output_tokens=2000,
                    top_p=0.95,
                ),
                history=history  # Previous conversation messages
            )

            # Send current message
            response = chat.send_message(user_message)

            return response.text

        except Exception as e:
            _logger.error(f"Gemini Chat API error: {str(e)}", exc_info=True)

            # User-friendly error messages
            if 'API_KEY_INVALID' in str(e):
                raise ValueError("API key không hợp lệ. Vui lòng kiểm tra lại cấu hình.")
            elif 'RATE_LIMIT' in str(e):
                raise ValueError("Đã vượt quá giới hạn API. Vui lòng thử lại sau ít phút.")
            elif 'SAFETY' in str(e):
                raise ValueError("Nội dung vi phạm chính sách an toàn của Gemini.")
            else:
                raise ValueError(f"Không thể kết nối với AI: {str(e)}")

    def _parse_response(self, ai_response):
        """
        Parse AI response and extract action if present

        Returns:
            dict: {message, action, suggestions}
        """

        # Try to parse JSON response (when AI returns structured data with action)
        try:
            # Check if response contains JSON in markdown code block
            if '```json' in ai_response:
                # Extract JSON from ```json ... ``` block
                start = ai_response.find('```json') + 7
                end = ai_response.find('```', start)
                json_str = ai_response[start:end].strip()
                parsed = json.loads(json_str)

                return {
                    'message': parsed.get('message', ''),
                    'action': parsed.get('action'),
                    'suggestions': parsed.get('suggestions', self._generate_default_suggestions(ai_response))
                }

            # Check if entire response is JSON
            elif ai_response.strip().startswith('{') and ai_response.strip().endswith('}'):
                parsed = json.loads(ai_response.strip())

                return {
                    'message': parsed.get('message', ''),
                    'action': parsed.get('action'),
                    'suggestions': parsed.get('suggestions', self._generate_default_suggestions(ai_response))
                }
        except json.JSONDecodeError:
            # Not valid JSON, continue to text parsing
            pass
        except Exception as e:
            _logger.warning(f"Error parsing JSON response: {str(e)}")

        # Plain text response (most common case)
        # Generate contextual suggestions
        suggestions = self._generate_default_suggestions(ai_response)

        return {
            'message': ai_response,
            'action': None,
            'suggestions': suggestions
        }

    def _generate_default_suggestions(self, response_text):
        """
        Generate contextual suggestions based on response

        Args:
            response_text (str): AI response text

        Returns:
            list: List of suggestion strings
        """
        suggestions = []
        response_lower = response_text.lower()

        # Context-based suggestions
        if any(keyword in response_lower for keyword in ['form 01', 'mẫu 01', 'đăng ký']):
            suggestions.extend(['Upload Mẫu 01', 'Xem ví dụ Mẫu 01'])

        if any(keyword in response_lower for keyword in ['form 02', 'mẫu 02', 'báo cáo']):
            suggestions.extend(['Upload Mẫu 02', 'Xem ví dụ Mẫu 02'])

        if any(keyword in response_lower for keyword in ['dashboard', 'thống kê', 'phân tích']):
            suggestions.extend(['Xem Dashboard HFC', 'Thống kê tổng quan'])

        if any(keyword in response_lower for keyword in ['chất', 'substance', 'hfc', 'gwp']):
            suggestions.extend(['Danh sách chất kiểm soát', 'Xem giá trị GWP'])

        if any(keyword in response_lower for keyword in ['công ty', 'company', 'tổ chức']):
            suggestions.extend(['Xem các công ty', 'Phân tích theo công ty'])

        # Default suggestions if none matched
        if not suggestions:
            suggestions = [
                'Xem thống kê',
                'Tài liệu gần đây',
                'Hỗ trợ chất kiểm soát'
            ]

        # Limit to 3 suggestions
        return suggestions[:3]
