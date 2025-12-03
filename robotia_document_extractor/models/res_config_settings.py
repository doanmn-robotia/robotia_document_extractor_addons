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

    gemini_max_retries = fields.Integer(
        string='Max Retries',
        config_parameter='robotia_document_extractor.gemini_max_retries',
        default=3,
        help='Maximum number of retry attempts when Gemini API extraction fails. '
             'Retries are executed immediately without delay. '
             'Default: 3'
    )

    gemini_allow_fallback = fields.Boolean(
        string='Allow Fallback Strategy',
        config_parameter='robotia_document_extractor.gemini_allow_fallback',
        default=False,
        help='Enable fallback to 2-step extraction (PDF → Text → JSON) when direct extraction fails. '
             'If disabled, extraction will fail immediately without trying the fallback method. '
             'Default: Enabled'
    )

    gemini_model = fields.Char(
        string='Gemini Model',
        config_parameter='robotia_document_extractor.gemini_model',
        default='gemini-2.5-pro',
        help='Gemini model to use for extraction. '
             'Options: gemini-3-pro-preview, gemini-2.5-pro, gemini-1.5-pro, gemini-1.5-flash, etc. '
             'See Google AI documentation for available models.'
    )

    extract_pages_run_ocr = fields.Boolean(
        string='Run OCR for Page Extraction',
        config_parameter='robotia_document_extractor.extract_pages_run_ocr',
        default=False,
        help='If enabled, OCR will be run on the extracted pages before AI processing. '
             'Enable this if the source PDF is an image scan without text layer. '
             'Default: Disabled'
    )

    extraction_strategy = fields.Selection(
        selection=[
            ('ai_native', _('100% AI (Gemini processes PDF directly)')),
            ('text_extract', _('Text Extraction + AI (Extract text first, then AI structures)')),
            ('batch_extract', _('Batch Extraction (Process pages in batches with chat session)'))
        ],
        string=_('Extraction Strategy'),
        config_parameter='robotia_document_extractor.extraction_strategy',
        default='ai_native',
        help=_('Choose extraction method:\n'
               '• 100% AI: Gemini natively reads and understands PDF layout (recommended)\n'
               '• Text Extract + AI: Extract text first using PyMuPDF, then AI structures it\n'
               '  (useful for very large PDFs or cost optimization)\n'
               '• Batch Extraction: Convert PDF to images, process in batches with adaptive sizing\n'
               '  (recommended for very large documents 20+ pages with many tables)')
    )

    # ===== Batch Extraction Configuration =====
    batch_size_min = fields.Integer(
        string=_('Minimum Batch Size'),
        config_parameter='robotia_document_extractor.batch_size_min',
        default=3,
        help=_('Minimum pages per API call for complex documents (many table rows). '
               'Smaller batches = more accurate but more API calls. '
               'Default: 3 pages')
    )

    batch_size_max = fields.Integer(
        string=_('Maximum Batch Size'),
        config_parameter='robotia_document_extractor.batch_size_max',
        default=7,
        help=_('Maximum pages per API call for simple documents (few table rows). '
               'Larger batches = fewer API calls but may lose accuracy. '
               'Default: 7 pages')
    )

    batch_image_dpi = fields.Integer(
        string=_('Image Resolution (DPI)'),
        config_parameter='robotia_document_extractor.batch_image_dpi',
        default=200,
        help=_('Resolution when converting PDF to images for batch extraction. '
               'Higher DPI = better quality but larger file sizes. '
               'Recommended: 150-300 DPI. Default: 200')
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
        default_prompt = self.env['document.extraction.service']._get_default_prompt_form_01()
        self.env['ir.config_parameter'].sudo().set_param(
            'robotia_document_extractor.extraction_prompt_form_01',
            default_prompt
        )
        return True

    def action_get_prompt_form_02(self):
        """Reset Form 02 prompt to default value"""
        default_prompt = self.env['document.extraction.service']._get_default_prompt_form_02()
        self.env['ir.config_parameter'].sudo().set_param(
            'robotia_document_extractor.extraction_prompt_form_02',
            default_prompt
        )
        return True

    def action_get_batch_prompt_form_01(self):
        """Reset Batch Form 01 prompt to default value"""
        default_prompt = self.env['document.extraction.service']._get_default_batch_prompt_form_01()
        self.env['ir.config_parameter'].sudo().set_param(
            'robotia_document_extractor.batch_prompt_form_01',
            default_prompt
        )
        return True

    def action_get_batch_prompt_form_02(self):
        """Reset Batch Form 02 prompt to default value"""
        default_prompt = self.env['document.extraction.service']._get_default_batch_prompt_form_02()
        self.env['ir.config_parameter'].sudo().set_param(
            'robotia_document_extractor.batch_prompt_form_02',
            default_prompt
        )
        return True

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
