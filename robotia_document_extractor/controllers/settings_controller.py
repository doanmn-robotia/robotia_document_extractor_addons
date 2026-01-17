# -*- coding: utf-8 -*-

import json
import logging
from odoo import http, _
from odoo.http import request

_logger = logging.getLogger(__name__)


class SettingsController(http.Controller):
    """Controller for Settings Dashboard - handles AI configuration CRUD"""

    @http.route('/document_extractor/settings/ai/load', type='json', auth='user')
    def load_ai_settings(self):
        """Load AI configuration settings from ir.config_parameter"""
        try:
            # Check permissions
            if not self._check_permissions():
                return {'error': _('Access Denied'), 'message': _('You do not have permission to view settings')}

            ICP = request.env['ir.config_parameter'].sudo()

            # Load all settings from ir.config_parameter
            settings = {
                # AI Engine Configuration
                'gemini_api_key': ICP.get_param('robotia_document_extractor.gemini_api_key', ''),
                'llama_cloud_api_key': ICP.get_param('robotia_document_extractor.llama_cloud_api_key', ''),
                'gemini_model': ICP.get_param('robotia_document_extractor.gemini_model', 'gemini-2.5-flash'),
                'gemini_temperature': float(ICP.get_param('robotia_document_extractor.gemini_temperature', '0.0')),
                'gemini_top_p': float(ICP.get_param('robotia_document_extractor.gemini_top_p', '0.95')),
                'gemini_top_k': int(ICP.get_param('robotia_document_extractor.gemini_top_k', '0')),
                'gemini_max_output_tokens': int(ICP.get_param('robotia_document_extractor.gemini_max_output_tokens', '65536')),
                'gemini_max_retries': int(ICP.get_param('robotia_document_extractor.gemini_max_retries', '3')),

                # Batch Extraction Configuration
                'batch_size_min': int(ICP.get_param('robotia_document_extractor.batch_size_min', '3')),
                'batch_size_max': int(ICP.get_param('robotia_document_extractor.batch_size_max', '7')),
                'batch_image_dpi': int(ICP.get_param('robotia_document_extractor.batch_image_dpi', '200')),

                # Google Drive Integration
                'google_drive_enabled': ICP.get_param('google_drive_enabled', 'False') == 'True',
                'google_drive_max_file_size_mb': int(ICP.get_param('google_drive_max_file_size_mb', '30')),
                'google_drive_form01_folder_id': ICP.get_param('google_drive_form01_folder_id', ''),
                'google_drive_form02_folder_id': ICP.get_param('google_drive_form02_folder_id', ''),
                'google_drive_processed_folder_id': ICP.get_param('google_drive_processed_folder_id', ''),
                'google_drive_auto_extraction_enabled': ICP.get_param('google_drive_auto_extraction_enabled', 'False') == 'True',
            }

            # Get service account email if configured
            service_account_json = ICP.get_param('google_drive_service_account_json', '')
            if service_account_json:
                try:
                    credentials = json.loads(service_account_json)
                    settings['google_drive_service_account_email'] = credentials.get('client_email', 'N/A')
                    settings['google_drive_configured'] = True
                except:
                    settings['google_drive_service_account_email'] = 'Invalid configuration'
                    settings['google_drive_configured'] = False
            else:
                settings['google_drive_service_account_email'] = 'Not configured'
                settings['google_drive_configured'] = False

            # Get Google Drive auto-extraction cron settings
            try:
                cron = request.env.ref('robotia_document_extractor.ir_cron_google_drive_auto_extract', raise_if_not_found=False)
                if cron:
                    settings['google_drive_cron_interval_number'] = cron.interval_number
                    settings['google_drive_cron_interval_type'] = cron.interval_type
                else:
                    settings['google_drive_cron_interval_number'] = 30
                    settings['google_drive_cron_interval_type'] = 'minutes'
            except:
                settings['google_drive_cron_interval_number'] = 30
                settings['google_drive_cron_interval_type'] = 'minutes'

            return settings

        except Exception as e:
            _logger.error("Error loading AI settings: %s", e, exc_info=True)
            return {'error': _('Load Failed'), 'message': str(e)}

    @http.route('/document_extractor/settings/ai/save', type='json', auth='user')
    def save_ai_settings(self, values):
        """Save AI configuration settings to ir.config_parameter"""
        try:
            # Check permissions
            if not self._check_permissions():
                return {'error': _('Access Denied'), 'message': _('You do not have permission to save settings')}

            ICP = request.env['ir.config_parameter'].sudo()

            # Save AI Engine Configuration
            if 'gemini_api_key' in values:
                ICP.set_param('robotia_document_extractor.gemini_api_key', values['gemini_api_key'])
            if 'llama_cloud_api_key' in values:
                ICP.set_param('robotia_document_extractor.llama_cloud_api_key', values['llama_cloud_api_key'])
            if 'gemini_model' in values:
                ICP.set_param('robotia_document_extractor.gemini_model', values['gemini_model'])
            if 'gemini_temperature' in values:
                ICP.set_param('robotia_document_extractor.gemini_temperature', str(values['gemini_temperature']))
            if 'gemini_top_p' in values:
                ICP.set_param('robotia_document_extractor.gemini_top_p', str(values['gemini_top_p']))
            if 'gemini_top_k' in values:
                ICP.set_param('robotia_document_extractor.gemini_top_k', str(values['gemini_top_k']))
            if 'gemini_max_output_tokens' in values:
                ICP.set_param('robotia_document_extractor.gemini_max_output_tokens', str(values['gemini_max_output_tokens']))
            if 'gemini_max_retries' in values:
                ICP.set_param('robotia_document_extractor.gemini_max_retries', str(values['gemini_max_retries']))

            # Save Batch Extraction Configuration
            if 'batch_size_min' in values:
                ICP.set_param('robotia_document_extractor.batch_size_min', str(values['batch_size_min']))
            if 'batch_size_max' in values:
                ICP.set_param('robotia_document_extractor.batch_size_max', str(values['batch_size_max']))
            if 'batch_image_dpi' in values:
                ICP.set_param('robotia_document_extractor.batch_image_dpi', str(values['batch_image_dpi']))

            # Save Google Drive Integration
            if 'google_drive_enabled' in values:
                ICP.set_param('google_drive_enabled', 'True' if values['google_drive_enabled'] else 'False')
            if 'google_drive_max_file_size_mb' in values:
                ICP.set_param('google_drive_max_file_size_mb', str(values['google_drive_max_file_size_mb']))
            if 'google_drive_form01_folder_id' in values:
                ICP.set_param('google_drive_form01_folder_id', values['google_drive_form01_folder_id'])
            if 'google_drive_form02_folder_id' in values:
                ICP.set_param('google_drive_form02_folder_id', values['google_drive_form02_folder_id'])
            if 'google_drive_processed_folder_id' in values:
                ICP.set_param('google_drive_processed_folder_id', values['google_drive_processed_folder_id'])
            if 'google_drive_auto_extraction_enabled' in values:
                ICP.set_param('google_drive_auto_extraction_enabled', 'True' if values['google_drive_auto_extraction_enabled'] else 'False')

            # Update Google Drive cron settings
            if 'google_drive_cron_interval_number' in values or 'google_drive_cron_interval_type' in values:
                try:
                    cron = request.env.ref('robotia_document_extractor.ir_cron_google_drive_auto_extract', raise_if_not_found=False)
                    if cron:
                        cron_values = {}
                        if 'google_drive_cron_interval_number' in values:
                            cron_values['interval_number'] = int(values['google_drive_cron_interval_number'])
                        if 'google_drive_cron_interval_type' in values:
                            cron_values['interval_type'] = values['google_drive_cron_interval_type']

                        if cron_values:
                            cron.sudo().write(cron_values)
                            _logger.info("Google Drive cron updated: %s", cron_values)
                except Exception as e:
                    _logger.warning("Failed to update cron settings: %s", e)

            _logger.info("AI settings saved successfully by user %s", request.env.user.name)
            return {'success': True, 'message': _('Settings saved successfully')}

        except Exception as e:
            _logger.error("Error saving AI settings: %s", e, exc_info=True)
            return {'error': _('Save Failed'), 'message': str(e)}

    @http.route('/document_extractor/settings/test_drive', type='json', auth='user')
    def test_google_drive_connection(self):
        """Test Google Drive connection"""
        try:
            # Check permissions
            if not self._check_permissions():
                return {'error': _('Access Denied'), 'message': _('You do not have permission to test connection')}

            ICP = request.env['ir.config_parameter'].sudo()
            service_account_json = ICP.get_param('google_drive_service_account_json', '')

            if not service_account_json:
                return {'error': _('Not Configured'), 'message': _('Please configure the Service Account first using "Upload Service Account" button.')}

            # Test connection using the Google Drive service
            drive_service = request.env['google.drive.service']
            result = drive_service.test_connection()

            if result['success']:
                return {'success': True, 'message': result['message']}
            else:
                return {'error': _('Connection Failed'), 'message': result['message']}

        except Exception as e:
            _logger.error("Error testing Google Drive connection: %s", e, exc_info=True)
            return {'error': _('Test Failed'), 'message': str(e)}

    @http.route('/document_extractor/settings/clear_drive_config', type='json', auth='user')
    def clear_google_drive_config(self):
        """Clear all Google Drive configuration"""
        try:
            # Check permissions
            if not self._check_permissions():
                return {'error': _('Access Denied'), 'message': _('You do not have permission to clear configuration')}

            ICP = request.env['ir.config_parameter'].sudo()
            ICP.set_param('google_drive_service_account_json', '')
            ICP.set_param('google_drive_form01_folder_id', '')
            ICP.set_param('google_drive_form02_folder_id', '')
            ICP.set_param('google_drive_processed_folder_id', '')

            _logger.info("Google Drive configuration cleared by user %s", request.env.user.name)
            return {'success': True, 'message': _('Google Drive configuration has been removed.')}

        except Exception as e:
            _logger.error("Error clearing Google Drive config: %s", e, exc_info=True)
            return {'error': _('Clear Failed'), 'message': str(e)}

    @http.route('/document_extractor/settings/upload_service_account', type='json', auth='user')
    def upload_service_account(self, json_content):
        """Upload and validate service account JSON"""
        try:
            # Check permissions
            if not self._check_permissions():
                return {'error': _('Access Denied'), 'message': _('You do not have permission to upload service account')}

            # Validate JSON format
            try:
                credentials = json.loads(json_content)
            except json.JSONDecodeError as e:
                return {'error': _('Invalid JSON'), 'message': _('Invalid JSON file format: %s') % str(e)}

            # Validate required fields
            required_fields = ['type', 'project_id', 'private_key_id', 'private_key', 'client_email']
            missing_fields = [f for f in required_fields if f not in credentials]

            if missing_fields:
                return {'error': _('Invalid Service Account'), 'message': _('Missing required fields: %s') % ", ".join(missing_fields)}

            if credentials.get('type') != 'service_account':
                return {'error': _('Invalid Service Account'), 'message': _('Expected type "service_account", got "%s"') % credentials.get("type")}

            # Save to system parameters
            ICP = request.env['ir.config_parameter'].sudo()
            ICP.set_param('google_drive_service_account_json', json_content)

            service_account_email = credentials.get('client_email')
            _logger.info("Google Drive service account uploaded by user %s: %s", request.env.user.name, service_account_email)

            return {
                'success': True,
                'message': _('Service account uploaded successfully'),
                'service_account_email': service_account_email
            }

        except Exception as e:
            _logger.error("Error uploading service account: %s", e, exc_info=True)
            return {'error': _('Upload Failed'), 'message': str(e)}

    def _check_permissions(self):
        """Check if user has permission to access settings"""
        user = request.env.user
        return user.has_group('base.group_system') or user.has_group('robotia_document_extractor.group_document_extractor_admin')
