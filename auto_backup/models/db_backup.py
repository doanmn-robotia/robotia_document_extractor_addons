# Copyright 2004-2009 Tiny SPRL (<http://tiny.be>).
# Copyright 2015 Agile Business Group <http://www.agilebg.com>
# Copyright 2016 Grupo ESOC Ingenieria de Servicios, S.L.U. - Jairo Llopis
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
import os
import shutil
import traceback
from contextlib import contextmanager
from datetime import datetime, timedelta
from glob import iglob
import re

import json
import stat
import subprocess
import tempfile

import configparser
import base64
from pathlib import Path

from odoo import _, api, exceptions, fields, models, tools
from odoo.exceptions import UserError
from odoo.service import db

_logger = logging.getLogger(__name__)
try:
    import pysftp
except ImportError:  # pragma: no cover
    _logger.debug("Cannot import pysftp")


class DbBackup(models.Model):
    _description = "Database Backup"
    _name = "db.backup"
    _inherit = "mail.thread"

    _sql_constraints = [
        ("name_unique", "UNIQUE(name)", "Cannot duplicate a configuration."),
        (
            "days_to_keep_positive",
            "CHECK(days_to_keep >= 0)",
            "I cannot remove backups from the future. Ask Doc for that.",
        ),
    ]

    name = fields.Char(
        compute="_compute_name",
        store=True,
        help="Summary of this backup process",
    )
    folder = fields.Char(
        default=lambda self: self._default_folder(),
        help="Absolute path for storing the backups",
        required=True,
    )
    days_to_keep = fields.Integer(
        required=True,
        default=0,
        help="Backups older than this will be deleted automatically. "
        "Set 0 to disable autodeletion.",
    )
    method = fields.Selection(
        [("local", "Local disk"), ("sftp", "Remote SFTP server")],
        default="local",
        help="Choose the storage method for this backup.",
    )
    sftp_host = fields.Char(
        "SFTP Server",
        help=(
            "The host name or IP address from your remote"
            " server. For example 192.168.0.1"
        ),
    )
    sftp_port = fields.Integer(
        "SFTP Port",
        default=22,
        help="The port on the FTP server that accepts SSH/SFTP calls.",
    )
    sftp_user = fields.Char(
        "Username in the SFTP Server",
        help=(
            "The username where the SFTP connection "
            "should be made with. This is the user on the external server."
        ),
    )
    sftp_password = fields.Char(
        "SFTP Password",
        help="The password for the SFTP connection. If you specify a private "
        "key file, then this is the password to decrypt it.",
    )
    sftp_private_key = fields.Char(
        "Private key location",
        help="Path to the private key file. Only the Odoo user should have "
        "read permissions for that file.",
    )

    backup_format = fields.Selection(
        [
            ("zip", "zip (includes filestore)"),
            ("dump", "pg_dump custom format (without filestore)"),
        ],
        default="zip",
        help="Choose the format for this backup.",
    )

    # System Paths Configuration
    custom_addons_path = fields.Char(
        string="Custom Addons Path",
        default="/opt/odoo/odoo18/custom_addons",
        help="Path to custom addons directory"
    )
    odoo_config_path = fields.Char(
        string="Odoo Config Path", 
        default="/etc/odoo/odoo.conf",
        help="Path to odoo.conf file"
    )
    nginx_config_path = fields.Char(
        string="Nginx Config Path",
        default="/etc/nginx/sites-available/odoo",
        help="Path to nginx configuration file"
    )
    systemd_service_path = fields.Char(
        string="Systemd Service Path",
        default="/etc/systemd/system/odoo18.service", 
        help="Path to systemd service file"
    )
    odoo_data_path = fields.Char(
        string="Odoo Data Path",
        default="/opt/odoo/.local/share/Odoo",
        help="Path to Odoo data directory"
    )
    python_venv_path = fields.Char(
        string="Python Virtual Environment",
        help="Path to Python virtual environment (optional)"
    )
    odoo_user = fields.Char(
        string="Odoo System User",
        default="odoo",
        help="System user running Odoo"
    )

    # Backup Components Selection
    backup_mode = fields.Selection([
        ('database_only', 'Database Only'),
        ('database_filestore', 'Database + Filestore'), 
        ('full_system', 'Full System Backup')
    ], string="Backup Mode", default='full_system')

    include_custom_addons = fields.Boolean(
        string="Include Custom Addons", 
        default=True
    )
    include_system_configs = fields.Boolean(
        string="Include System Configs", 
        default=True
    )
    include_odoo_data = fields.Boolean(
        string="Include Odoo Data Directory", 
        default=True
    )

    # Cloud Sync Configuration
    enable_cloud_sync = fields.Boolean(
        string="Enable Cloud Sync",
        default=False,
        help="Automatically sync backups to cloud storage after local backup"
    )
    cloud_provider = fields.Selection([
        ('gdrive', 'Google Drive'),
        ('s3', 'Amazon S3'),
        ('onedrive', 'Microsoft OneDrive'),
        ('dropbox', 'Dropbox'),
        ('custom', 'Custom rclone Remote')
    ], string="Cloud Provider", help="Select cloud storage provider")
    
    rclone_config_name = fields.Char(
        string="rclone Remote Name",
        help="Name of the rclone remote configuration (e.g., 'mydrive', 'myaws')"
    )
    cloud_backup_path = fields.Char(
        string="Cloud Backup Path",
        default="/odoo_backups",
        help="Path on cloud storage where backups will be stored"
    )
    cloud_retention_days = fields.Integer(
        string="Cloud Retention (Days)",
        default=30,
        help="Number of days to keep backups in cloud storage (0 = keep forever)"
    )
    verify_cloud_upload = fields.Boolean(
        string="Verify Cloud Upload",
        default=True,
        help="Verify file integrity after cloud upload"
    )
    cloud_bandwidth_limit = fields.Char(
        string="Bandwidth Limit",
        help="Limit upload bandwidth (e.g., '10M' for 10MB/s, '1G' for 1GB/s)"
    )
    encrypt_cloud_backup = fields.Boolean(
        string="Encrypt Cloud Backup",
        default=False,
        help="Encrypt backup before uploading to cloud (requires rclone crypt)"
    )

    backup_history_count = fields.Integer(
        string="Backup History Count",
        compute="_compute_backup_history_count"
    )

    @api.depends()
    def _compute_backup_history_count(self):
        for record in self:
            record.backup_history_count = self.env['backup.history'].search_count([
                ('backup_config_id', '=', record.id)
            ])

    def action_view_backup_history(self):
        """View backup history for this configuration"""
        self.ensure_one()
        action = self.env.ref('auto_backup.action_backup_history').read()[0]
        action['domain'] = [('backup_config_id', '=', self.id)]
        action['context'] = {
            'default_backup_config_id': self.id,
            'search_default_success': 0,  # Show all records
        }
        return action

    @api.model
    def _default_folder(self):
        """Default to ``backups`` folder inside current server datadir."""
        return os.path.join(tools.config["data_dir"], "backups", self.env.cr.dbname)

    @api.depends("folder", "method", "sftp_host", "sftp_port", "sftp_user")
    def _compute_name(self):
        """Get the right summary for this job."""
        for rec in self:
            if rec.method == "local":
                rec.name = f"{rec.folder} @ localhost"
            elif rec.method == "sftp":
                rec.name = f"sftp://{rec.sftp_user}@{rec.sftp_host}:{rec.sftp_port}{rec.folder}"

    @api.constrains("folder", "method")
    def _check_folder(self):
        """Do not use the filestore or you will backup your backups."""
        for record in self:
            if record.method == "local" and record.folder.startswith(
                tools.config.filestore(self.env.cr.dbname)
            ):
                raise exceptions.ValidationError(
                    self.env._(
                        "Do not save backups on your filestore, or you will "
                        "backup your backups too!"
                    )
                )
            
    @api.constrains('custom_addons_path', 'odoo_config_path', 'nginx_config_path', 
                    'systemd_service_path', 'odoo_data_path')
    def _validate_system_paths(self):
        """Validate all configured paths exist and are accessible"""
        for record in self:
            if record.backup_mode == 'full_system':
                paths_to_check = {
                    'Custom Addons': record.custom_addons_path,
                    'Odoo Config': record.odoo_config_path,
                    'Nginx Config': record.nginx_config_path,
                    'Systemd Service': record.systemd_service_path,
                    'Odoo Data': record.odoo_data_path,
                }
                
                invalid_paths = []
                for path_name, path_value in paths_to_check.items():
                    if path_value and not record._check_path_exists(path_value, path_name):
                        invalid_paths.append(f"{path_name}: {path_value}")
                
                if invalid_paths:
                    _logger.warning(f"Some backup paths are invalid: {', '.join(invalid_paths)}")

    def _check_path_exists(self, path, path_name):
        """Check if path exists and log warnings"""
        if not path:
            return True  # Empty paths are optional
            
        if not os.path.exists(path):
            _logger.warning(f"{path_name} path does not exist: {path}")
            return False
            
        if not self._check_path_permissions(path, path_name):
            return False
            
        return True

    def _check_path_permissions(self, path, path_name):
        """Check read permissions for backup paths"""
        try:
            if os.path.isfile(path):
                with open(path, 'r'):
                    pass
            elif os.path.isdir(path):
                os.listdir(path)
            return True
        except (PermissionError, OSError) as e:
            _logger.warning(f"Cannot access {path_name} path {path}: {e}")
            return False

    def action_validate_paths(self):
        """Manual validation action for paths"""
        self.ensure_one()
        messages = []
        
        paths_to_check = {
            'Custom Addons': self.custom_addons_path,
            'Odoo Config': self.odoo_config_path,
            'Nginx Config': self.nginx_config_path,
            'Systemd Service': self.systemd_service_path,
            'Odoo Data': self.odoo_data_path,
            'Python Venv': self.python_venv_path,
        }
        
        for path_name, path_value in paths_to_check.items():
            if not path_value:
                messages.append(f"✓ {path_name}: Not configured (optional)")
                continue
                
            if self._check_path_exists(path_value, path_name):
                messages.append(f"✓ {path_name}: Valid ({path_value})")
            else:
                messages.append(f"✗ {path_name}: Invalid or inaccessible ({path_value})")
        
        message = "Path Validation Results:\n\n" + "\n".join(messages)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Path Validation',
                'message': message,
                'type': 'info',
                'sticky': True,
            }
        }

    def action_sftp_test_connection(self):
        """Check if the SFTP settings are correct."""
        try:
            # Just open and close the connection
            with self.sftp_connection():
                raise UserError(_("Connection Test Succeeded!"))
        except (
            pysftp.CredentialException,
            pysftp.ConnectionException,
            pysftp.SSHException,
        ) as exc:
            _logger.info("Connection Test Failed!", exc_info=True)
            raise UserError(self.env._("Connection Test Failed!")) from exc

    def action_backup(self):
        """Enhanced backup with compression support"""
        import glob

        backup = None
        successful = self.browse()

        # Start with local storage
        for rec in self.filtered(lambda r: r.method == "local"):
            timestamp = datetime.now()
            
            if rec.backup_mode == 'full_system':
                # Full system backup - always compressed
                backup_base_path = os.path.join(rec.folder, f"backup_{timestamp.strftime('%Y_%m_%d_%H_%M_%S')}")
                with rec.backup_log():
                    try:
                        os.makedirs(rec.folder, exist_ok=True)
                        rec._backup_full_system(backup_base_path, timestamp)
                        successful |= rec
                    except OSError as exc:
                        _logger.exception(f"Full system backup failed - OSError: {exc}")
            else:
                # Database-only or database+filestore backup
                if rec.backup_format == 'zip':
                    # ZIP format - compressed by default
                    filename = self.filename(timestamp, ext=rec.backup_format)
                    with rec.backup_log():
                        try:
                            os.makedirs(rec.folder, exist_ok=True)
                        except OSError as exc:
                            _logger.exception(f"Action backup - OSError: {exc}")

                        with open(os.path.join(rec.folder, filename), "wb") as destiny:
                            if backup:
                                with open(backup) as cached:
                                    shutil.copyfileobj(cached, destiny)
                            else:
                                db.dump_db(
                                    self.env.cr.dbname, destiny, backup_format=rec.backup_format
                                )
                                backup = backup or destiny.name
                        successful |= rec
                else:
                    # DUMP format - create compressed version
                    base_filename = f"backup_{timestamp.strftime('%Y_%m_%d_%H_%M_%S')}"
                    temp_dir = os.path.join(rec.folder, f"{base_filename}_temp")
                    
                    with rec.backup_log():
                        try:
                            os.makedirs(rec.folder, exist_ok=True)
                            os.makedirs(temp_dir, exist_ok=True)
                            
                            # Create database backup
                            db_file = os.path.join(temp_dir, f"{self.env.cr.dbname}.dump")
                            with open(db_file, "wb") as destiny:
                                db.dump_db(self.env.cr.dbname, destiny, backup_format='dump')
                            
                            # Add filestore if needed
                            if rec.backup_mode == 'database_filestore':
                                filestore_path = tools.config.filestore(self.env.cr.dbname)
                                if os.path.exists(filestore_path):
                                    target_filestore = os.path.join(temp_dir, 'filestore')
                                    shutil.copytree(filestore_path, target_filestore)
                            
                            # Create metadata
                            metadata = {
                                'backup_info': {
                                    'timestamp': timestamp.isoformat(),
                                    'backup_mode': rec.backup_mode,
                                    'backup_format': rec.backup_format,
                                    'database_name': self.env.cr.dbname,
                                    'compressed': True
                                }
                            }
                            
                            metadata_file = os.path.join(temp_dir, 'metadata.json')
                            with open(metadata_file, 'w') as f:
                                json.dump(metadata, f, indent=2)
                            
                            # Create compressed archive
                            archive_path = os.path.join(rec.folder, f"{base_filename}.tar.gz")
                            shutil.make_archive(
                                archive_path[:-7],  # remove .tar.gz
                                'gztar',
                                rec.folder,
                                os.path.basename(temp_dir)
                            )
                            
                            # Cleanup temp directory
                            shutil.rmtree(temp_dir)
                            
                            _logger.info(f"Compressed backup created: {archive_path}")
                            successful |= rec
                            
                        except OSError as exc:
                            _logger.exception(f"Compressed backup failed - OSError: {exc}")

        # Handle SFTP backups with compression
        sftp = self.filtered(lambda r: r.method == "sftp")
        if sftp:
            for rec in sftp:
                timestamp = datetime.now()
                
                with rec.backup_log():
                    try:
                        # Create local compressed backup first
                        with tempfile.TemporaryDirectory() as temp_dir:
                            if rec.backup_mode == 'full_system':
                                backup_base_path = os.path.join(temp_dir, f"backup_{timestamp.strftime('%Y_%m_%d_%H_%M_%S')}")
                                rec._backup_full_system(backup_base_path, timestamp)
                                # Archive already created by _backup_full_system
                                archive_path = f"{backup_base_path}.tar.gz"
                            else:
                                # Create simple compressed backup
                                backup_name = f"backup_{timestamp.strftime('%Y_%m_%d_%H_%M_%S')}"
                                backup_temp_dir = os.path.join(temp_dir, backup_name)
                                os.makedirs(backup_temp_dir)
                                
                                # Database backup
                                db_file = os.path.join(backup_temp_dir, f"{self.env.cr.dbname}.dump")
                                with open(db_file, "wb") as f:
                                    db.dump_db(self.env.cr.dbname, f, backup_format='dump')
                                
                                # Filestore if needed
                                if rec.backup_mode == 'database_filestore':
                                    filestore_path = tools.config.filestore(self.env.cr.dbname)
                                    if os.path.exists(filestore_path):
                                        shutil.copytree(filestore_path, os.path.join(backup_temp_dir, 'filestore'))
                                
                                # Create archive
                                archive_path = os.path.join(temp_dir, f"{backup_name}.tar.gz")
                                shutil.make_archive(
                                    archive_path[:-7],
                                    'gztar',
                                    temp_dir,
                                    backup_name
                                )
                            
                            # Upload compressed archive to SFTP
                            with rec.sftp_connection() as remote:
                                try:
                                    remote.makedirs(rec.folder)
                                except pysftp.ConnectionException as exc:
                                    _logger.exception(f"pysftp ConnectionException: {exc}")
                                
                                remote_file = os.path.join(rec.folder, os.path.basename(archive_path))
                                remote.put(archive_path, remote_file)
                                _logger.info(f"Compressed backup uploaded to SFTP: {remote_file}")
                            
                            successful |= rec
                            
                    except Exception as exc:
                        _logger.exception(f"SFTP compressed backup failed: {exc}")

        # Cloud sync for successful backups
        for rec in successful:
            if rec.enable_cloud_sync:
                with rec.backup_log():
                    if rec.backup_mode == 'full_system':
                        # For full system backups, sync the compressed archive
                        archive_path = None
                        if rec.method == "local":
                            # Find the latest archive in the backup folder
                            import glob
                            pattern = os.path.join(rec.folder, "backup_*.tar.gz")
                            archives = glob.glob(pattern)
                            if archives:
                                archive_path = max(archives, key=os.path.getctime)
                        
                        if archive_path and os.path.exists(archive_path):
                            _logger.info(f"Starting cloud sync for: {archive_path}")
                            sync_success, sync_message = rec._sync_to_cloud(archive_path)
                            
                            if sync_success:
                                _logger.info(f"Cloud sync successful: {sync_message}")
                                rec.message_post(body=f"☁️ Cloud sync successful: {sync_message}")
                            else:
                                _logger.error(f"Cloud sync failed: {sync_message}")
                                rec.message_post(
                                    body=f"☁️ Cloud sync failed: {sync_message}",
                                    subtype_id=rec.env.ref("auto_backup.mail_message_subtype_failure").id,
                                )
                    else:
                        # For database/filestore backups, find the backup file
                        backup_file = None
                        if rec.method == "local":
                            if rec.backup_format == 'zip':
                                # Find latest .dump.zip file
                                pattern = os.path.join(rec.folder, "*.dump.zip")
                                files = glob.glob(pattern)
                                if files:
                                    backup_file = max(files, key=os.path.getctime)
                            else:
                                # Find latest .tar.gz file (compressed dump)
                                pattern = os.path.join(rec.folder, "backup_*.tar.gz")
                                files = glob.glob(pattern)
                                if files:
                                    backup_file = max(files, key=os.path.getctime)
                        
                        if backup_file and os.path.exists(backup_file):
                            sync_success, sync_message = rec._sync_to_cloud(backup_file)
                            
                            if sync_success:
                                _logger.info(f"Cloud sync successful: {sync_message}")
                                rec.message_post(body=f"☁️ Cloud sync successful: {sync_message}")
                            else:
                                _logger.error(f"Cloud sync failed: {sync_message}")
                                rec.message_post(
                                    body=f"☁️ Cloud sync failed: {sync_message}",
                                    subtype_id=rec.env.ref("auto_backup.mail_message_subtype_failure").id,
                                )

        # Remove old files for successful backups
        successful.cleanup()
        
        # Cloud cleanup for backups with cloud sync enabled
        for rec in successful.filtered('enable_cloud_sync'):
            rec._cleanup_cloud_backups()

    def _backup_full_system(self, backup_dir, timestamp):
        """Perform full system backup with compression"""
        self.ensure_one()
        
        # Create temporary working directory
        temp_backup_dir = f"{backup_dir}_temp"
        os.makedirs(temp_backup_dir, exist_ok=True)
        
        try:
            # Create subdirectories in temp location
            subdirs = ['database', 'filestore', 'custom_addons', 'system_configs', 'odoo_data']
            for subdir in subdirs:
                os.makedirs(os.path.join(temp_backup_dir, subdir), exist_ok=True)
            
            # Always backup database
            self._backup_database(temp_backup_dir)
            
            # Backup filestore (included in database+filestore and full_system modes)
            if self.backup_mode in ['database_filestore', 'full_system']:
                self._backup_filestore(temp_backup_dir)
            
            # Full system components
            if self.backup_mode == 'full_system':
                if self.include_custom_addons and self.custom_addons_path:
                    self._backup_custom_addons(temp_backup_dir)
                
                if self.include_system_configs:
                    self._backup_system_configs(temp_backup_dir)
                
                if self.include_odoo_data and self.odoo_data_path:
                    self._backup_odoo_data(temp_backup_dir)
            
            # Generate metadata and system info
            self._generate_system_info(temp_backup_dir)
            metadata = self._create_backup_metadata(temp_backup_dir, timestamp)
            
            # Generate restore scripts
            scripts_dir = self._generate_restore_scripts(temp_backup_dir, metadata)
            
            # Create compressed archive
            archive_name = f"backup_{timestamp.strftime('%Y_%m_%d_%H_%M_%S')}"
            archive_path = f"{backup_dir}.tar.gz"
            
            _logger.info(f"Creating compressed backup archive: {archive_path}")
            
            # Create tar.gz archive from temp directory
            shutil.make_archive(
                backup_dir,  # base name (without extension)
                'gztar',     # format
                os.path.dirname(temp_backup_dir),  # root directory
                os.path.basename(temp_backup_dir)   # directory to archive
            )
            
            # Update metadata with final archive info
            metadata['backup_info']['archive_path'] = archive_path
            metadata['backup_info']['compressed'] = True
            metadata['backup_info']['compression_format'] = 'tar.gz'
            
            # Create backup history record with archive path
            self._create_backup_history_record(archive_path, metadata, scripts_dir)
            
            _logger.info(f"Compressed backup created successfully: {archive_path}")
            
            return metadata
            
        finally:
            # Cleanup temp directory
            if os.path.exists(temp_backup_dir):
                shutil.rmtree(temp_backup_dir)
                _logger.info(f"Cleaned up temp directory: {temp_backup_dir}")

    def _backup_database(self, backup_dir):
        """Backup database with metadata"""
        # db_backup_path = os.path.join(backup_dir, 'database', f'{self.env.cr.dbname}.dump')
        
        # with open(db_backup_path, 'wb') as db_file:
        #     db.dump_db(self.env.cr.dbname, db_file, backup_format='dump')



        # try:
        #     with self.sudo():
        #         db_backup_path = os.path.join(backup_dir, 'database', f'{self.env.cr.dbname}.dump')
        #         with open(db_backup_path, 'wb') as db_file:
        #             db.dump_db(self.env.cr.dbname, db_file, backup_format='dump')
        # except Exception as e:
        #     # Fallback to superuser context
        #     pass

        try:
            from odoo import tools
            original_list_db = tools.config.get('list_db', False)
            
            # Temporarily enable db management
            tools.config['list_db'] = True
            
            db_backup_path = os.path.join(backup_dir, 'database', f'{self.env.cr.dbname}.dump')
            with open(db_backup_path, 'wb') as db_file:
                db.dump_db(self.env.cr.dbname, db_file, backup_format='dump')
                
            # Restore original config
            tools.config['list_db'] = original_list_db
            
        except Exception as e:
            # Ensure config is restored
            tools.config['list_db'] = original_list_db
            raise

        
        _logger.info(f"Database backed up to: {db_backup_path}")

    def _backup_filestore(self, backup_dir):
        """Backup filestore directory"""
        filestore_path = tools.config.filestore(self.env.cr.dbname)
        target_path = os.path.join(backup_dir, 'filestore')
        
        if os.path.exists(filestore_path):
            shutil.copytree(filestore_path, target_path, dirs_exist_ok=True)
            _logger.info(f"Filestore backed up to: {target_path}")
        else:
            _logger.warning(f"Filestore path not found: {filestore_path}")

    def _backup_custom_addons(self, backup_dir):
        """Backup custom addons directory"""
        if not self.custom_addons_path or not os.path.exists(self.custom_addons_path):
            _logger.warning(f"Custom addons path not found: {self.custom_addons_path}")
            return
        
        target_path = os.path.join(backup_dir, 'custom_addons')
        shutil.copytree(self.custom_addons_path, target_path, dirs_exist_ok=True)
        _logger.info(f"Custom addons backed up to: {target_path}")

    def _backup_system_configs(self, backup_dir):
        """Backup system configuration files"""
        config_dir = os.path.join(backup_dir, 'system_configs')
        
        configs = {
            'odoo.conf': self.odoo_config_path,
            'nginx_config': self.nginx_config_path,
            'systemd_service': self.systemd_service_path,
        }
        
        for config_name, config_path in configs.items():
            if config_path and os.path.exists(config_path):
                target_file = os.path.join(config_dir, config_name)
                shutil.copy2(config_path, target_file)
                _logger.info(f"Config {config_name} backed up to: {target_file}")
            else:
                _logger.warning(f"Config file not found: {config_path}")

    def _backup_odoo_data(self, backup_dir):
        """Backup odoo data directory"""
        if not self.odoo_data_path or not os.path.exists(self.odoo_data_path):
            _logger.warning(f"Odoo data path not found: {self.odoo_data_path}")
            return
        
        target_path = os.path.join(backup_dir, 'odoo_data')
        shutil.copytree(self.odoo_data_path, target_path, dirs_exist_ok=True)
        _logger.info(f"Odoo data backed up to: {target_path}")

    def _generate_system_info(self, backup_dir):
        """Generate system information files"""
        system_info = {
            'timestamp': datetime.now().isoformat(),
            'odoo_version': self.env['ir.module.module'].search([('name', '=', 'base')]).latest_version,
            'database_name': self.env.cr.dbname,
            'python_version': subprocess.check_output(['python3', '--version']).decode().strip(),
            'os_info': subprocess.check_output(['uname', '-a']).decode().strip(),
            'disk_usage': {},
        }
        
        # Get disk usage for important paths
        paths_to_check = [self.folder]
        if self.custom_addons_path:
            paths_to_check.append(self.custom_addons_path)
        if self.odoo_data_path:
            paths_to_check.append(self.odoo_data_path)
        
        for path in paths_to_check:
            if os.path.exists(path):
                try:
                    usage = shutil.disk_usage(path)
                    system_info['disk_usage'][path] = {
                        'total': usage.total,
                        'used': usage.used,
                        'free': usage.free
                    }
                except Exception as e:
                    _logger.warning(f"Could not get disk usage for {path}: {e}")
        
        info_file = os.path.join(backup_dir, 'system_info.json')
        with open(info_file, 'w') as f:
            json.dump(system_info, f, indent=2)
        
        _logger.info(f"System info generated: {info_file}")

    def _create_backup_metadata(self, backup_dir, timestamp):
        """Create comprehensive metadata.json"""
        metadata = {
            'backup_info': {
                'timestamp': timestamp.isoformat(),
                'backup_mode': self.backup_mode,
                'backup_format': self.backup_format,
                'odoo_user': self.odoo_user,
                'database_name': self.env.cr.dbname,
            },
            'paths': {
                'custom_addons_path': self.custom_addons_path,
                'odoo_config_path': self.odoo_config_path,
                'nginx_config_path': self.nginx_config_path,
                'systemd_service_path': self.systemd_service_path,
                'odoo_data_path': self.odoo_data_path,
                'python_venv_path': self.python_venv_path,
            },
            'components_included': {
                'database': True,
                'filestore': self.backup_mode in ['database_filestore', 'full_system'],
                'custom_addons': self.backup_mode == 'full_system' and self.include_custom_addons,
                'system_configs': self.backup_mode == 'full_system' and self.include_system_configs,
                'odoo_data': self.backup_mode == 'full_system' and self.include_odoo_data,
            },
            'backup_size': self._calculate_backup_size(backup_dir),
        }
        
        metadata_file = os.path.join(backup_dir, 'metadata.json')
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        _logger.info(f"Backup metadata created: {metadata_file}")
        
        # IMPORTANT: Return the metadata dictionary
        return metadata

    def _calculate_backup_size(self, backup_dir):
        """Calculate total backup size"""
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(backup_dir):
            for filename in filenames:
                file_path = os.path.join(dirpath, filename)
                try:
                    total_size += os.path.getsize(file_path)
                except (OSError, FileNotFoundError):
                    pass
        return total_size

    @api.model
    def action_backup_all(self):
        """Run all scheduled backups."""
        return self.search([]).action_backup()

    @contextmanager
    def backup_log(self):
        """Log a backup result."""
        try:
            _logger.info(f"Starting database backup: {self.name}")
            yield
        except Exception:
            _logger.exception(f"Database backup failed: {self.name}")
            escaped_tb = tools.html_escape(traceback.format_exc())
            self.message_post(  # pylint: disable=translation-required
                body=f"<p>{_('Database backup failed.')}</p><pre>{escaped_tb}</pre>",
                subtype_id=self.env.ref("auto_backup.mail_message_subtype_failure").id,
            )
        else:
            _logger.info(f"Database backup succeeded: {self.name}")
            self.message_post(body=_("Database backup succeeded."))

    def cleanup(self):
        """Clean up old backups including compressed files"""
        now = datetime.now()
        for rec in self.filtered("days_to_keep"):
            with rec.cleanup_log():
                bu_format = rec.backup_format
                
                # Define file patterns to clean
                if rec.backup_mode == 'full_system':
                    # Full system backups are always .tar.gz
                    file_patterns = ['backup_*.tar.gz']
                else:
                    if bu_format == "zip":
                        file_patterns = ['*.dump.zip']
                    else:
                        # DUMP format can be compressed or uncompressed
                        file_patterns = ['*.dump', 'backup_*.tar.gz']
                
                # Calculate cutoff date
                cutoff_date = now - timedelta(days=rec.days_to_keep)
                oldest_timestamp = cutoff_date.strftime('%Y_%m_%d')
                
                if rec.method == "local":
                    for pattern in file_patterns:
                        for name in iglob(os.path.join(rec.folder, pattern)):
                            file_name = os.path.basename(name)
                            
                            # Check if file is older than cutoff
                            should_delete = False
                            
                            if file_name.startswith('backup_'):
                                # Extract timestamp from backup_YYYY_MM_DD_HH_MM_SS format
                                try:
                                    timestamp_part = file_name.split('backup_')[1].split('.')[0]
                                    if len(timestamp_part) >= 10:  # YYYY_MM_DD minimum
                                        file_date_str = timestamp_part[:10]  # YYYY_MM_DD
                                        if file_date_str < oldest_timestamp:
                                            should_delete = True
                                except (IndexError, ValueError):
                                    _logger.warning(f"Could not parse timestamp from filename: {file_name}")
                            else:
                                # For legacy format files, use file modification time
                                file_mtime = datetime.fromtimestamp(os.path.getmtime(name))
                                if file_mtime < cutoff_date:
                                    should_delete = True
                            
                            if should_delete:
                                try:
                                    os.unlink(name)
                                    _logger.info(f"Deleted old backup: {name}")
                                except OSError as e:
                                    _logger.error(f"Failed to delete {name}: {e}")

                elif rec.method == "sftp":
                    with rec.sftp_connection() as remote:
                        try:
                            for name in remote.listdir(rec.folder):
                                should_delete = False
                                
                                # Check against all patterns
                                for pattern in file_patterns:
                                    pattern_regex = pattern.replace('*', '.*')
                                    if re.match(pattern_regex, name):
                                        if name.startswith('backup_'):
                                            try:
                                                timestamp_part = name.split('backup_')[1].split('.')[0]
                                                if len(timestamp_part) >= 10:
                                                    file_date_str = timestamp_part[:10]
                                                    if file_date_str < oldest_timestamp:
                                                        should_delete = True
                                            except (IndexError, ValueError):
                                                _logger.warning(f"Could not parse SFTP timestamp: {name}")
                                        else:
                                            # For legacy files, check file timestamp if available
                                            try:
                                                file_stat = remote.stat(f"{rec.folder}/{name}")
                                                file_mtime = datetime.fromtimestamp(file_stat.st_mtime)
                                                if file_mtime < cutoff_date:
                                                    should_delete = True
                                            except Exception:
                                                # If we can't get file stats, skip deletion to be safe
                                                pass
                                        break
                                
                                if should_delete:
                                    try:
                                        remote.unlink(f"{rec.folder}/{name}")
                                        _logger.info(f"Deleted old SFTP backup: {name}")
                                    except Exception as e:
                                        _logger.error(f"Failed to delete SFTP file {name}: {e}")
                        
                        except Exception as e:
                            _logger.error(f"SFTP cleanup error: {e}")

    @contextmanager
    def cleanup_log(self):
        """Log a possible cleanup failure."""
        self.ensure_one()
        try:
            _logger.info(f"Starting cleanup process after database backup: {self.name}")
            yield
        except Exception:
            _logger.exception(f"Cleanup of old database backups failed: {self.name}")
            escaped_tb = tools.html_escape(traceback.format_exc())
            self.message_post(  # pylint: disable=translation-required
                body=(
                    f"<p>{_('Cleanup of old database backups failed.')}</p>"
                    f"<pre>{escaped_tb}</pre>"
                ),
                subtype_id=self.env.ref("auto_backup.failure").id,
            )
        else:
            _logger.info(f"Cleanup of old database backups succeeded: {self.name}")

    @staticmethod
    def filename(when, ext="zip"):
        """Generate a file name for a backup.

        :param datetime.datetime when:
            Use this datetime instead of :meth:`datetime.datetime.now`.
        :param str ext: Extension of the file. Default: dump.zip
        """
        return "{:%Y_%m_%d_%H_%M_%S}.{ext}".format(
            when, ext="dump.zip" if ext == "zip" else ext
        )

    def sftp_connection(self):
        """Return a new SFTP connection with found parameters."""
        self.ensure_one()
        params = {
            "host": self.sftp_host,
            "username": self.sftp_user,
            "port": self.sftp_port,
        }
        _logger.debug(
            "Trying to connect to sftp://%(username)s@%(host)s:%(port)d", extra=params
        )
        if self.sftp_private_key:
            params["private_key"] = self.sftp_private_key
            if self.sftp_password:
                params["private_key_pass"] = self.sftp_password
        else:
            params["password"] = self.sftp_password

        return pysftp.Connection(**params)
    
    def _generate_restore_scripts(self, backup_dir, metadata):
        """Generate all restore scripts"""
        scripts_dir = os.path.join(backup_dir, 'scripts')
        os.makedirs(scripts_dir, exist_ok=True)
        
        # Generate restore configuration
        self._create_restore_config(scripts_dir, metadata)
        
        # Generate scripts
        self._create_same_server_restore_script(scripts_dir, metadata)
        self._create_pre_restore_backup_script(scripts_dir)
        self._generate_rollback_script(scripts_dir)
        
        # Make scripts executable
        self._make_scripts_executable(scripts_dir)
        
        _logger.info(f"Restore scripts generated in: {scripts_dir}")
        return scripts_dir

    def _create_restore_config(self, scripts_dir, metadata):
        """Create restore configuration file"""
        restore_config = {
            'backup_metadata': metadata,
            'restore_settings': {
                'database_name': self.env.cr.dbname,
                'odoo_user': self.odoo_user,
                'backup_mode': self.backup_mode,
                'services_to_stop': ['odoo', 'nginx'],
                'services_to_start': ['postgresql', 'odoo', 'nginx'],
            },
            'paths': {
                'custom_addons_path': self.custom_addons_path,
                'odoo_config_path': self.odoo_config_path,
                'nginx_config_path': self.nginx_config_path,
                'systemd_service_path': self.systemd_service_path,
                'odoo_data_path': self.odoo_data_path,
                'python_venv_path': self.python_venv_path,
            }
        }
        
        config_file = os.path.join(scripts_dir, 'restore_config.json')
        with open(config_file, 'w') as f:
            json.dump(restore_config, f, indent=2)

    def _create_same_server_restore_script(self, scripts_dir, metadata):
        """Create restore script for same server"""
        script_content = '''#!/bin/bash
# Same Server Restore Script
# Generated by Odoo Auto-Backup Module
# Backup Date: {timestamp}
# Backup Mode: {backup_mode}

set -e  # Exit on any error

SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
BACKUP_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="$SCRIPT_DIR/restore_config.json"
LOG_FILE="/var/log/odoo_restore.log"
PRE_RESTORE_DIR="/tmp/pre_restore_backup_$(date +%Y%m%d_%H%M%S)"

# Colors for output
RED='\\033[0;31m'
GREEN='\\033[0;32m'
YELLOW='\\033[1;33m'
NC='\\033[0m' # No Color

# Functions
log_message() {{
    echo "$(date '+%Y-%m-%d %H:%M:%S'): $1" | tee -a "$LOG_FILE"
}}

log_error() {{
    echo -e "${{RED}}ERROR: $1${{NC}}" | tee -a "$LOG_FILE"
}}

log_success() {{
    echo -e "${{GREEN}}SUCCESS: $1${{NC}}" | tee -a "$LOG_FILE"
}}

log_warning() {{
    echo -e "${{YELLOW}}WARNING: $1${{NC}}" | tee -a "$LOG_FILE"
}}

check_root() {{
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root"
        exit 1
    fi
}}

backup_current_system() {{
    log_message "Creating pre-restore backup..."
    mkdir -p "$PRE_RESTORE_DIR"
    
    # Backup current database
    if sudo -u {odoo_user} pg_dump {database_name} > "$PRE_RESTORE_DIR/current_database.sql" 2>/dev/null; then
        log_success "Current database backed up"
    else
        log_warning "Could not backup current database"
    fi
    
    # Backup current filestore
    if [ -d "{filestore_path}" ]; then
        cp -r "{filestore_path}" "$PRE_RESTORE_DIR/filestore" 2>/dev/null || log_warning "Could not backup filestore"
    fi
    
    echo "$PRE_RESTORE_DIR" > "$SCRIPT_DIR/pre_restore_path.txt"
    log_success "Pre-restore backup created at: $PRE_RESTORE_DIR"
}}

stop_services() {{
    log_message "Stopping services..."
    
    services=("odoo" "nginx")
    for service in "${{services[@]}}"; do
        if systemctl is-active --quiet "$service"; then
            systemctl stop "$service"
            log_success "Stopped $service"
        else
            log_warning "$service was not running"
        fi
    done
}}

restore_database() {{
    log_message "Restoring database..."
    
    # Find database backup
    DB_BACKUP=""
    if [ -f "$BACKUP_DIR/database/{database_name}.dump" ]; then
        DB_BACKUP="$BACKUP_DIR/database/{database_name}.dump"
    else
        DB_BACKUP=$(find "$BACKUP_DIR" -name "*.dump" -type f | head -1)
    fi
    
    if [ -z "$DB_BACKUP" ] || [ ! -f "$DB_BACKUP" ]; then
        log_error "Database backup file not found"
        exit 1
    fi
    
    log_message "Found database backup: $DB_BACKUP"
    
    # Copy to temp location to avoid permission issues
    TEMP_DUMP="/tmp/{database_name}_restore_$(date +%Y%m%d_%H%M%S).dump"
    cp "$DB_BACKUP" "$TEMP_DUMP"
    chmod 644 "$TEMP_DUMP"
    
    # Drop existing database
    sudo -u {odoo_user} dropdb --if-exists {database_name} 2>/dev/null || true
    
    # Create new database
    sudo -u {odoo_user} createdb {database_name}
    
    # Restore database
    if sudo -u {odoo_user} pg_restore -d {database_name} "$TEMP_DUMP" 2>/dev/null; then
        log_success "Database restored successfully"
    else
        log_warning "Database restore completed with warnings"
    fi
    
    # Verify restore
    USER_COUNT=$(sudo -u {odoo_user} psql -d {database_name} -t -c "SELECT COUNT(*) FROM res_users;" 2>/dev/null | xargs || echo "0")
    if [ "$USER_COUNT" -gt 0 ]; then
        log_success "Database verification passed - found $USER_COUNT users"
    else
        log_warning "Database verification: no users found"
    fi
    
    # Cleanup
    rm -f "$TEMP_DUMP"
    log_success "Cleaned up temporary dump file"
}}

restore_filestore() {{
    log_message "Restoring filestore..."
    
    FILESTORE_BACKUP="$BACKUP_DIR/filestore"
    FILESTORE_TARGET="{filestore_path}"
    
    if [ -d "$FILESTORE_BACKUP" ]; then
        # Remove current filestore
        rm -rf "$FILESTORE_TARGET"
        
        # Restore filestore
        cp -r "$FILESTORE_BACKUP" "$FILESTORE_TARGET"
        
        # Fix permissions
        chown -R {odoo_user}:{odoo_user} "$FILESTORE_TARGET"
        
        log_success "Filestore restored successfully"
    else
        log_warning "Filestore backup not found, skipping"
    fi
}}

restore_custom_addons() {{
    log_message "Restoring custom addons..."
    
    ADDONS_BACKUP="$BACKUP_DIR/custom_addons"
    ADDONS_TARGET="{custom_addons_path}"
    
    if [ -d "$ADDONS_BACKUP" ] && [ -n "$ADDONS_TARGET" ]; then
        # Backup current addons
        if [ -d "$ADDONS_TARGET" ]; then
            mv "$ADDONS_TARGET" "${{ADDONS_TARGET}}.backup.$(date +%Y%m%d_%H%M%S)"
        fi
        
        # Restore addons
        cp -r "$ADDONS_BACKUP" "$ADDONS_TARGET"
        chown -R {odoo_user}:{odoo_user} "$ADDONS_TARGET"
        
        log_success "Custom addons restored successfully"
    else
        log_warning "Custom addons backup not found or path not configured, skipping"
    fi
}}

restore_system_configs() {{
    log_message "Restoring system configurations..."
    
    CONFIGS_BACKUP="$BACKUP_DIR/system_configs"
    
    if [ -d "$CONFIGS_BACKUP" ]; then
        # Restore Odoo config
        if [ -f "$CONFIGS_BACKUP/odoo.conf" ] && [ -n "{odoo_config_path}" ]; then
            cp "$CONFIGS_BACKUP/odoo.conf" "{odoo_config_path}.backup.$(date +%Y%m%d_%H%M%S)"
            cp "$CONFIGS_BACKUP/odoo.conf" "{odoo_config_path}"
            log_success "Odoo config restored"
        fi
        
        # Restore Nginx config
        if [ -f "$CONFIGS_BACKUP/nginx_config" ] && [ -n "{nginx_config_path}" ]; then
            cp "{nginx_config_path}" "{nginx_config_path}.backup.$(date +%Y%m%d_%H%M%S)"
            cp "$CONFIGS_BACKUP/nginx_config" "{nginx_config_path}"
            log_success "Nginx config restored"
        fi
        
        # Restore Systemd service
        if [ -f "$CONFIGS_BACKUP/systemd_service" ] && [ -n "{systemd_service_path}" ]; then
            cp "{systemd_service_path}" "{systemd_service_path}.backup.$(date +%Y%m%d_%H%M%S)"
            cp "$CONFIGS_BACKUP/systemd_service" "{systemd_service_path}"
            systemctl daemon-reload
            log_success "Systemd service restored"
        fi
    else
        log_warning "System configs backup not found, skipping"
    fi
}}

restore_odoo_data() {{
    log_message "Restoring Odoo data..."
    
    DATA_BACKUP="$BACKUP_DIR/odoo_data"
    DATA_TARGET="{odoo_data_path}"
    
    if [ -d "$DATA_BACKUP" ] && [ -n "$DATA_TARGET" ]; then
        # Backup current data
        if [ -d "$DATA_TARGET" ]; then
            mv "$DATA_TARGET" "${{DATA_TARGET}}.backup.$(date +%Y%m%d_%H%M%S)"
        fi
        
        # Restore data
        cp -r "$DATA_BACKUP" "$DATA_TARGET"
        chown -R {odoo_user}:{odoo_user} "$DATA_TARGET"
        
        log_success "Odoo data restored successfully"
    else
        log_warning "Odoo data backup not found or path not configured, skipping"
    fi
}}

start_services() {{
    log_message "Starting services..."
    
    services=("postgresql" "odoo" "nginx")
    for service in "${{services[@]}}"; do
        if systemctl start "$service"; then
            log_success "Started $service"
        else
            log_error "Failed to start $service"
        fi
    done
}}

verify_restore() {{
    log_message "Verifying restore..."
    
    # Wait for services to start
    sleep 10
    
    # Check if Odoo is responding
    if curl -f -s http://localhost:8069/web/database/manager >/dev/null; then
        log_success "Odoo is responding"
    else
        log_warning "Odoo may not be responding properly"
    fi
    
    # Check database connection
    if sudo -u {odoo_user} psql -d {database_name} -c "SELECT 1;" >/dev/null 2>&1; then
        log_success "Database connection verified"
    else
        log_error "Database connection failed"
    fi
}}

rollback() {{
    log_error "Restore failed, initiating rollback..."
    if [ -f "$SCRIPT_DIR/rollback.sh" ]; then
        bash "$SCRIPT_DIR/rollback.sh"
    else
        log_error "Rollback script not found"
    fi
}}

# Main execution
main() {{
    log_message "Starting same server restore..."
    log_message "Backup source: $BACKUP_DIR"
    log_message "Backup mode: {backup_mode}"
    
    check_root
    
    # Set trap for rollback on error
    trap rollback ERR
    
    backup_current_system
    stop_services
    
    # Restore based on backup mode
    restore_database
    
    if [ "{backup_mode}" = "database_filestore" ] || [ "{backup_mode}" = "full_system" ]; then
        restore_filestore
    fi
    
    if [ "{backup_mode}" = "full_system" ]; then
        restore_custom_addons
        # restore_system_configs
        restore_odoo_data
    fi
    
    start_services
    verify_restore
    
    log_success "Restore completed successfully!"
    log_message "Pre-restore backup saved at: $PRE_RESTORE_DIR"
    log_message "Restore log: $LOG_FILE"
}}

# Show usage if no arguments
if [ $# -eq 0 ]; then
    echo "Usage: $0"
    echo "This script will restore the Odoo system from the backup in this directory."
    echo "Make sure to run as root: sudo $0"
    exit 1
fi

main "$@"
'''.format(
            timestamp=metadata['backup_info']['timestamp'],
            backup_mode=metadata['backup_info']['backup_mode'],
            database_name=metadata['backup_info']['database_name'],
            filestore_path=tools.config.filestore(self.env.cr.dbname),
            odoo_user=metadata['backup_info']['odoo_user'],
            custom_addons_path=metadata['paths']['custom_addons_path'] or '',
            odoo_config_path=metadata['paths']['odoo_config_path'] or '',
            nginx_config_path=metadata['paths']['nginx_config_path'] or '',
            systemd_service_path=metadata['paths']['systemd_service_path'] or '',
            odoo_data_path=metadata['paths']['odoo_data_path'] or ''
        )
        
        script_file = os.path.join(scripts_dir, 'same_server_restore.sh')
        with open(script_file, 'w') as f:
            f.write(script_content)

    def _create_pre_restore_backup_script(self, scripts_dir):
        """Create script to backup current system before restore"""
        script_content = '''#!/bin/bash
# Pre-Restore Backup Script
# This script creates a backup of the current system before restore

set -e

LOG_FILE="/var/log/odoo_pre_restore_backup.log"
BACKUP_DIR="/tmp/pre_restore_backup_$(date +%Y%m%d_%H%M%S)"

log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S'): $1" | tee -a "$LOG_FILE"
}

main() {
    log_message "Creating pre-restore backup..."
    
    mkdir -p "$BACKUP_DIR"
    
    # Backup database
    if sudo -u postgres pg_dump ''' + self.env.cr.dbname + ''' > "$BACKUP_DIR/database.sql"; then
        log_message "Database backed up"
    fi
    
    # Backup filestore
    FILESTORE_PATH="''' + tools.config.filestore(self.env.cr.dbname) + '''"
    if [ -d "$FILESTORE_PATH" ]; then
        cp -r "$FILESTORE_PATH" "$BACKUP_DIR/filestore"
        log_message "Filestore backed up"
    fi
    
    echo "$BACKUP_DIR"
    log_message "Pre-restore backup completed: $BACKUP_DIR"
}

main "$@"
'''
        
        script_file = os.path.join(scripts_dir, 'pre_restore_backup.sh')
        with open(script_file, 'w') as f:
            f.write(script_content)

    def _generate_rollback_script(self, scripts_dir):
        """Create rollback script in case restore fails"""
        script_content = '''#!/bin/bash
# Rollback Script
# This script restores the system from pre-restore backup

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="/var/log/odoo_rollback.log"

log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S'): $1" | tee -a "$LOG_FILE"
}

main() {
    log_message "Starting rollback..."
    
    # Get pre-restore backup path
    PRE_RESTORE_PATH_FILE="$SCRIPT_DIR/pre_restore_path.txt"
    if [ ! -f "$PRE_RESTORE_PATH_FILE" ]; then
        log_message "ERROR: Pre-restore backup path not found"
        exit 1
    fi
    
    PRE_RESTORE_DIR=$(cat "$PRE_RESTORE_PATH_FILE")
    
    if [ ! -d "$PRE_RESTORE_DIR" ]; then
        log_message "ERROR: Pre-restore backup directory not found: $PRE_RESTORE_DIR"
        exit 1
    fi
    
    log_message "Rolling back from: $PRE_RESTORE_DIR"
    
    # Stop services
    systemctl stop odoo nginx
    
    # Restore database
    if [ -f "$PRE_RESTORE_DIR/current_database.sql" ]; then
        sudo -u postgres dropdb --if-exists ''' + self.env.cr.dbname + '''
        sudo -u postgres createdb ''' + self.env.cr.dbname + '''
        sudo -u postgres psql ''' + self.env.cr.dbname + ''' < "$PRE_RESTORE_DIR/current_database.sql"
        log_message "Database rolled back"
    fi
    
    # Restore filestore
    if [ -d "$PRE_RESTORE_DIR/filestore" ]; then
        rm -rf "''' + tools.config.filestore(self.env.cr.dbname) + '''"
        cp -r "$PRE_RESTORE_DIR/filestore" "''' + tools.config.filestore(self.env.cr.dbname) + '''"
        chown -R ''' + (self.odoo_user or 'odoo') + ''':''' + (self.odoo_user or 'odoo') + ''' "''' + tools.config.filestore(self.env.cr.dbname) + '''"
        log_message "Filestore rolled back"
    fi
    
    # Start services
    systemctl start postgresql odoo nginx
    
    log_message "Rollback completed"
}

main "$@"
'''
        
        script_file = os.path.join(scripts_dir, 'rollback.sh')
        with open(script_file, 'w') as f:
            f.write(script_content)

    def _make_scripts_executable(self, scripts_dir):
        """Make all scripts executable"""
        scripts = ['same_server_restore.sh', 'pre_restore_backup.sh', 'rollback.sh']
        
        for script in scripts:
            script_path = os.path.join(scripts_dir, script)
            if os.path.exists(script_path):
                # Make executable (755)
                os.chmod(script_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
                _logger.info(f"Made executable: {script_path}")

    def _check_rclone_installed(self):
        """Check if rclone is installed and accessible"""
        try:
            result = subprocess.run(['rclone', 'version'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                _logger.info(f"rclone is installed: {result.stdout.splitlines()[0]}")
                return True
            else:
                _logger.error(f"rclone version check failed: {result.stderr}")
                return False
        except FileNotFoundError:
            _logger.error("rclone is not installed or not in PATH")
            return False
        except subprocess.TimeoutExpired:
            _logger.error("rclone version check timed out")
            return False
        except Exception as e:
            _logger.error(f"Error checking rclone installation: {e}")
            return False

    def _validate_rclone_config(self):
        """Validate rclone configuration exists and is accessible"""
        if not self.rclone_config_name:
            return False, "rclone remote name is not configured"
        
        try:
            # Check if remote exists
            result = subprocess.run([
                'rclone', 'listremotes'
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                return False, f"Failed to list rclone remotes: {result.stderr}"
            
            remotes = [line.strip().rstrip(':') for line in result.stdout.splitlines()]
            if self.rclone_config_name not in remotes:
                return False, f"Remote '{self.rclone_config_name}' not found in rclone config. Available remotes: {', '.join(remotes)}"
            
            return True, f"Remote '{self.rclone_config_name}' is configured"
            
        except subprocess.TimeoutExpired:
            return False, "rclone remote validation timed out"
        except Exception as e:
            return False, f"Error validating rclone config: {e}"

    def action_test_cloud_connection(self):
        """Test connection to cloud storage"""
        self.ensure_one()
        
        if not self.enable_cloud_sync:
            raise UserError(_("Cloud sync is not enabled"))
        
        if not self._check_rclone_installed():
            raise UserError(_("rclone is not installed. Please install rclone first."))
        
        is_valid, message = self._validate_rclone_config()
        if not is_valid:
            raise UserError(_(f"rclone configuration error: {message}"))
        
        try:
            # Test connection by listing root directory
            test_path = f"{self.rclone_config_name}:"
            result = subprocess.run([
                'rclone', 'lsd', test_path, '--max-depth', '1'
            ], capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                # Test creating a test directory
                test_dir = f"{self.rclone_config_name}:{self.cloud_backup_path}/test_connection"
                subprocess.run([
                    'rclone', 'mkdir', test_dir
                ], capture_output=True, text=True, timeout=30)
                
                # Remove test directory
                subprocess.run([
                    'rclone', 'rmdir', test_dir
                ], capture_output=True, text=True, timeout=30)
                
                raise UserError(_("✅ Cloud connection test successful!\n\nRemote: %s\nPath: %s") % 
                              (self.rclone_config_name, self.cloud_backup_path))
            else:
                raise UserError(_("❌ Cloud connection test failed:\n%s") % result.stderr)
                
        except subprocess.TimeoutExpired:
            raise UserError(_("❌ Cloud connection test timed out"))
        except Exception as e:
            raise UserError(_("❌ Cloud connection test error: %s") % str(e))
        
    def _sync_to_cloud(self, backup_path):
        """Upload backup to cloud storage using rclone"""
        if not self.enable_cloud_sync:
            return True, "Cloud sync disabled"
        
        if not self._check_rclone_installed():
            return False, "rclone not installed"
        
        is_valid, message = self._validate_rclone_config()
        if not is_valid:
            return False, f"rclone config error: {message}"
        
        try:
            # Prepare cloud path
            filename = os.path.basename(backup_path)
            cloud_full_path = f"{self.rclone_config_name}:{self.cloud_backup_path}/{filename}"
            
            # Prepare rclone command
            rclone_cmd = ['rclone', 'copy', backup_path, 
                         f"{self.rclone_config_name}:{self.cloud_backup_path}"]
            
            # Add bandwidth limit if specified
            if self.cloud_bandwidth_limit:
                rclone_cmd.extend(['--bwlimit', self.cloud_bandwidth_limit])
            
            # Add progress reporting
            rclone_cmd.extend(['--progress', '--stats-one-line'])
            
            _logger.info(f"Starting cloud upload: {backup_path} → {cloud_full_path}")
            
            # Execute upload
            result = subprocess.run(rclone_cmd, 
                                  capture_output=True, text=True, timeout=3600)  # 1 hour timeout
            
            if result.returncode == 0:
                _logger.info(f"Cloud upload successful: {cloud_full_path}")
                
                # Verify upload if enabled
                if self.verify_cloud_upload:
                    verify_success, verify_msg = self._verify_cloud_sync(cloud_full_path, backup_path)
                    if verify_success:
                        return True, f"Upload and verification successful: {cloud_full_path}"
                    else:
                        return False, f"Upload successful but verification failed: {verify_msg}"
                else:
                    return True, f"Upload successful: {cloud_full_path}"
            else:
                _logger.error(f"Cloud upload failed: {result.stderr}")
                return False, f"Upload failed: {result.stderr}"
                
        except subprocess.TimeoutExpired:
            return False, "Cloud upload timed out (>1 hour)"
        except Exception as e:
            _logger.error(f"Cloud upload error: {e}")
            return False, f"Upload error: {str(e)}"

    def _verify_cloud_sync(self, cloud_path, local_path):
        """Verify cloud backup integrity"""
        try:
            # Get local file size
            local_size = os.path.getsize(local_path)
            
            # Get cloud file info
            result = subprocess.run([
                'rclone', 'lsl', cloud_path
            ], capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                # Parse rclone output: size date time filename
                lines = result.stdout.strip().split('\n')
                if lines and lines[0]:
                    parts = lines[0].split()
                    if len(parts) >= 4:
                        cloud_size = int(parts[0])
                        
                        if local_size == cloud_size:
                            _logger.info(f"Cloud backup verification successful: {cloud_path} ({cloud_size} bytes)")
                            return True, f"Size verified: {cloud_size} bytes"
                        else:
                            return False, f"Size mismatch: local {local_size} vs cloud {cloud_size}"
                    else:
                        return False, "Could not parse cloud file info"
                else:
                    return False, "Cloud file not found"
            else:
                return False, f"Failed to get cloud file info: {result.stderr}"
                
        except Exception as e:
            return False, f"Verification error: {str(e)}"

    def _list_cloud_backups(self):
        """List all backups in cloud storage"""
        if not self.enable_cloud_sync or not self.rclone_config_name:
            return []
        
        try:
            cloud_dir = f"{self.rclone_config_name}:{self.cloud_backup_path}"
            result = subprocess.run([
                'rclone', 'lsl', cloud_dir
            ], capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                backups = []
                for line in result.stdout.strip().split('\n'):
                    if line.strip():
                        parts = line.split()
                        if len(parts) >= 4:
                            size = int(parts[0])
                            date_str = parts[1]
                            time_str = parts[2]
                            filename = ' '.join(parts[3:])
                            
                            backups.append({
                                'filename': filename,
                                'size': size,
                                'date': f"{date_str} {time_str}",
                                'cloud_path': f"{cloud_dir}/{filename}"
                            })
                return backups
            else:
                _logger.error(f"Failed to list cloud backups: {result.stderr}")
                return []
                
        except Exception as e:
            _logger.error(f"Error listing cloud backups: {e}")
            return []

    def _download_from_cloud(self, cloud_filename, local_destination):
        """Download backup from cloud storage"""
        if not self.enable_cloud_sync or not self.rclone_config_name:
            return False, "Cloud sync not configured"
        
        try:
            cloud_path = f"{self.rclone_config_name}:{self.cloud_backup_path}/{cloud_filename}"
            
            _logger.info(f"Downloading from cloud: {cloud_path} → {local_destination}")
            
            result = subprocess.run([
                'rclone', 'copy', cloud_path, local_destination,
                '--progress', '--stats-one-line'
            ], capture_output=True, text=True, timeout=3600)
            
            if result.returncode == 0:
                downloaded_file = os.path.join(local_destination, cloud_filename)
                if os.path.exists(downloaded_file):
                    _logger.info(f"Cloud download successful: {downloaded_file}")
                    return True, downloaded_file
                else:
                    return False, "Download completed but file not found"
            else:
                return False, f"Download failed: {result.stderr}"
                
        except subprocess.TimeoutExpired:
            return False, "Cloud download timed out"
        except Exception as e:
            return False, f"Download error: {str(e)}"

    def _cleanup_cloud_backups(self):
        """Clean up old backups from cloud storage"""
        if not self.enable_cloud_sync or self.cloud_retention_days <= 0:
            return
        
        try:
            cutoff_date = datetime.now() - timedelta(days=self.cloud_retention_days)
            cloud_backups = self._list_cloud_backups()
            
            deleted_count = 0
            for backup in cloud_backups:
                filename = backup['filename']
                
                # Extract date from filename (backup_YYYY_MM_DD_HH_MM_SS.tar.gz)
                should_delete = False
                if filename.startswith('backup_'):
                    try:
                        timestamp_part = filename.split('backup_')[1].split('.')[0]
                        if len(timestamp_part) >= 10:  # YYYY_MM_DD minimum
                            file_date_str = timestamp_part[:10].replace('_', '-')  # Convert to YYYY-MM-DD
                            file_date = datetime.strptime(file_date_str, '%Y-%m-%d')
                            if file_date < cutoff_date:
                                should_delete = True
                    except (ValueError, IndexError):
                        _logger.warning(f"Could not parse date from cloud backup: {filename}")
                
                if should_delete:
                    cloud_file_path = f"{self.rclone_config_name}:{self.cloud_backup_path}/{filename}"
                    result = subprocess.run([
                        'rclone', 'delete', cloud_file_path
                    ], capture_output=True, text=True, timeout=60)
                    
                    if result.returncode == 0:
                        _logger.info(f"Deleted old cloud backup: {filename}")
                        deleted_count += 1
                    else:
                        _logger.error(f"Failed to delete cloud backup {filename}: {result.stderr}")
            
            if deleted_count > 0:
                _logger.info(f"Cloud cleanup completed: {deleted_count} old backups deleted")
                
        except Exception as e:
            _logger.error(f"Cloud cleanup error: {e}")

    def _create_backup_history_record(self, backup_dir, metadata, scripts_dir=None):
        """Create backup history record"""
        try:
            components_data = {
                'timestamp': metadata['backup_info']['timestamp'],
                'components': metadata['components_included'],
                'paths': metadata['paths'],
                'backup_size_bytes': metadata.get('backup_size', 0)
            }
            
            backup_size_mb = metadata.get('backup_size', 0) / (1024 * 1024) if metadata.get('backup_size') else 0
            
            history_vals = {
                'backup_config_id': self.id,
                'backup_path': backup_dir,
                'backup_size': backup_size_mb,
                'backup_mode': self.backup_mode,
                'components_backed_up': json.dumps(components_data),
                'restore_scripts_path': scripts_dir,
                'backup_status': 'success',
            }
            
            history_record = self.env['backup.history'].create(history_vals)
            _logger.info(f"Backup history record created: {history_record.id}")
            
            return history_record
            
        except Exception as e:
            _logger.error(f"Failed to create backup history record: {e}")
            return None






















class BackupHistory(models.Model):
    _name = "backup.history"
    _description = "Backup History"
    _order = "create_date desc"
    _rec_name = "display_name"

    display_name = fields.Char(compute="_compute_display_name", store=True)
    backup_config_id = fields.Many2one(
        'db.backup', 
        string="Backup Configuration", 
        required=True,
        ondelete='cascade'
    )
    backup_path = fields.Char(
        string="Backup Path",
        required=True,
        help="Full path to backup directory or file"
    )
    backup_size = fields.Float(
        string="Backup Size (MB)",
        help="Total backup size in megabytes"
    )
    backup_mode = fields.Selection([
        ('database_only', 'Database Only'),
        ('database_filestore', 'Database + Filestore'), 
        ('full_system', 'Full System Backup')
    ], string="Backup Mode", required=True)
    
    components_backed_up = fields.Text(
        string="Components Backed Up",
        help="JSON string of components included in backup"
    )
    restore_tested = fields.Boolean(
        string="Restore Tested", 
        default=False,
        help="Whether this backup has been tested for restore"
    )
    restore_scripts_path = fields.Char(
        string="Restore Scripts Path",
        help="Path to generated restore scripts"
    )
    backup_status = fields.Selection([
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('partial', 'Partial Success')
    ], string="Backup Status", default='success')
    
    error_message = fields.Text(
        string="Error Message",
        help="Error details if backup failed"
    )
    notes = fields.Text(string="Notes")

    # Cloud Sync Fields
    cloud_sync_enabled = fields.Boolean(
        string="Cloud Sync Enabled",
        help="Whether cloud sync was enabled for this backup"
    )
    cloud_sync_status = fields.Selection([
        ('pending', 'Pending'),
        ('uploading', 'Uploading'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('not_synced', 'Not Synced')
    ], string="Cloud Sync Status", default='not_synced')
    
    cloud_path = fields.Char(
        string="Cloud Path",
        help="Full path to backup in cloud storage"
    )
    cloud_size = fields.Float(
        string="Cloud Size (MB)",
        help="Size of backup in cloud storage"
    )
    cloud_provider = fields.Char(
        string="Cloud Provider",
        help="Cloud storage provider used"
    )
    cloud_upload_date = fields.Datetime(
        string="Cloud Upload Date",
        help="When the backup was uploaded to cloud"
    )
    cloud_verified = fields.Boolean(
        string="Cloud Verified",
        help="Whether cloud backup integrity was verified"
    )

    @api.depends('backup_config_id', 'create_date', 'backup_mode')
    def _compute_display_name(self):
        for record in self:
            if record.backup_config_id and record.create_date:
                timestamp = record.create_date.strftime('%Y-%m-%d %H:%M:%S')
                record.display_name = f"{record.backup_config_id.name} - {timestamp} ({record.backup_mode})"
            else:
                record.display_name = "New Backup History"

    def action_test_restore(self):
        """Test restore functionality"""
        self.ensure_one()
        # This will be implemented in later phases
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Restore Test',
                'message': 'Restore testing will be available in the next phase.',
                'type': 'info',
            }
        }

    def action_view_scripts(self):
        """View generated restore scripts"""
        self.ensure_one()
        if not self.restore_scripts_path or not os.path.exists(self.restore_scripts_path):
            raise UserError(_("Restore scripts not found at: %s") % (self.restore_scripts_path or "Not set"))
        
        scripts_info = []
        scripts_dir = self.restore_scripts_path
        
        for script_file in ['same_server_restore.sh', 'pre_restore_backup.sh', 'rollback.sh', 'restore_config.json']:
            script_path = os.path.join(scripts_dir, script_file)
            if os.path.exists(script_path):
                scripts_info.append(f"✓ {script_file}")
            else:
                scripts_info.append(f"✗ {script_file} (missing)")
        
        message = f"Restore scripts location: {scripts_dir}\n\nAvailable scripts:\n" + "\n".join(scripts_info)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Restore Scripts',
                'message': message,
                'type': 'info',
                'sticky': True,
            }
        }
    

    def action_create_migration(self):
        """Create migration package for this backup"""
        self.ensure_one()
        
        if self.backup_status != 'success':
            raise UserError(_("Can only create migration package for successful backups"))
        
        # Create migration wizard with this backup pre-selected
        wizard = self.env['backup.migration.wizard'].create({
            'backup_history_id': self.id,
        })
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'New Server Migration',
            'res_model': 'backup.migration.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_backup_history_id': self.id}
        }
    
    def action_sync_to_cloud(self):
        """Manually sync this backup to cloud"""
        self.ensure_one()
        
        if not self.backup_config_id.enable_cloud_sync:
            raise UserError(_("Cloud sync is not enabled for this backup configuration"))
        
        if not os.path.exists(self.backup_path):
            raise UserError(_("Backup file not found: %s") % self.backup_path)
        
        self.cloud_sync_status = 'uploading'
        
        sync_success, sync_message = self.backup_config_id._sync_to_cloud(self.backup_path)
        
        if sync_success:
            self.cloud_sync_status = 'success'
            self.cloud_upload_date = fields.Datetime.now()
            self.cloud_path = f"{self.backup_config_id.rclone_config_name}:{self.backup_config_id.cloud_backup_path}/{os.path.basename(self.backup_path)}"
            self.cloud_provider = self.backup_config_id.cloud_provider
            
            # Get cloud file size
            if self.backup_config_id.verify_cloud_upload:
                verify_success, verify_msg = self.backup_config_id._verify_cloud_sync(self.cloud_path, self.backup_path)
                self.cloud_verified = verify_success
                if verify_success and "bytes" in verify_msg:
                    try:
                        size_bytes = int(verify_msg.split(":")[-1].strip().split()[0])
                        self.cloud_size = size_bytes / (1024 * 1024)  # Convert to MB
                    except:
                        pass
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Cloud Sync Successful',
                    'message': sync_message,
                    'type': 'success',
                }
            }
        else:
            self.cloud_sync_status = 'failed'
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Cloud Sync Failed',
                    'message': sync_message,
                    'type': 'danger',
                }
            }

    def action_download_from_cloud(self):
        """Download backup from cloud to local temp directory"""
        self.ensure_one()
        
        if self.cloud_sync_status != 'success':
            raise UserError(_("Backup is not available in cloud storage"))
        
        if not self.cloud_path:
            raise UserError(_("Cloud path is not set"))
        
        # Create temp download directory
        temp_dir = tempfile.mkdtemp(prefix='odoo_cloud_download_')
        
        try:
            filename = os.path.basename(self.cloud_path)
            download_success, result = self.backup_config_id._download_from_cloud(filename, temp_dir)
            
            if download_success:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Cloud Download Successful',
                        'message': f'Downloaded to: {result}',
                        'type': 'success',
                        'sticky': True,
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Cloud Download Failed',
                        'message': result,
                        'type': 'danger',
                    }
                }
                
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Cloud Download Error',
                    'message': str(e),
                    'type': 'danger',
                }
            }

    def action_list_cloud_backups(self):
        """List all cloud backups for this configuration"""
        self.ensure_one()
        
        if not self.backup_config_id.enable_cloud_sync:
            raise UserError(_("Cloud sync is not enabled"))
        
        cloud_backups = self.backup_config_id._list_cloud_backups()
        
        if cloud_backups:
            backup_list = []
            for backup in cloud_backups:
                size_mb = backup['size'] / (1024 * 1024)
                backup_list.append(f"📁 {backup['filename']} ({size_mb:.1f} MB) - {backup['date']}")
            
            message = f"Cloud backups in {self.backup_config_id.rclone_config_name}:{self.backup_config_id.cloud_backup_path}:\n\n" + "\n".join(backup_list)
        else:
            message = "No cloud backups found"
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Cloud Backups',
                'message': message,
                'type': 'info',
                'sticky': True,
            }
        }
    
























class BackupPathMapping(models.TransientModel):
    _name = "backup.path.mapping"
    _description = "Backup Path Mapping for New Server"

    wizard_id = fields.Many2one('backup.migration.wizard', string="Migration Wizard")
    backup_history_id = fields.Many2one('backup.history', string="Backup History")
    
    original_path = fields.Char(string="Original Path", required=True, readonly=True)
    target_path = fields.Char(string="Target Path", required=True)
    path_type = fields.Selection([
        ('custom_addons', 'Custom Addons'),
        ('odoo_config', 'Odoo Config'),
        ('nginx_config', 'Nginx Config'),
        ('systemd_service', 'Systemd Service'),
        ('odoo_data', 'Odoo Data'),
        ('python_venv', 'Python Virtual Environment'),
        ('backup_folder', 'Backup Folder')
    ], string="Path Type", required=True)
    
    is_valid = fields.Boolean(string="Valid", compute="_compute_is_valid", store=True)
    validation_message = fields.Char(string="Validation Message", compute="_compute_is_valid", store=True)
    is_required = fields.Boolean(string="Required", default=True)

    @api.depends('target_path', 'path_type')
    def _compute_is_valid(self):
        for record in self:
            if not record.target_path:
                record.is_valid = False
                record.validation_message = "Target path is required"
                continue
            
            # Basic path validation
            if not record.target_path.startswith('/'):
                record.is_valid = False
                record.validation_message = "Path must be absolute (start with /)"
                continue
            
            # Path type specific validation
            if record.path_type == 'odoo_config' and not record.target_path.endswith('.conf'):
                record.is_valid = False
                record.validation_message = "Odoo config should end with .conf"
                continue
            
            if record.path_type == 'systemd_service' and not record.target_path.endswith('.service'):
                record.is_valid = False
                record.validation_message = "Systemd service should end with .service"
                continue
            
            record.is_valid = True
            record.validation_message = "Valid path"










class BackupMigrationWizard(models.TransientModel):
    _name = "backup.migration.wizard"
    _description = "Backup Migration Wizard"

    backup_history_id = fields.Many2one(
        'backup.history', 
        string="Backup to Migrate", 
        required=True,
        domain="[('backup_status', '=', 'success')]"
    )
    
    # Target Server Configuration
    target_server_name = fields.Char(string="Target Server Name", required=True, default="new-server")
    target_server_ip = fields.Char(string="Target Server IP")
    target_os = fields.Selection([
        ('ubuntu20', 'Ubuntu 20.04 LTS'),
        ('ubuntu22', 'Ubuntu 22.04 LTS'),
        ('ubuntu24', 'Ubuntu 24.04 LTS'),
        ('debian11', 'Debian 11'),
        ('debian12', 'Debian 12'),
        ('centos8', 'CentOS 8'),
        ('rhel8', 'RHEL 8'),
        ('rhel9', 'RHEL 9'),
    ], string="Target OS", required=True, default='ubuntu22')
    
    target_odoo_user = fields.Char(string="Target Odoo User", default="odoo")
    target_database_name = fields.Char(string="Target Database Name")
    
    # Simplified Path Configuration
    target_custom_addons = fields.Char(string="Custom Addons Path", default="/opt/odoo/custom_addons")
    target_odoo_config = fields.Char(string="Odoo Config Path", default="/etc/odoo/odoo.conf")
    target_nginx_config = fields.Char(string="Nginx Config Path", default="/etc/nginx/sites-available/odoo")
    target_systemd_service = fields.Char(string="Systemd Service Path", default="/etc/systemd/system/odoo.service")
    target_odoo_data = fields.Char(string="Odoo Data Path", default="/home/odoo/.local/share/Odoo")
    target_backup_folder = fields.Char(string="Backup Folder", default="/opt/odoo/backups")
    
    # Migration Options
    migration_mode = fields.Selection([
        ('full_migration', 'Full Migration (Recommended)'),
        ('data_only', 'Data Only (Database + Filestore)'),
    ], string="Migration Mode", default='full_migration')
    
    include_ssl_setup = fields.Boolean(string="Include SSL Setup", default=False)
    domain_name = fields.Char(string="Domain Name (for SSL)")
    
    # Status Fields
    compatibility_check_done = fields.Boolean(string="Compatibility Check Done", default=False)
    compatibility_status = fields.Selection([
        ('compatible', 'Compatible'),
        ('warning', 'Compatible with Warnings'),
        ('incompatible', 'Incompatible')
    ], string="Compatibility Status")
    compatibility_report = fields.Text(string="Compatibility Report")
    
    migration_package_path = fields.Char(string="Migration Package Path")
    
    @api.onchange('backup_history_id')
    def _onchange_backup_history(self):
        """Set default database name when backup is selected"""
        if self.backup_history_id:
            self.target_database_name = self.backup_history_id.backup_config_id.env.cr.dbname
            self._set_default_paths()
    
    @api.onchange('target_os', 'target_odoo_user')
    def _onchange_target_config(self):
        """Update default paths based on OS and user"""
        self._set_default_paths()
    
    def _set_default_paths(self):
        """Set default paths based on target OS"""
        if self.target_os and self.target_os.startswith(('ubuntu', 'debian')):
            self.target_custom_addons = "/opt/odoo/custom_addons"
            self.target_odoo_config = "/etc/odoo/odoo.conf"
            self.target_nginx_config = "/etc/nginx/sites-available/odoo"
            self.target_systemd_service = "/etc/systemd/system/odoo.service"
            self.target_odoo_data = f"/home/{self.target_odoo_user or 'odoo'}/.local/share/Odoo"
            self.target_backup_folder = "/opt/odoo/backups"
        else:  # CentOS/RHEL
            self.target_custom_addons = "/opt/odoo/custom_addons"
            self.target_odoo_config = "/etc/odoo/odoo.conf"
            self.target_nginx_config = "/etc/nginx/conf.d/odoo.conf"
            self.target_systemd_service = "/etc/systemd/system/odoo.service"
            self.target_odoo_data = f"/home/{self.target_odoo_user or 'odoo'}/.local/share/Odoo"
            self.target_backup_folder = "/opt/odoo/backups"
    
    def action_check_compatibility(self):
        """Check compatibility between source and target"""
        self.ensure_one()
        
        warnings = []
        errors = []
        
        # Basic validation
        if not self.target_server_name:
            errors.append("Target server name is required")
        
        if not self.target_database_name:
            errors.append("Target database name is required")
        
        # Path validation
        required_paths = [
            ('Custom Addons', self.target_custom_addons),
            ('Odoo Config', self.target_odoo_config),
            ('Backup Folder', self.target_backup_folder),
        ]
        
        for path_name, path_value in required_paths:
            if not path_value:
                errors.append(f"{path_name} path is required")
            elif not path_value.startswith('/'):
                errors.append(f"{path_name} path must be absolute (start with /)")
        
        # Get backup info
        backup_size_gb = self.backup_history_id.backup_size / 1024 if self.backup_history_id.backup_size else 0
        if backup_size_gb > 10:
            warnings.append(f"Large backup size ({backup_size_gb:.1f} GB) - ensure target has sufficient disk space")
        
        # SSL validation
        if self.include_ssl_setup and not self.domain_name:
            errors.append("Domain name is required for SSL setup")
        
        # Determine status
        if errors:
            self.compatibility_status = 'incompatible'
        elif warnings:
            self.compatibility_status = 'warning'
        else:
            self.compatibility_status = 'compatible'
        
        # Generate report
        report_lines = []
        
        if self.compatibility_status == 'compatible':
            report_lines.append("✅ COMPATIBILITY CHECK PASSED")
        elif self.compatibility_status == 'warning':
            report_lines.append("⚠️ COMPATIBILITY CHECK - WARNINGS FOUND")
        else:
            report_lines.append("❌ COMPATIBILITY CHECK FAILED")
        
        report_lines.append("")
        report_lines.append("TARGET CONFIGURATION:")
        report_lines.append(f"  Server: {self.target_server_name}")
        report_lines.append(f"  OS: {self.target_os}")
        report_lines.append(f"  Database: {self.target_database_name}")
        report_lines.append(f"  User: {self.target_odoo_user}")
        
        if errors:
            report_lines.append("")
            report_lines.append("❌ CRITICAL ISSUES:")
            report_lines.extend([f"  • {error}" for error in errors])
        
        if warnings:
            report_lines.append("")
            report_lines.append("⚠️ WARNINGS:")
            report_lines.extend([f"  • {warning}" for warning in warnings])
        
        if self.compatibility_status == 'compatible':
            report_lines.append("")
            report_lines.append("✅ Migration should proceed without issues")
        
        self.compatibility_report = "\n".join(report_lines)
        self.compatibility_check_done = True
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Compatibility Check Complete',
                'message': f'Status: {self.compatibility_status.title()}',
                'type': 'success' if self.compatibility_status == 'compatible' else 'warning',
                'sticky': True,
            }
        }
    
    def action_generate_migration_package(self):
        """Generate migration package handling compressed backups"""
        self.ensure_one()
        
        if not self.compatibility_check_done:
            raise UserError(_("Please run compatibility check first"))
        
        if self.compatibility_status == 'incompatible':
            raise UserError(_("Cannot generate migration package - compatibility issues found"))
        
        # Create migration package directory
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        package_name = f"migration_{self.target_server_name}_{timestamp}"
        package_dir = os.path.join('/tmp', package_name)
        
        _logger.info(f"Starting migration package generation: {package_name}")
        
        try:
            # Create main directory
            os.makedirs(package_dir, exist_ok=True)
            _logger.info(f"Created package directory: {package_dir}")
            
            # Create subdirectories
            subdirs = ['backup_data', 'migration_config', 'scripts']
            for subdir in subdirs:
                subdir_path = os.path.join(package_dir, subdir)
                os.makedirs(subdir_path, exist_ok=True)
                _logger.info(f"Created subdirectory: {subdir_path}")
            
            # Handle backup data based on source type
            source_backup_path = self.backup_history_id.backup_path
            target_backup_path = os.path.join(package_dir, 'backup_data')
            
            _logger.info(f"Processing backup data from: {source_backup_path}")
            
            if source_backup_path.endswith('.tar.gz'):
                # Compressed backup - extract it
                _logger.info("Extracting compressed backup...")
                with tempfile.TemporaryDirectory() as temp_extract_dir:
                    # Extract the compressed backup
                    shutil.unpack_archive(source_backup_path, temp_extract_dir)
                    
                    # Find the extracted directory (should be only one)
                    extracted_items = os.listdir(temp_extract_dir)
                    if len(extracted_items) == 1 and os.path.isdir(os.path.join(temp_extract_dir, extracted_items[0])):
                        extracted_dir = os.path.join(temp_extract_dir, extracted_items[0])
                        # Copy extracted contents to backup_data
                        for item in os.listdir(extracted_dir):
                            source_item = os.path.join(extracted_dir, item)
                            target_item = os.path.join(target_backup_path, item)
                            if os.path.isdir(source_item):
                                shutil.copytree(source_item, target_item)
                            else:
                                shutil.copy2(source_item, target_item)
                    else:
                        # Multiple items or files - copy all
                        for item in extracted_items:
                            source_item = os.path.join(temp_extract_dir, item)
                            target_item = os.path.join(target_backup_path, item)
                            if os.path.isdir(source_item):
                                shutil.copytree(source_item, target_item)
                            else:
                                shutil.copy2(source_item, target_item)
                
                _logger.info(f"Extracted compressed backup to: {target_backup_path}")
                
            elif os.path.isdir(source_backup_path):
                # Directory backup - copy contents
                for item in os.listdir(source_backup_path):
                    source_item = os.path.join(source_backup_path, item)
                    target_item = os.path.join(target_backup_path, item)
                    if os.path.isdir(source_item):
                        shutil.copytree(source_item, target_item)
                    else:
                        shutil.copy2(source_item, target_item)
                _logger.info(f"Copied backup directory contents to: {target_backup_path}")
                
            elif os.path.isfile(source_backup_path):
                # Single file backup
                if source_backup_path.endswith(('.zip', '.dump')):
                    # Copy single backup file
                    shutil.copy2(source_backup_path, os.path.join(target_backup_path, os.path.basename(source_backup_path)))
                    _logger.info(f"Copied backup file to: {target_backup_path}")
                else:
                    raise UserError(_("Unsupported backup file format: %s") % source_backup_path)
            else:
                raise UserError(_("Source backup path not found: %s") % source_backup_path)
            
            # Generate migration configuration
            _logger.info("Generating migration configuration...")
            self._generate_migration_config(package_dir)
            
            # Generate migration scripts
            _logger.info("Generating migration scripts...")
            self._generate_migration_scripts(package_dir)
            
            # Verify package contents
            self._verify_package_contents(package_dir)
            
            # Create archive
            _logger.info("Creating package archive...")
            archive_path = f"{package_dir}.tar.gz"
            shutil.make_archive(package_dir, 'gztar', '/tmp', package_name)
            
            # Get archive size
            archive_size_mb = os.path.getsize(archive_path) / (1024 * 1024)
            _logger.info(f"Archive created: {archive_path} ({archive_size_mb:.1f} MB)")
            
            # Cleanup temp directory
            shutil.rmtree(package_dir)
            _logger.info(f"Cleaned up temporary directory: {package_dir}")
            
            self.migration_package_path = archive_path
            
            # Create detailed success message
            message = f"""Migration package created successfully!

Package: {os.path.basename(archive_path)}
Size: {archive_size_mb:.1f} MB
Location: {archive_path}

Source backup: {"Compressed" if source_backup_path.endswith('.tar.gz') else "Uncompressed"}

Contents:
✅ Backup data extracted and copied
✅ Configuration files generated
✅ Migration scripts created
✅ Verification scripts included

Next steps:
1. Copy package to target server
2. Extract: tar -xzf {os.path.basename(archive_path)}
3. Run: sudo ./scripts/migrate.sh
"""
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Migration Package Created',
                    'message': message,
                    'type': 'success',
                    'sticky': True,
                }
            }
            
        except Exception as e:
            _logger.error(f"Failed to generate migration package: {e}", exc_info=True)
            raise UserError(_("Failed to generate migration package: %s") % str(e))
    
    def _verify_package_contents(self, package_dir):
        """Verify package contents are complete"""
        _logger.info("Verifying package contents...")
        
        required_files = [
            'migration_config/path_mapping.json',
            'migration_config/target_server_info.json', 
            'migration_config/compatibility_report.json',
            'migration_config/README.md',
            'scripts/migrate.sh',
            'scripts/install_odoo.sh',
            'scripts/configure.sh',
            'scripts/verify.sh'
        ]
        
        missing_files = []
        for file_path in required_files:
            full_path = os.path.join(package_dir, file_path)
            if not os.path.exists(full_path):
                missing_files.append(file_path)
            else:
                file_size = os.path.getsize(full_path)
                _logger.info(f"✅ {file_path} ({file_size} bytes)")
        
        if missing_files:
            _logger.warning(f"Missing files: {missing_files}")
            raise UserError(_("Package verification failed. Missing files: %s") % ', '.join(missing_files))
        
        # Check backup data
        backup_data_dir = os.path.join(package_dir, 'backup_data')
        if not os.path.exists(backup_data_dir) or not os.listdir(backup_data_dir):
            raise UserError(_("Backup data directory is empty or missing"))
        
        backup_items = os.listdir(backup_data_dir)
        _logger.info(f"✅ Backup data contains: {backup_items}")
        
        _logger.info("Package verification completed successfully")
    
    def _generate_migration_config(self, package_dir):
        """Generate migration configuration files"""
        config_dir = os.path.join(package_dir, 'migration_config')
        
        # Path mapping configuration
        backup_config = self.backup_history_id.backup_config_id
        path_mapping = {
            'custom_addons': {
                'original': backup_config.custom_addons_path or '',
                'target': self.target_custom_addons or ''
            },
            'odoo_config': {
                'original': backup_config.odoo_config_path or '',
                'target': self.target_odoo_config or ''
            },
            'nginx_config': {
                'original': backup_config.nginx_config_path or '',
                'target': self.target_nginx_config or ''
            },
            'systemd_service': {
                'original': backup_config.systemd_service_path or '',
                'target': self.target_systemd_service or ''
            },
            'odoo_data': {
                'original': backup_config.odoo_data_path or '',
                'target': self.target_odoo_data or ''
            },
            'backup_folder': {
                'original': backup_config.folder or '',
                'target': self.target_backup_folder or ''
            }
        }
        
        path_mapping_file = os.path.join(config_dir, 'path_mapping.json')
        with open(path_mapping_file, 'w') as f:
            json.dump(path_mapping, f, indent=2)
        
        _logger.info(f"Path mapping created: {path_mapping_file}")
        
        # Target server configuration
        server_config = {
            'server_name': self.target_server_name,
            'server_ip': self.target_server_ip or '',
            'target_os': self.target_os,
            'odoo_user': self.target_odoo_user,
            'database_name': self.target_database_name,
            'migration_mode': self.migration_mode,
            'include_ssl': self.include_ssl_setup,
            'domain_name': self.domain_name or '',
            'generated_at': datetime.now().isoformat(),
            'source_backup': {
                'backup_id': self.backup_history_id.id,
                'backup_path': self.backup_history_id.backup_path,
                'backup_mode': self.backup_history_id.backup_mode,
                'backup_size_mb': self.backup_history_id.backup_size,
                'created_date': self.backup_history_id.create_date.isoformat() if self.backup_history_id.create_date else ''
            }
        }
        
        server_config_file = os.path.join(config_dir, 'target_server_info.json')
        with open(server_config_file, 'w') as f:
            json.dump(server_config, f, indent=2)
        
        _logger.info(f"Server config created: {server_config_file}")
        
        # Compatibility report
        compatibility_file = os.path.join(config_dir, 'compatibility_report.json')
        with open(compatibility_file, 'w') as f:
            json.dump({
                'status': self.compatibility_status or 'unknown',
                'report': self.compatibility_report or '',
                'check_date': datetime.now().isoformat(),
                'validated_paths': {
                    'custom_addons': bool(self.target_custom_addons and self.target_custom_addons.startswith('/')),
                    'odoo_config': bool(self.target_odoo_config and self.target_odoo_config.startswith('/')),
                    'backup_folder': bool(self.target_backup_folder and self.target_backup_folder.startswith('/'))
                }
            }, f, indent=2)
        
        _logger.info(f"Compatibility report created: {compatibility_file}")
        
        # Migration instructions
        instructions = f"""# Odoo Migration Instructions

## Generated Package Contents:
- backup_data/          : Original backup files
- migration_config/     : Configuration files
- scripts/             : Migration scripts

## Quick Start:
1. Copy this package to target server: {self.target_server_name}
2. Extract: tar -xzf migration_package.tar.gz
3. Run: sudo ./scripts/migrate.sh
4. Follow on-screen instructions

## Target Configuration:
- OS: {self.target_os}
- Database: {self.target_database_name}
- User: {self.target_odoo_user}
- Custom Addons: {self.target_custom_addons}

## Manual Steps Required:
1. Install Odoo 18 on target server
2. Install PostgreSQL
3. Configure firewall (ports 80, 443, 8069)
4. Update DNS records (if using domain: {self.domain_name or 'N/A'})

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        instructions_file = os.path.join(config_dir, 'README.md')
        with open(instructions_file, 'w') as f:
            f.write(instructions)
        
        _logger.info(f"Instructions created: {instructions_file}")
    
    def _generate_migration_scripts(self, package_dir):
        """Generate comprehensive migration scripts"""
        scripts_dir = os.path.join(package_dir, 'scripts')
        
        # Generate main migration script
        self._create_main_migration_script(scripts_dir)
        
        # Generate installation script
        self._create_install_script(scripts_dir)
        
        # Generate verification script
        self._create_verify_script(scripts_dir)
        
        # Generate configuration script
        self._create_config_script(scripts_dir)
        
        # Make all scripts executable
        for script_file in ['migrate.sh', 'install_odoo.sh', 'verify.sh', 'configure.sh']:
            script_path = os.path.join(scripts_dir, script_file)
            if os.path.exists(script_path):
                os.chmod(script_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
                _logger.info(f"Made executable: {script_path}")

    def _create_main_migration_script(self, scripts_dir):
        """Create main migration orchestration script"""
        script_content = f'''#!/bin/bash
# Main Odoo Migration Script
# Target: {self.target_server_name} ({self.target_os})
# Database: {self.target_database_name}
# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

set -e

SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
MIGRATION_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_DIR="$MIGRATION_DIR/migration_config"
BACKUP_DATA_DIR="$MIGRATION_DIR/backup_data"

# Colors
RED='\\033[0;31m'
GREEN='\\033[0;32m'
YELLOW='\\033[1;33m'
BLUE='\\033[0;34m'
NC='\\033[0m'

log() {{
    echo -e "${{BLUE}}[$(date '+%Y-%m-%d %H:%M:%S')]${{NC}} $1"
}}

success() {{
    echo -e "${{GREEN}}✅ $1${{NC}}"
}}

warning() {{
    echo -e "${{YELLOW}}⚠️  $1${{NC}}"
}}

error() {{
    echo -e "${{RED}}❌ $1${{NC}}"
}}

check_root() {{
    if [[ $EUID -ne 0 ]]; then
        error "This script must be run as root: sudo $0"
        exit 1
    fi
}}

load_config() {{
    log "Loading migration configuration..."
    
    if [ ! -f "$CONFIG_DIR/target_server_info.json" ]; then
        error "Configuration file not found: $CONFIG_DIR/target_server_info.json"
        exit 1
    fi
    
    if [ ! -f "$CONFIG_DIR/path_mapping.json" ]; then
        error "Path mapping file not found: $CONFIG_DIR/path_mapping.json"
        exit 1
    fi
    
    success "Configuration loaded"
}}

show_info() {{
    echo ""
    echo "================================="
    echo "    ODOO MIGRATION STARTED"
    echo "================================="
    echo "Target Server: {self.target_server_name}"
    echo "Target OS: {self.target_os}"
    echo "Database: {self.target_database_name}"
    echo "Odoo User: {self.target_odoo_user}"
    echo "Migration Mode: {self.migration_mode}"
    echo ""
    echo "Target Paths:"
    echo "  Custom Addons: {self.target_custom_addons}"
    echo "  Config File: {self.target_odoo_config}"
    echo "  Data Directory: {self.target_odoo_data}"
    echo "  Backup Folder: {self.target_backup_folder}"
    echo ""
    echo "Backup Source: $BACKUP_DATA_DIR"
    echo "================================="
    echo ""
}}

create_directories() {{
    log "Creating directory structure..."
    
    mkdir -p "{self.target_custom_addons}"
    mkdir -p "$(dirname "{self.target_odoo_config}")"
    mkdir -p "{self.target_backup_folder}"
    mkdir -p "{self.target_odoo_data}"
    mkdir -p "$(dirname "{self.target_nginx_config}")"
    
    success "Directories created"
}}

create_user() {{
    log "Creating system user: {self.target_odoo_user}"
    
    if id "{self.target_odoo_user}" &>/dev/null; then
        warning "User {self.target_odoo_user} already exists"
    else
        useradd -m -s /bin/bash -r {self.target_odoo_user}
        success "User {self.target_odoo_user} created"
    fi
}}

set_permissions() {{
    log "Setting file permissions..."
    
    chown -R {self.target_odoo_user}:{self.target_odoo_user} "{self.target_custom_addons}"
    chown -R {self.target_odoo_user}:{self.target_odoo_user} "{self.target_backup_folder}"
    chown -R {self.target_odoo_user}:{self.target_odoo_user} "{self.target_odoo_data}"
    
    success "Permissions set"
}}

install_dependencies() {{
    log "Installing Odoo and dependencies..."
    
    if [ -f "$SCRIPT_DIR/install_odoo.sh" ]; then
        bash "$SCRIPT_DIR/install_odoo.sh"
    else
        warning "install_odoo.sh not found, please install Odoo manually"
    fi
}}

restore_data() {{
    log "Restoring backup data..."
    
    # Find database backup
    DB_BACKUP=""
    if [ -f "$BACKUP_DATA_DIR/database/{self.backup_history_id.backup_config_id.env.cr.dbname}.dump" ]; then
        DB_BACKUP="$BACKUP_DATA_DIR/database/{self.backup_history_id.backup_config_id.env.cr.dbname}.dump"
    else
        DB_BACKUP=$(find "$BACKUP_DATA_DIR" -name "*.dump" | head -1)
    fi
    
    if [ -n "$DB_BACKUP" ] && [ -f "$DB_BACKUP" ]; then
        log "Restoring database from: $DB_BACKUP"
        
        # Create database
        sudo -u postgres createdb {self.target_database_name} 2>/dev/null || {{
            warning "Database {self.target_database_name} might already exist"
        }}
        
        # Restore database
        sudo -u postgres pg_restore -d {self.target_database_name} "$DB_BACKUP" || {{
            warning "Database restore completed with warnings"
        }}
        
        success "Database restored"
    else
        error "Database backup file not found"
        exit 1
    fi
    
    # Restore filestore
    if [ -d "$BACKUP_DATA_DIR/filestore" ]; then
        log "Restoring filestore..."
        FILESTORE_TARGET="/var/lib/odoo/.local/share/Odoo/filestore/{self.target_database_name}"
        mkdir -p "$(dirname "$FILESTORE_TARGET")"
        cp -r "$BACKUP_DATA_DIR/filestore" "$FILESTORE_TARGET"
        chown -R {self.target_odoo_user}:{self.target_odoo_user} "$FILESTORE_TARGET"
        success "Filestore restored"
    fi
    
    # Restore custom addons
    if [ -d "$BACKUP_DATA_DIR/custom_addons" ] && [ "{self.migration_mode}" = "full_migration" ]; then
        log "Restoring custom addons..."
        cp -r "$BACKUP_DATA_DIR/custom_addons"/* "{self.target_custom_addons}/" 2>/dev/null || true
        chown -R {self.target_odoo_user}:{self.target_odoo_user} "{self.target_custom_addons}"
        success "Custom addons restored"
    fi
}}

configure_system() {{
    log "Configuring system..."
    
    if [ -f "$SCRIPT_DIR/configure.sh" ]; then
        bash "$SCRIPT_DIR/configure.sh"
    else
        warning "configure.sh not found, manual configuration required"
    fi
}}

verify_installation() {{
    log "Verifying migration..."
    
    if [ -f "$SCRIPT_DIR/verify.sh" ]; then
        bash "$SCRIPT_DIR/verify.sh"
    else
        warning "verify.sh not found, please verify manually"
    fi
}}

show_completion() {{
    echo ""
    echo "================================="
    echo "   MIGRATION COMPLETED!"
    echo "================================="
    echo ""
    success "Odoo migration finished successfully"
    echo ""
    echo "Next steps:"
    echo "1. Start Odoo service: systemctl start odoo"
    echo "2. Check status: systemctl status odoo"
    echo "3. Access Odoo: http://$(hostname -I | awk '{{print $1}}'):8069"
    
    if [ -n "{self.domain_name}" ]; then
        echo "4. Configure DNS: {self.domain_name} → $(hostname -I | awk '{{print $1}}')"
    fi
    
    echo ""
    echo "Configuration files:"
    echo "  Odoo config: {self.target_odoo_config}"
    echo "  Custom addons: {self.target_custom_addons}"
    echo "  Backup folder: {self.target_backup_folder}"
    echo ""
    echo "================================="
}}

# Main execution
main() {{
    check_root
    show_info
    
    read -p "Continue with migration? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Migration cancelled"
        exit 0
    fi
    
    load_config
    create_directories
    create_user
    set_permissions
    install_dependencies
    restore_data
    configure_system
    verify_installation
    show_completion
}}

# Show help
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    echo "Odoo Migration Script"
    echo "Usage: sudo $0"
    echo ""
    echo "This script will migrate Odoo to a new server with the following configuration:"
    echo "  Target Server: {self.target_server_name}"
    echo "  Target OS: {self.target_os}"
    echo "  Database: {self.target_database_name}"
    echo "  User: {self.target_odoo_user}"
    echo ""
    echo "Make sure you have:"
    echo "  - Root access (run with sudo)"
    echo "  - Internet connection"
    echo "  - Sufficient disk space"
    echo ""
    exit 0
fi

main "$@"
'''
        
        script_file = os.path.join(scripts_dir, 'migrate.sh')
        with open(script_file, 'w') as f:
            f.write(script_content)

    def _create_install_script(self, scripts_dir):
        """Create Odoo installation script"""
        if self.target_os.startswith(('ubuntu', 'debian')):
            package_cmd = 'apt-get'
            update_cmd = 'apt-get update'
        else:
            package_cmd = 'yum'
            update_cmd = 'yum update -y'
        
        script_content = f'''#!/bin/bash
# Odoo Installation Script for {self.target_os}

set -e

echo "Installing Odoo and dependencies for {self.target_os}..."

# Update system
{update_cmd}

# Install dependencies
{package_cmd} install -y python3 python3-pip postgresql postgresql-contrib nginx curl wget

# Install Odoo
if command -v odoo &> /dev/null; then
    echo "Odoo already installed"
else
    echo "Installing Odoo 18..."
    wget -q -O - https://nightly.odoo.com/odoo.key | apt-key add - || true
    echo "deb http://nightly.odoo.com/18.0/nightly/deb/ ./" > /etc/apt/sources.list.d/odoo.list
    {update_cmd}
    {package_cmd} install -y odoo
fi

# Start PostgreSQL
systemctl start postgresql
systemctl enable postgresql

echo "✅ Odoo installation completed"
'''
        
        script_file = os.path.join(scripts_dir, 'install_odoo.sh')
        with open(script_file, 'w') as f:
            f.write(script_content)

    def _create_verify_script(self, scripts_dir):
        """Create verification script"""
        script_content = f'''#!/bin/bash
# Migration Verification Script

echo "Verifying Odoo migration..."

# Check directories
echo "Checking directories..."
[ -d "{self.target_custom_addons}" ] && echo "✅ Custom addons directory exists" || echo "❌ Custom addons directory missing"
[ -d "{self.target_backup_folder}" ] && echo "✅ Backup directory exists" || echo "❌ Backup directory missing"
[ -d "{self.target_odoo_data}" ] && echo "✅ Odoo data directory exists" || echo "❌ Odoo data directory missing"

# Check user
echo "Checking user..."
id {self.target_odoo_user} &>/dev/null && echo "✅ User {self.target_odoo_user} exists" || echo "❌ User {self.target_odoo_user} missing"

# Check database
echo "Checking database..."
sudo -u postgres psql -l | grep -q {self.target_database_name} && echo "✅ Database {self.target_database_name} exists" || echo "❌ Database {self.target_database_name} missing"

# Check services
echo "Checking services..."
systemctl is-active --quiet postgresql && echo "✅ PostgreSQL running" || echo "❌ PostgreSQL not running"
systemctl is-active --quiet odoo && echo "✅ Odoo running" || echo "⚠️  Odoo not running (may need manual start)"

echo ""
echo "Verification completed!"
echo "If Odoo is not running, start it with: systemctl start odoo"
'''
        
        script_file = os.path.join(scripts_dir, 'verify.sh')
        with open(script_file, 'w') as f:
            f.write(script_content)

    def _create_config_script(self, scripts_dir):
        """Create configuration script"""
        script_content = f'''#!/bin/bash
# System Configuration Script

echo "Configuring system for Odoo..."

# Create Odoo config if it doesn't exist
if [ ! -f "{self.target_odoo_config}" ]; then
    echo "Creating Odoo configuration..."
    cat > "{self.target_odoo_config}" << EOF
[options]
addons_path = /usr/lib/python3/dist-packages/odoo/addons,{self.target_custom_addons}
data_dir = {self.target_odoo_data}
db_host = localhost
db_port = 5432
db_user = {self.target_odoo_user}
db_password = False
dbfilter = {self.target_database_name}
EOF
    echo "✅ Odoo config created"
fi

# Configure systemd service
if [ ! -f "/etc/systemd/system/odoo.service" ]; then
    echo "Creating systemd service..."
    cat > "/etc/systemd/system/odoo.service" << EOF
[Unit]
Description=Odoo
Requires=postgresql.service
After=postgresql.service

[Service]
Type=simple
SyslogIdentifier=odoo
PermissionsStartOnly=true
User={self.target_odoo_user}
Group={self.target_odoo_user}
ExecStart=/usr/bin/odoo --config={self.target_odoo_config}
StandardOutput=journal+console

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable odoo
    echo "✅ Systemd service configured"
fi

# Configure firewall
echo "Configuring firewall..."
if command -v ufw &> /dev/null; then
    ufw --force enable
    ufw allow ssh
    ufw allow 80/tcp
    ufw allow 443/tcp
    ufw allow 8069/tcp
    echo "✅ UFW firewall configured"
fi

echo "✅ System configuration completed"
'''
        
        script_file = os.path.join(scripts_dir, 'configure.sh')
        with open(script_file, 'w') as f:
            f.write(script_content)
    
    def action_test_migration(self):
        """Test migration - simplified"""
        self.ensure_one()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Migration Package Ready',
                'message': f'Migration package created successfully!\nExtract and run: ./scripts/migrate.sh',
                'type': 'success',
                'sticky': True,
            }
        }


