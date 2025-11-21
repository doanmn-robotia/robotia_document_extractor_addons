# -*- coding: utf-8 -*-

import json
from odoo import api, models, fields, _
from odoo.exceptions import UserError


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
        default='gemini-2.5-pro',
        help='Gemini model to use for extraction. '
             'Options: gemini-3-pro-preview, gemini-2.5-pro, gemini-1.5-pro, gemini-1.5-flash, etc. '
             'See Google AI documentation for available models.'
    )
    # ===== Google Drive Integration Settings =====
    google_drive_enabled = fields.Boolean(
        string='Enable Google Drive Integration',
        config_parameter='google_drive_enabled',
        default=False,
        help='Enable or disable Google Drive integration for document extraction'
    )

    google_drive_service_account_json = fields.Char(
        string='Service Account JSON (Hidden)',
        config_parameter='google_drive_service_account_json',
        help='Internal field - Service account JSON stored in config parameter'
    )

    google_drive_configured = fields.Boolean(
        string='Drive Configured',
        compute='_compute_google_drive_configured',
        help='Whether Google Drive service account is configured'
    )

    google_drive_service_account_email = fields.Char(
        string='Service Account Email',
        compute='_compute_google_drive_service_account_email',
        help='Service account email (read-only, extracted from uploaded JSON)'
    )

    @api.depends('google_drive_service_account_json')
    def _compute_google_drive_configured(self):
        """Check if Google Drive is configured"""
        for record in self:
            record.google_drive_configured = bool(record.google_drive_service_account_json)

    @api.depends('google_drive_service_account_json')
    def _compute_google_drive_service_account_email(self):
        """Get service account email from stored JSON"""
        for record in self:
            if record.google_drive_service_account_json:
                try:
                    credentials = json.loads(record.google_drive_service_account_json)
                    record.google_drive_service_account_email = credentials.get('client_email', 'N/A')
                except:
                    record.google_drive_service_account_email = 'Invalid configuration'
            else:
                record.google_drive_service_account_email = 'Not configured'


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

    def action_open_google_drive_config_wizard(self):
        """Open Google Drive configuration wizard"""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Configure Google Drive'),
            'res_model': 'google.drive.config.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }

    def action_test_google_drive_connection(self):
        """Test Google Drive connection with configured credentials"""
        ICP = self.env['ir.config_parameter'].sudo()
        service_account_json = ICP.get_param('google_drive_service_account_json', '')

        # Validate that credentials are configured
        if not service_account_json:
            raise UserError(_('Please configure the Service Account first using "Configure Service Account" button.'))

        # Test connection using the Google Drive service
        try:
            drive_service = self.env['google.drive.service']
            result = drive_service.test_connection()

            if result['success']:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Connection Successful'),
                        'message': result['message'],
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                raise UserError(_('Connection Failed:\n\n%s') % result['message'])

        except UserError:
            raise
        except Exception as e:
            raise UserError(_('Connection Test Failed:\n\n%s') % str(e))
