# -*- coding: utf-8 -*-

import json
import base64
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class GoogleDriveConfigWizard(models.TransientModel):
    _name = 'google.drive.config.wizard'
    _description = 'Google Drive Configuration Wizard'

    service_account_file = fields.Binary(
        string='Service Account JSON File',
        required=True,
        help='Upload the JSON key file downloaded from Google Cloud Console'
    )

    service_account_filename = fields.Char(
        string='Filename'
    )

    form01_folder_id = fields.Char(
        string='Form 01 Folder ID',
        help='Google Drive folder ID for Form 01 Registration documents'
    )

    form02_folder_id = fields.Char(
        string='Form 02 Folder ID',
        help='Google Drive folder ID for Form 02 Report documents'
    )

    processed_folder_id = fields.Char(
        string='Processed Folder ID',
        help='Folder to move processed files after extraction'
    )

    @api.model
    def default_get(self, fields_list):
        """Load current folder IDs if exist"""
        res = super().default_get(fields_list)
        ICP = self.env['ir.config_parameter'].sudo()

        if 'form01_folder_id' in fields_list:
            res['form01_folder_id'] = ICP.get_param('google_drive_form01_folder_id', '')
        if 'form02_folder_id' in fields_list:
            res['form02_folder_id'] = ICP.get_param('google_drive_form02_folder_id', '')
        if 'processed_folder_id' in fields_list:
            res['processed_folder_id'] = ICP.get_param('google_drive_processed_folder_id', '')

        return res

    def action_configure(self):
        """Save the service account JSON to system parameters"""
        self.ensure_one()

        if not self.service_account_file:
            raise UserError(_('Please upload a service account JSON file.'))

        try:
            # Decode the uploaded file
            json_content = base64.b64decode(self.service_account_file).decode('utf-8')

            # Validate JSON format
            credentials = json.loads(json_content)

            # Validate required fields
            required_fields = ['type', 'project_id', 'private_key_id', 'private_key', 'client_email']
            missing_fields = [f for f in required_fields if f not in credentials]

            if missing_fields:
                raise UserError(_('Invalid service account file. Missing fields: %s') % ', '.join(missing_fields))

            if credentials.get('type') != 'service_account':
                raise UserError(_('Invalid service account file. Expected type "service_account", got "%s"') % credentials.get('type'))

            # Save to system parameters
            ICP = self.env['ir.config_parameter'].sudo()
            ICP.set_param('google_drive_service_account_json', json_content)
            ICP.set_param('google_drive_form01_folder_id', self.form01_folder_id or '')
            ICP.set_param('google_drive_form02_folder_id', self.form02_folder_id or '')
            ICP.set_param('google_drive_processed_folder_id', self.processed_folder_id or '')

            service_account_email = credentials.get('client_email')
            _logger.info("Google Drive service account configured: %s", service_account_email)

            # Show success notification and close wizard
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Configuration Saved'),
                    'message': _('Service account configured successfully!\n\nService Account: %s\n\nYou can now test the connection in Settings.') % service_account_email,
                    'type': 'success',
                    'sticky': False,
                    'next': {'type': 'ir.actions.act_window_close'}
                }
            }

        except json.JSONDecodeError as e:
            raise UserError(_('Invalid JSON file format: %s') % str(e))
        except Exception as e:
            _logger.error("Error configuring Google Drive: %s", e)
            raise UserError(_('Failed to configure Google Drive: %s') % str(e))

    def action_test_connection(self):
        """Test connection after configuration"""
        # First save the configuration
        self.action_configure()

        # Then test the connection
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
                        'next': {'type': 'ir.actions.act_window_close'}
                    }
                }
            else:
                raise UserError(_('Connection Failed:\n\n%s') % result['message'])

        except Exception as e:
            raise UserError(_('Connection Test Failed:\n\n%s') % str(e))

    def action_clear_config(self):
        """Clear the stored configuration"""
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('google_drive_service_account_json', '')
        ICP.set_param('google_drive_form01_folder_id', '')
        ICP.set_param('google_drive_form02_folder_id', '')
        ICP.set_param('google_drive_processed_folder_id', '')

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Configuration Cleared'),
                'message': _('Google Drive configuration has been removed.'),
                'type': 'info',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'}
            }
        }
