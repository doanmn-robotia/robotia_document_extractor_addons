# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    gemini_api_key = fields.Char(
        string='Gemini API Key',
        config_parameter='robotia_document_extractor.gemini_api_key',
        help='Enter your Google Gemini API key for document extraction'
    )

    gemini_max_output_tokens = fields.Integer(
        string='Max Output Tokens',
        config_parameter='robotia_document_extractor.gemini_max_output_tokens',
        default=65536,
        help='Maximum number of tokens for Gemini API response. '
             'Increase this value if extraction fails for very long documents. '
             'Default: 65536 (Gemini 2.0 Flash maximum)'
    )

    gemini_model = fields.Char(
        string='Gemini Model',
        config_parameter='robotia_document_extractor.gemini_model',
        default='gemini-2.0-flash-exp',
        help='Gemini model to use for extraction. '
             'Options: gemini-2.0-flash-exp, gemini-1.5-pro, gemini-1.5-flash, etc. '
             'See Google AI documentation for available models.'
    )


    def action_get_prompt_form_01(self):
        """Reset Form 01 prompt to default value"""
        from . import extraction_service
        default_prompt = extraction_service.DocumentExtractionService._get_default_prompt_form_01(self.env['document.extraction.service'])
        self.env['ir.config_parameter'].sudo().set_param(
            'robotia_document_extractor.extraction_prompt_form_01',
            default_prompt
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_get_prompt_form_02(self):
        """Reset Form 02 prompt to default value"""
        from . import extraction_service
        default_prompt = extraction_service.DocumentExtractionService._get_default_prompt_form_02(self.env['document.extraction.service'])
        self.env['ir.config_parameter'].sudo().set_param(
            'robotia_document_extractor.extraction_prompt_form_02',
            default_prompt
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
