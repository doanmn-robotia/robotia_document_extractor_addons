# -*- coding: utf-8 -*-

from odoo import models, fields

class ChatbotMessage(models.Model):
    """
    Individual message in a chatbot conversation
    """
    _name = 'chatbot.message'
    _description = 'Chatbot Message'
    _order = 'create_date asc'

    conversation_id = fields.Many2one(
        'chatbot.conversation',
        string='Conversation',
        required=True,
        ondelete='cascade',
        index=True
    )

    role = fields.Selection([
        ('user', 'User'),
        ('assistant', 'Assistant')
    ], string='Role', required=True, index=True)

    content = fields.Text(string='Content', required=True)

    # Optional: Store action data if message triggers action
    action_type = fields.Char(string='Action Type')
    action_data = fields.Json(string='Action Data')
