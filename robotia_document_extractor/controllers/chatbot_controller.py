# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

class ChatbotController(http.Controller):
    """
    Chatbot RPC endpoints
    """

    @http.route('/chatbot/message', type='json', auth='user')
    def send_message(self, message, conversation_id=None):
        """
        Send message to chatbot and get response

        Args:
            message (str): User message
            conversation_id (int): Optional conversation ID

        Returns:
            dict: {
                'conversation_id': int,
                'message': str,
                'action': dict or None,
                'suggestions': list
            }
        """
        try:
            # Get or create conversation
            if not conversation_id:
                conversation = request.env['chatbot.conversation'].create({
                    'user_id': request.env.user.id
                })
                conversation_id = conversation.id
            else:
                conversation = request.env['chatbot.conversation'].browse(conversation_id)
                if not conversation.exists() or conversation.user_id.id != request.env.user.id:
                    # Invalid conversation, create new
                    conversation = request.env['chatbot.conversation'].create({
                        'user_id': request.env.user.id
                    })
                    conversation_id = conversation.id

            # Save user message
            request.env['chatbot.message'].create({
                'conversation_id': conversation_id,
                'role': 'user',
                'content': message
            })

            # Get AI response
            chatbot_service = request.env['chatbot.service']
            response = chatbot_service.get_response(message, conversation_id)

            # Save assistant message
            request.env['chatbot.message'].create({
                'conversation_id': conversation_id,
                'role': 'assistant',
                'content': response['message'],
                'action_type': response.get('action', {}).get('type') if response.get('action') else None,
                'action_data': response.get('action')
            })

            return {
                'conversation_id': conversation_id,
                'message': response['message'],
                'action': response.get('action'),
                'suggestions': response.get('suggestions', [])
            }

        except Exception as e:
            _logger.error(f"Chatbot error: {str(e)}", exc_info=True)
            return {
                'conversation_id': conversation_id if conversation_id else None,
                'message': 'Xin lỗi, đã có lỗi xảy ra. Vui lòng thử lại.',
                'action': None,
                'suggestions': ['Thử lại', 'Trang chủ']
            }

    @http.route('/chatbot/conversation/history', type='json', auth='user')
    def get_conversation_history(self, conversation_id):
        """Get conversation history"""
        try:
            conversation = request.env['chatbot.conversation'].browse(conversation_id)

            if not conversation.exists() or conversation.user_id.id != request.env.user.id:
                return {'error': 'Conversation not found'}

            messages = []
            for msg in conversation.message_ids:
                messages.append({
                    'id': msg.id,
                    'role': msg.role,
                    'content': msg.content,
                    'timestamp': msg.create_date.isoformat(),
                    'action': msg.action_data
                })

            return {
                'conversation_id': conversation_id,
                'messages': messages
            }

        except Exception as e:
            _logger.error(f"Error getting conversation history: {str(e)}")
            return {'error': str(e)}
