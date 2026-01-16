# -*- coding: utf-8 -*-

import base64
import json
import logging
from odoo import api, models, fields, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ===== Core API Configuration =====
    gemini_api_key = fields.Char(
        string='Gemini API Key',
        config_parameter='robotia_document_extractor.gemini_api_key',
        help='Enter your Google Gemini API key for document extraction'
    )

    llama_cloud_api_key = fields.Char(
        string='LlamaCloud API Key',
        config_parameter='robotia_document_extractor.llama_cloud_api_key'
    )

    # ===== Extraction Strategy =====
    extraction_strategy = fields.Selection(
        selection=[
            ('ai_native', '100% AI (Gemini processes PDF directly)'),
            ('text_extract', 'Text Extraction + AI (Extract text first, then AI structures)'),
            ('batch_extract', 'Batch Extraction (Process pages in batches with chat session)'),
            ('llama_split', 'LlamaSplit Extract (Split by category + Llama OCR + Gemini)')
        ],
        string='Extraction Strategy',
        config_parameter='robotia_document_extractor.extraction_strategy',
        default='ai_native',
        help='Choose extraction method:\n'
               '• 100% AI: Gemini natively reads and understands PDF layout (recommended)\n'
               '• Text Extract + AI: Extract text first using PyMuPDF, then AI structures it\n'
               '  (useful for very large PDFs or cost optimization)\n'
               '• Batch Extraction: Convert PDF to images, process in batches with adaptive sizing\n'
               '  (recommended for very large documents 20+ pages with many tables)\n'
               '• LlamaSplit Extract: Split document by categories, OCR with LlamaParse, then extract with Gemini chat\n'
               '  (highest accuracy, uses LlamaCloud Split API + LlamaParse + Gemini)'
    )

    # ===== Gemini Core Configuration =====
    gemini_model = fields.Char(
        string='Gemini Model',
        config_parameter='robotia_document_extractor.gemini_model',
        default='gemini-2.5-pro',
        help='Gemini model to use for extraction. '
             'Options: gemini-3-pro-preview, gemini-2.5-pro, gemini-1.5-pro, gemini-1.5-flash, etc. '
             'See Google AI documentation for available models.'
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

    # ===== Gemini Advanced Parameters =====
    gemini_temperature = fields.Float(
        string='Temperature',
        config_parameter='robotia_document_extractor.gemini_temperature',
        default=0.0,
        help='Controls randomness in Gemini output. '
             '0.0 = Fully deterministic (recommended for accuracy). '
             '0.1-0.3 = Low randomness (consistent results). '
             '0.5-1.0 = Higher creativity (NOT recommended for data extraction). '
             'Default: 0.0'
    )

    gemini_top_p = fields.Float(
        string='Top P (Nucleus Sampling)',
        config_parameter='robotia_document_extractor.gemini_top_p',
        default=0.95,
        help='Controls diversity by limiting token selection. '
             '0.95 = Consider top 95% probability mass (recommended). '
             '1.0 = Consider all tokens (maximum flexibility). '
             '0.8 or lower = May miss rare but accurate tokens. '
             'Default: 0.95'
    )

    gemini_top_k = fields.Integer(
        string='Top K',
        config_parameter='robotia_document_extractor.gemini_top_k',
        default=0,
        help='Limits vocabulary to top K tokens. '
             '0 = No limit (recommended for precision). '
             '40 = Only consider 40 most likely tokens. '
             'Set to 0 for maximum accuracy with rare/specialized terms. '
             'Default: 0 (no limit)'
    )

    # ===== Batch Extraction Configuration =====
    batch_size_min = fields.Integer(
        string='Minimum Batch Size',
        config_parameter='robotia_document_extractor.batch_size_min',
        default=3,
        help='Minimum pages per API call for complex documents (many table rows). '
               'Smaller batches = more accurate but more API calls. '
               'Default: 3 pages'
    )

    batch_size_max = fields.Integer(
        string='Maximum Batch Size',
        config_parameter='robotia_document_extractor.batch_size_max',
        default=7,
        help='Maximum pages per API call for simple documents (few table rows). '
               'Larger batches = fewer API calls but may lose accuracy. '
               'Default: 7 pages'
    )

    batch_image_dpi = fields.Integer(
        string='Image Resolution (DPI)',
        config_parameter='robotia_document_extractor.batch_image_dpi',
        default=200,
        help='Resolution when converting PDF to images for batch extraction. '
               'Higher DPI = better quality but larger file sizes. '
               'Recommended: 150-300 DPI. Default: 200'
    )

    # ===== Google Drive Integration Settings =====
    google_drive_enabled = fields.Boolean(
        string='Enable Google Drive Integration',
        config_parameter='google_drive_enabled',
        default=False,
        help='Enable or disable Google Drive integration for document extraction'
    )

    google_drive_max_file_size_mb = fields.Integer(
        string='Max File Size (MB)',
        config_parameter='google_drive_max_file_size_mb',
        default=30,
        help='Maximum PDF file size to process from Google Drive (in megabytes). '
             'Files larger than this limit will be skipped automatically. '
             'Recommended: 30MB (approximately 30-40 pages of scanned documents). '
             'Default: 30'
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

    # ===== Google Drive - Service Account File Upload =====
    google_drive_service_account_file = fields.Binary(
        string='Service Account JSON File',
        help='Upload the JSON key file from Google Cloud Console'
    )

    google_drive_service_account_filename = fields.Char(
        string='Service Account Filename'
    )

    # ===== Google Drive - Folder Configuration =====
    google_drive_form01_folder_id = fields.Char(
        string='Form 01 Folder ID',
        config_parameter='google_drive_form01_folder_id',
        help='Google Drive folder ID for Form 01 Registration documents'
    )

    google_drive_form02_folder_id = fields.Char(
        string='Form 02 Folder ID',
        config_parameter='google_drive_form02_folder_id',
        help='Google Drive folder ID for Form 02 Report documents'
    )

    google_drive_processed_folder_id = fields.Char(
        string='Processed Folder ID',
        config_parameter='google_drive_processed_folder_id',
        help='Google Drive folder where processed files will be moved'
    )

    # ===== Google Drive - Cron Control =====
    google_drive_cron_active = fields.Boolean(
        string='Cron Job Active',
        compute='_compute_google_drive_cron_active',
        inverse='_inverse_google_drive_cron_active',
        help='Enable or disable the automatic extraction cron job'
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

    @api.depends()
    def _compute_google_drive_cron_active(self):
        """Get current Google Drive cron active state"""
        for record in self:
            cron = self.env.ref(
                'robotia_document_extractor.ir_cron_google_drive_auto_extract',
                raise_if_not_found=False
            )
            record.google_drive_cron_active = cron.active if cron else False

    def _inverse_google_drive_cron_active(self):
        """Update Google Drive cron active state"""
        for record in self:
            cron = self.env.ref(
                'robotia_document_extractor.ir_cron_google_drive_auto_extract',
                raise_if_not_found=False
            )
            if cron:
                cron.sudo().write({'active': record.google_drive_cron_active})

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

    def action_upload_service_account_json(self):
        """Process uploaded service account JSON file"""
        self.ensure_one()

        if not self.google_drive_service_account_file:
            raise UserError(_('Please upload a service account JSON file.'))

        try:
            # Decode uploaded file
            json_content = base64.b64decode(self.google_drive_service_account_file).decode('utf-8')

            # Validate JSON format
            credentials = json.loads(json_content)

            # Validate required fields
            required_fields = ['type', 'project_id', 'private_key_id', 'private_key', 'client_email']
            missing_fields = [f for f in required_fields if f not in credentials]

            if missing_fields:
                raise UserError(
                    _('Invalid service account file. Missing fields: %s') % ', '.join(missing_fields)
                )

            if credentials.get('type') != 'service_account':
                raise UserError(
                    _('Invalid service account file. Expected type "service_account", got "%s"')
                    % credentials.get('type')
                )

            # Save to config parameter
            self.env['ir.config_parameter'].sudo().set_param(
                'google_drive_service_account_json',
                json_content
            )

            service_email = credentials.get('client_email')
            _logger.info("Google Drive service account uploaded: %s", service_email)

            # Clear the binary field after successful save
            self.write({
                'google_drive_service_account_file': False,
                'google_drive_service_account_filename': False
            })

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Upload Successful'),
                    'message': _('Service account configured: %s') % service_email,
                    'type': 'success',
                    'sticky': False,
                }
            }

        except json.JSONDecodeError as e:
            raise UserError(_('Invalid JSON file format: %s') % str(e))
        except Exception as e:
            _logger.error("Error uploading service account JSON: %s", e)
            raise UserError(_('Upload failed: %s') % str(e))

    def action_clear_google_drive_config(self):
        """Clear all Google Drive configuration"""
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('google_drive_service_account_json', '')
        ICP.set_param('google_drive_form01_folder_id', '')
        ICP.set_param('google_drive_form02_folder_id', '')
        ICP.set_param('google_drive_processed_folder_id', '')

        # Also clear binary field and folder IDs
        self.write({
            'google_drive_service_account_file': False,
            'google_drive_service_account_filename': False,
            'google_drive_form01_folder_id': '',
            'google_drive_form02_folder_id': '',
            'google_drive_processed_folder_id': ''
        })

        _logger.info("Google Drive configuration cleared")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Configuration Cleared'),
                'message': _('All Google Drive settings have been removed.'),
                'type': 'info',
                'sticky': False,
            }
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

    def is_doc_admin(self):
        return self.env.user.has_group('robotia_document_extractor.group_document_extractor_admin') and self.env.context.get('module') == 'robotia_document_extractor'

    def execute(self):
        if self.is_doc_admin():
            return super(ResConfigSettings, self.sudo()).execute()
        return super().execute()

    @api.model_create_single
    def create(self, vals):
        if self.is_doc_admin():
            return super(ResConfigSettings, self.sudo()).create(vals)
        return super().create(vals)

    def write(self, vals):
        if self.is_doc_admin():
            return super(ResConfigSettings, self.sudo()).write(vals)
        return super().write(vals)
