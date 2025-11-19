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

    # ===== Google Drive Integration Settings =====
    gdrive_enabled = fields.Boolean(
        string='Enable Google Drive Integration',
        config_parameter='robotia_document_extractor.gdrive_enabled',
        default=False,
        help='Enable automatic fetching of PDF files from Google Drive'
    )
    gdrive_folder_id = fields.Char(
        string='Google Drive Folder ID',
        config_parameter='robotia_document_extractor.gdrive_folder_id',
        help='Google Drive folder ID to fetch PDF files from. '
             'You can find this in the folder URL: https://drive.google.com/drive/folders/FOLDER_ID'
    )
    gdrive_credentials_json = fields.Text(
        string='Google Drive Service Account JSON',
        config_parameter='robotia_document_extractor.gdrive_credentials_json',
        help='Service Account credentials JSON from Google Cloud Console. '
             'Create a service account at https://console.cloud.google.com/iam-admin/serviceaccounts '
             'and share the Google Drive folder with the service account email.'
    )
    gdrive_cron_interval = fields.Integer(
        string='Fetch Interval (minutes)',
        config_parameter='robotia_document_extractor.gdrive_cron_interval',
        default=30,
        help='Interval in minutes between automatic fetches from Google Drive. Default: 30 minutes'
    )
    gdrive_ocr_batch_size = fields.Integer(
        string='OCR Batch Size',
        config_parameter='robotia_document_extractor.gdrive_ocr_batch_size',
        default=3,
        help='Number of documents to process in each OCR cron run. Default: 3'
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
