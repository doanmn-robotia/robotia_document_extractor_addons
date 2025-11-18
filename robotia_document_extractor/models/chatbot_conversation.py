# -*- coding: utf-8 -*-

from odoo import models, fields, api

class ChatbotConversation(models.Model):
    """
    Chatbot conversation - tracks chat history per user
    """
    _name = 'chatbot.conversation'
    _description = 'Chatbot Conversation'
    _order = 'create_date desc'

    user_id = fields.Many2one(
        'res.users',
        string='User',
        required=True,
        default=lambda self: self.env.user,
        ondelete='cascade',
        index=True
    )

    message_ids = fields.One2many(
        'chatbot.message',
        'conversation_id',
        string='Messages'
    )

    last_message_date = fields.Datetime(
        string='Last Message',
        compute='_compute_last_message_date',
        store=True
    )

    message_count = fields.Integer(
        string='Message Count',
        compute='_compute_message_count',
        store=True
    )

    title = fields.Char(
        string='Title',
        compute='_compute_title',
        store=True
    )

    @api.depends('message_ids.create_date')
    def _compute_last_message_date(self):
        for record in self:
            if record.message_ids:
                record.last_message_date = max(record.message_ids.mapped('create_date'))
            else:
                record.last_message_date = False

    @api.depends('message_ids')
    def _compute_message_count(self):
        for record in self:
            record.message_count = len(record.message_ids)

    @api.depends('message_ids')
    def _compute_title(self):
        for record in self:
            if record.message_ids:
                first_user_msg = record.message_ids.filtered(lambda m: m.role == 'user')
                if first_user_msg:
                    # Use first 50 chars of first user message
                    record.title = first_user_msg[0].content[:50] + ('...' if len(first_user_msg[0].content) > 50 else '')
                else:
                    record.title = 'New Conversation'
            else:
                record.title = 'New Conversation'
