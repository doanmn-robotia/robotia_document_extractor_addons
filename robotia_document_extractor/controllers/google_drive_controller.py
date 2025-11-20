# -*- coding: utf-8 -*-

import json
import logging
from odoo import http
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


class GoogleDriveController(http.Controller):
    """Controller for Google Drive integration endpoints"""

    @http.route('/google_drive/test_connection', type='json', auth='user', methods=['POST'])
    def test_connection(self):
        """
        Test Google Drive connection

        :return: Dictionary with connection test results
        """
        try:
            drive_service = request.env['google.drive.service']
            result = drive_service.test_connection()

            return {
                'success': result['success'],
                'message': result['message']
            }

        except Exception as e:
            _logger.exception("Google Drive connection test failed")
            return {
                'success': False,
                'message': f'Connection test failed: {str(e)}'
            }

    @http.route('/google_drive/sync', type='json', auth='user', methods=['POST'])
    def sync_folder(self, folder_id=None, limit=100):
        """
        Manually trigger Google Drive folder sync

        :param folder_id: Optional folder ID (uses configured folder if not provided)
        :param limit: Maximum number of files to process
        :return: Dictionary with sync results
        """
        try:
            drive_service = request.env['google.drive.service']
            result = drive_service.sync_folder(folder_id=folder_id, limit=limit)
            return result

        except Exception as e:
            _logger.exception("Google Drive sync failed")
            return {
                'success': False,
                'error': str(e)
            }

    @http.route('/google_drive/download/<string:file_id>', type='http', auth='user', methods=['GET'])
    def download_file(self, file_id):
        """
        Download a specific file from Google Drive

        :param file_id: Google Drive file ID
        :return: File attachment or error response
        """
        try:
            drive_service = request.env['google.drive.service']
            token = drive_service._get_access_token()

            if not token:
                return request.make_response(
                    json.dumps({'success': False, 'error': 'Failed to get access token'}),
                    headers=[('Content-Type', 'application/json')]
                )

            # Get file metadata and download
            file_metadata = drive_service.get_file_metadata(file_id, token=token)
            attachment = drive_service._process_drive_file(file_metadata, token)

            if attachment:
                return request.make_response(
                    json.dumps({
                        'success': True,
                        'attachment_id': attachment.id,
                        'attachment_name': attachment.name
                    }),
                    headers=[('Content-Type', 'application/json')]
                )
            else:
                return request.make_response(
                    json.dumps({'success': False, 'error': 'Failed to download file'}),
                    headers=[('Content-Type', 'application/json')]
                )

        except Exception as e:
            _logger.exception("Failed to download file from Google Drive")
            return request.make_response(
                json.dumps({'success': False, 'error': str(e)}),
                headers=[('Content-Type', 'application/json')]
            )

    @http.route('/google_drive/list_files', type='json', auth='user', methods=['POST'])
    def list_files(self, folder_id=None, page_size=50):
        """
        List files in Google Drive folder

        :param folder_id: Optional folder ID (uses configured folder if not provided)
        :param page_size: Number of files per page
        :return: List of files with metadata
        """
        try:
            ICP = request.env['ir.config_parameter'].sudo()

            # Get folder ID from config if not provided
            if not folder_id:
                folder_id = ICP.get_param('google_drive_folder_id')

            if not folder_id:
                return {
                    'success': False,
                    'error': 'Google Drive folder ID is not configured'
                }

            drive_service = request.env['google.drive.service']
            token = drive_service._get_access_token()

            if not token:
                return {
                    'success': False,
                    'error': 'Failed to get access token'
                }

            result = drive_service.list_files(
                folder_id=folder_id,
                page_size=page_size,
                token=token
            )

            return {
                'success': True,
                'files': result.get('files', []),
                'nextPageToken': result.get('nextPageToken')
            }

        except Exception as e:
            _logger.exception("Failed to list files from Google Drive")
            return {
                'success': False,
                'error': str(e)
            }
