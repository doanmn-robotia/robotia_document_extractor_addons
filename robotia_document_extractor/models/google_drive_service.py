# -*- coding: utf-8 -*-

import json
import logging
import base64
import io
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Full Drive access scope
SCOPES = ['https://www.googleapis.com/auth/drive']


class GoogleDriveService(models.AbstractModel):
    _name = 'google.drive.service'
    _description = 'Google Drive Service'

    def _get_drive_service(self):
        """
        Create Google Drive service client using service account

        :return: Google Drive service object
        """
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            ICP = self.env['ir.config_parameter'].sudo()

            # Get service account JSON credentials from config
            service_account_json = ICP.get_param('google_drive_service_account_json')

            if not service_account_json:
                raise UserError(_('Google Drive service account credentials not configured. '
                                'Please go to Settings > Technical > Parameters > System Parameters '
                                'and add "google_drive_service_account_json" with your service account JSON content.'))
            

            # Parse JSON credentials
            try:
                credentials_dict = json.loads(service_account_json)
            except json.JSONDecodeError as e:
                raise UserError(_('Invalid service account JSON format: %s') % str(e))

            # Create credentials with full Drive scope
            credentials = service_account.Credentials.from_service_account_info(
                credentials_dict,
                scopes=SCOPES
            )

            # Build and return service client
            service = build('drive', 'v3', credentials=credentials)
            return service

        except ImportError as e:
            _logger.error("Required Google libraries not installed: %s", e)
            raise UserError(_('Please install required packages: pip install google-auth google-api-python-client'))
        except Exception as e:
            _logger.error("Error creating Google Drive service: %s", e)
            raise UserError(_('Failed to initialize Google Drive service: %s') % str(e))

    @api.model
    def list_files(self, folder_id=None, query=None, page_size=100, page_token=None, order_by='modifiedTime desc'):
        """
        List files in Google Drive folder

        :param folder_id: Folder ID to list files from (None for all Drive)
        :param query: Additional query string
        :param page_size: Number of files per page
        :param page_token: Page token for pagination
        :param order_by: Sort order (default: newest first)
        :return: Dictionary with files list, nextPageToken, and total count
        """
        try:
            service = self._get_drive_service()

            # Build query
            query_parts = []
            if folder_id:
                query_parts.append(f"'{folder_id}' in parents")
            if query:
                query_parts.append(query)
            query_parts.append("trashed = false")

            final_query = ' and '.join(query_parts)

            # Execute list request
            kwargs = {
                'q': final_query,
                'pageSize': min(page_size, 1000),
                'orderBy': order_by,
                'fields': 'nextPageToken, files(id, name, mimeType, size, createdTime, modifiedTime, webViewLink, thumbnailLink, parents, iconLink, owners)'
            }

            if page_token:
                kwargs['pageToken'] = page_token

            result = service.files().list(**kwargs).execute()

            files = result.get('files', [])
            _logger.info("Listed %d files from Google Drive (folder: %s)", len(files), folder_id or 'root')

            return {
                'files': files,
                'count': len(files),
                'nextPageToken': result.get('nextPageToken'),
                'hasMore': bool(result.get('nextPageToken'))
            }

        except Exception as e:
            _logger.error("Error listing files (folder: %s): %s", folder_id, e)
            raise UserError(_('Failed to list files: %s') % str(e))

    @api.model
    def get_file_metadata(self, file_id):
        """
        Get file metadata from Google Drive

        :param file_id: Google Drive file ID
        :return: File metadata dict
        """
        try:
            service = self._get_drive_service()

            result = service.files().get(
                fileId=file_id,
                fields='id, name, mimeType, size, createdTime, modifiedTime, webViewLink, thumbnailLink, parents'
            ).execute()

            return result

        except Exception as e:
            _logger.error("Error getting file metadata %s: %s", file_id, e)
            raise UserError(_('Failed to get file metadata: %s') % str(e))

    @api.model
    def download_file(self, file_id):
        """
        Download file content from Google Drive

        :param file_id: Google Drive file ID
        :return: Binary file content
        """
        try:
            from googleapiclient.http import MediaIoBaseDownload

            service = self._get_drive_service()

            # Request file content
            request = service.files().get_media(fileId=file_id)
            file_stream = io.BytesIO()
            downloader = MediaIoBaseDownload(file_stream, request)

            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    _logger.info("Download progress: %d%%", int(status.progress() * 100))

            file_stream.seek(0)
            return file_stream.read()

        except Exception as e:
            _logger.error("Error downloading file %s: %s", file_id, e)
            raise UserError(_('Failed to download file: %s') % str(e))

    @api.model
    def upload_file(self, file_content, file_name, mime_type, folder_id=None):
        """
        Upload file to Google Drive

        :param file_content: Binary file content
        :param file_name: File name
        :param mime_type: MIME type
        :param folder_id: Parent folder ID (optional)
        :return: Upload result dict with file metadata
        """
        try:
            from googleapiclient.http import MediaIoBaseUpload

            service = self._get_drive_service()

            # Prepare file metadata
            file_metadata = {'name': file_name}
            if folder_id:
                file_metadata['parents'] = [folder_id]

            # Prepare media content
            file_stream = io.BytesIO(file_content)
            media = MediaIoBaseUpload(file_stream, mimetype=mime_type, resumable=True)

            # Upload file
            result = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name, mimeType, size, webViewLink'
            ).execute()

            _logger.info("Uploaded file %s (ID: %s)", file_name, result.get('id'))
            return result

        except Exception as e:
            _logger.error("Error uploading file %s: %s", file_name, e)
            raise UserError(_('Failed to upload file: %s') % str(e))

    @api.model
    def delete_file(self, file_id):
        """
        Delete file from Google Drive

        :param file_id: Google Drive file ID
        :return: True if successful
        """
        try:
            service = self._get_drive_service()
            service.files().delete(fileId=file_id).execute()
            _logger.info("Deleted file %s", file_id)
            return True

        except Exception as e:
            _logger.error("Error deleting file %s: %s", file_id, e)
            raise UserError(_('Failed to delete file: %s') % str(e))

    @api.model
    def create_folder(self, folder_name, parent_folder_id=None):
        """
        Create a folder in Google Drive

        :param folder_name: Name of the folder
        :param parent_folder_id: Parent folder ID (optional)
        :return: Created folder metadata
        """
        try:
            service = self._get_drive_service()

            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }

            if parent_folder_id:
                file_metadata['parents'] = [parent_folder_id]

            result = service.files().create(
                body=file_metadata,
                fields='id, name, webViewLink'
            ).execute()

            _logger.info("Created folder %s (ID: %s)", folder_name, result.get('id'))
            return result

        except Exception as e:
            _logger.error("Error creating folder %s: %s", folder_name, e)
            raise UserError(_('Failed to create folder: %s') % str(e))

    @api.model
    def search_files(self, search_term, folder_id=None, mime_type=None, page_size=100):
        """
        Search files in Google Drive by name

        :param search_term: Search term for file name
        :param folder_id: Optional folder to search in
        :param mime_type: Optional mime type filter (e.g., 'application/pdf')
        :param page_size: Number of results
        :return: List of matching files
        """
        try:
            service = self._get_drive_service()

            # Build query
            query_parts = []
            query_parts.append(f"name contains '{search_term}'")
            if folder_id:
                query_parts.append(f"'{folder_id}' in parents")
            if mime_type:
                query_parts.append(f"mimeType = '{mime_type}'")
            query_parts.append("trashed = false")

            final_query = ' and '.join(query_parts)

            result = service.files().list(
                q=final_query,
                pageSize=page_size,
                orderBy='modifiedTime desc',
                fields='files(id, name, mimeType, size, modifiedTime, webViewLink)'
            ).execute()

            files = result.get('files', [])
            _logger.info("Found %d files matching '%s'", len(files), search_term)

            return files

        except Exception as e:
            _logger.error("Error searching files: %s", e)
            raise UserError(_('Failed to search files: %s') % str(e))

    @api.model
    def list_folders(self, parent_folder_id=None, page_size=100):
        """
        List all folders in Google Drive

        :param parent_folder_id: Parent folder ID (None for root)
        :param page_size: Number of folders to return
        :return: List of folders
        """
        try:
            service = self._get_drive_service()

            query_parts = []
            query_parts.append("mimeType = 'application/vnd.google-apps.folder'")
            if parent_folder_id:
                query_parts.append(f"'{parent_folder_id}' in parents")
            query_parts.append("trashed = false")

            final_query = ' and '.join(query_parts)

            result = service.files().list(
                q=final_query,
                pageSize=page_size,
                orderBy='name',
                fields='files(id, name, webViewLink, modifiedTime)'
            ).execute()

            folders = result.get('files', [])
            _logger.info("Found %d folders", len(folders))

            return folders

        except Exception as e:
            _logger.error("Error listing folders: %s", e)
            raise UserError(_('Failed to list folders: %s') % str(e))

    @api.model
    def move_file(self, file_id, new_folder_id):
        """
        Move file to a different folder

        :param file_id: File ID to move
        :param new_folder_id: Destination folder ID
        :return: Updated file metadata
        """
        try:
            service = self._get_drive_service()

            # Get current parents
            file_metadata = service.files().get(
                fileId=file_id,
                fields='parents'
            ).execute()

            previous_parents = ','.join(file_metadata.get('parents', []))

            # Move to new folder
            result = service.files().update(
                fileId=file_id,
                addParents=new_folder_id,
                removeParents=previous_parents,
                fields='id, name, parents'
            ).execute()

            _logger.info("Moved file %s to folder %s", file_id, new_folder_id)
            return result

        except Exception as e:
            _logger.error("Error moving file %s: %s", file_id, e)
            raise UserError(_('Failed to move file: %s') % str(e))

    @api.model
    def copy_file(self, file_id, new_name=None, destination_folder_id=None):
        """
        Copy a file in Google Drive

        :param file_id: File ID to copy
        :param new_name: New name for the copy (optional)
        :param destination_folder_id: Destination folder ID (optional)
        :return: Copied file metadata
        """
        try:
            service = self._get_drive_service()

            body = {}
            if new_name:
                body['name'] = new_name
            if destination_folder_id:
                body['parents'] = [destination_folder_id]

            result = service.files().copy(
                fileId=file_id,
                body=body,
                fields='id, name, webViewLink'
            ).execute()

            _logger.info("Copied file %s to %s", file_id, result.get('id'))
            return result

        except Exception as e:
            _logger.error("Error copying file %s: %s", file_id, e)
            raise UserError(_('Failed to copy file: %s') % str(e))

    @api.model
    def rename_file(self, file_id, new_name):
        """
        Rename a file in Google Drive

        :param file_id: File ID to rename
        :param new_name: New name
        :return: Updated file metadata
        """
        try:
            service = self._get_drive_service()

            result = service.files().update(
                fileId=file_id,
                body={'name': new_name},
                fields='id, name, webViewLink'
            ).execute()

            _logger.info("Renamed file %s to %s", file_id, new_name)
            return result

        except Exception as e:
            _logger.error("Error renaming file %s: %s", file_id, e)
            raise UserError(_('Failed to rename file: %s') % str(e))

    @api.model
    def test_connection(self):
        """
        Test connection to Google Drive API

        :return: Dictionary with success status and message
        """
        try:
            service = self._get_drive_service()

            # Try to list files (limited to 1) to verify connection
            result = service.files().list(
                pageSize=1,
                fields='files(id, name)'
            ).execute()

            files = result.get('files', [])
            file_count_msg = f" Found {len(files)} file(s)." if files else " Drive is accessible but empty."

            return {
                'success': True,
                'message': _('Connection successful! Google Drive API is accessible.') + file_count_msg
            }

        except Exception as e:
            error_msg = str(e)
            if 'credentials' in error_msg.lower() or 'authentication' in error_msg.lower():
                error_msg = _('Authentication failed. Please check your service account credentials.')
            elif 'permission' in error_msg.lower() or '403' in error_msg:
                error_msg = _('Permission denied. Please verify the service account has Drive API enabled.')

            return {
                'success': False,
                'message': error_msg
            }

    @api.model
    def sync_folder(self, folder_id=None, limit=100):
        """
        Sync files from Google Drive folder to Odoo attachments

        :param folder_id: Folder ID (uses config if None)
        :param limit: Max files to process
        :return: Sync result dict
        """
        ICP = self.env['ir.config_parameter'].sudo()

        if not ICP.get_param('google_drive_enabled'):
            raise UserError(_('Google Drive integration is not enabled.'))

        if not folder_id:
            folder_id = ICP.get_param('google_drive_folder_id')

        if not folder_id:
            raise UserError(_('Google Drive folder ID is not configured.'))

        try:
            result = self.list_files(folder_id=folder_id, page_size=limit)
            files = result.get('files', [])

            _logger.info("Google Drive sync: Found %d files in folder %s", len(files), folder_id)

            processed_files = []
            errors = []

            for file_data in files:
                try:
                    attachment = self._process_drive_file(file_data)
                    if attachment:
                        processed_files.append({
                            'file_id': file_data.get('id'),
                            'file_name': file_data.get('name'),
                            'attachment_id': attachment.id
                        })
                except Exception as e:
                    _logger.error("Error processing file %s: %s", file_data.get('name'), e)
                    errors.append({
                        'file_id': file_data.get('id'),
                        'file_name': file_data.get('name'),
                        'error': str(e)
                    })

            return {
                'success': True,
                'processed_count': len(processed_files),
                'error_count': len(errors),
                'files': processed_files,
                'errors': errors,
                'has_more': bool(result.get('nextPageToken')),
                'next_page_token': result.get('nextPageToken')
            }

        except Exception as e:
            _logger.exception("Google Drive sync failed: %s", e)
            raise UserError(_('Google Drive sync failed: %s') % str(e))

    @api.model
    def _process_drive_file(self, file_data):
        """
        Process a single file from Google Drive

        :param file_data: File metadata
        :return: ir.attachment record or None
        """
        file_id = file_data.get('id')
        file_name = file_data.get('name')
        mime_type = file_data.get('mimeType')

        # Skip Google Docs native formats
        if mime_type.startswith('application/vnd.google-apps.'):
            _logger.info("Skipping Google native format: %s", file_name)
            return None

        # Check if already synced
        existing = self.env['ir.attachment'].search([('google_drive_id', '=', file_id)], limit=1)
        if existing:
            _logger.info("File %s already synced (attachment ID: %s)", file_name, existing.id)
            return existing

        # Download file
        file_content = self.download_file(file_id)

        # Create attachment
        attachment = self.env['ir.attachment'].create({
            'name': file_name,
            'datas': base64.b64encode(file_content),
            'mimetype': mime_type,
            'type': 'binary',
            'google_drive_id': file_id,
            'google_drive_url': file_data.get('webViewLink'),
            'description': f'Synced from Google Drive on {fields.Datetime.now()}'
        })

        _logger.info("Created attachment %s for file %s", attachment.id, file_name)
        return attachment


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    google_drive_id = fields.Char(
        string='Google Drive ID',
        copy=False,
        index=True,
        help='Google Drive file ID'
    )
    google_drive_url = fields.Char(
        string='Google Drive URL',
        copy=False,
        help='Web view link for the file in Google Drive'
    )
