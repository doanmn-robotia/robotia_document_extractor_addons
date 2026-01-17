/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";

export class AITab extends Component {
    static template = "robotia_document_extractor.SettingsAITab";
    static props = {
        onDirtyChange: { type: Function, optional: true },
        onSaveRequest: { type: Function, optional: true },
        onCancelRequest: { type: Function, optional: true },
    };

    setup() {
        this.notification = useService("notification");

        this.state = useState({
            loading: true,
            saving: false,
            dirty: false,
            originalValues: {},

            // AI Engine Configuration
            gemini_api_key: '',
            llama_cloud_api_key: '',
            gemini_model: 'gemini-2.5-flash',
            gemini_temperature: 0.0,
            gemini_top_p: 0.95,
            gemini_top_k: 0,
            gemini_max_output_tokens: 65536,
            gemini_max_retries: 3,

            // Batch Extraction Configuration
            batch_size_min: 3,
            batch_size_max: 7,
            batch_image_dpi: 200,

            // Google Drive Integration
            google_drive_enabled: false,
            google_drive_configured: false,
            google_drive_service_account_email: 'Not configured',
            google_drive_max_file_size_mb: 30,
            google_drive_form01_folder_id: '',
            google_drive_form02_folder_id: '',
            google_drive_processed_folder_id: '',
            google_drive_auto_extraction_enabled: false,
            google_drive_cron_interval_number: 30,
            google_drive_cron_interval_type: 'minutes',
        });

        onWillStart(async () => {
            await this.loadSettings();

            // Register save and cancel methods with parent
            if (this.props.onSaveRequest) {
                this.props.onSaveRequest(() => this.saveSettings());
            }
            if (this.props.onCancelRequest) {
                this.props.onCancelRequest(() => this.reloadSettings());
            }
        });
    }

    async loadSettings() {
        try {
            this.state.loading = true;
            const data = await rpc('/document_extractor/settings/ai/load');

            if (data.error) {
                throw new Error(data.message);
            }

            // Update state with loaded data
            Object.assign(this.state, data);

            // Store original values for Cancel functionality
            this.state.originalValues = { ...data };
            this.state.loading = false;
            this.state.dirty = false;

        } catch (error) {
            this.notification.add(error.message || _t("Failed to load settings"), {
                type: "danger",
                title: _t("Load Error")
            });
            this.state.loading = false;
        }
    }

    async saveSettings() {
        if (this.state.saving) return;

        try {
            this.state.saving = true;

            // Extract values to save
            const values = {
                // AI Engine
                gemini_api_key: this.state.gemini_api_key,
                llama_cloud_api_key: this.state.llama_cloud_api_key,
                gemini_model: this.state.gemini_model,
                gemini_temperature: parseFloat(this.state.gemini_temperature),
                gemini_top_p: parseFloat(this.state.gemini_top_p),
                gemini_top_k: parseInt(this.state.gemini_top_k),
                gemini_max_output_tokens: parseInt(this.state.gemini_max_output_tokens),
                gemini_max_retries: parseInt(this.state.gemini_max_retries),

                // Batch Extraction
                batch_size_min: parseInt(this.state.batch_size_min),
                batch_size_max: parseInt(this.state.batch_size_max),
                batch_image_dpi: parseInt(this.state.batch_image_dpi),

                // Google Drive
                google_drive_enabled: this.state.google_drive_enabled,
                google_drive_max_file_size_mb: parseInt(this.state.google_drive_max_file_size_mb),
                google_drive_form01_folder_id: this.state.google_drive_form01_folder_id,
                google_drive_form02_folder_id: this.state.google_drive_form02_folder_id,
                google_drive_processed_folder_id: this.state.google_drive_processed_folder_id,
                google_drive_auto_extraction_enabled: this.state.google_drive_auto_extraction_enabled,
                google_drive_cron_interval_number: parseInt(this.state.google_drive_cron_interval_number),
                google_drive_cron_interval_type: this.state.google_drive_cron_interval_type,
            };

            const result = await rpc('/document_extractor/settings/ai/save', { values });

            if (result.error) {
                throw new Error(result.message);
            }

            // Update original values after successful save
            this.state.originalValues = { ...values };
            this.state.dirty = false;
            this.props.onDirtyChange?.(false);

            this.notification.add(_t("Settings saved successfully"), {
                type: "success",
                title: _t("Success")
            });

        } catch (error) {
            this.notification.add(error.message || _t("Failed to save settings"), {
                type: "danger",
                title: _t("Save Error")
            });
        } finally {
            this.state.saving = false;
        }
    }

    reloadSettings() {
        // Revert to original values
        Object.assign(this.state, this.state.originalValues);
        this.state.dirty = false;
        this.props.onDirtyChange?.(false);
    }

    onFieldChange() {
        // Mark as dirty when any field changes
        this.state.dirty = true;
        this.props.onDirtyChange?.(true);
    }

    async testGoogleDriveConnection() {
        try {
            const result = await rpc('/document_extractor/settings/test_drive');

            if (result.error) {
                throw new Error(result.message);
            }

            this.notification.add(result.message, {
                type: "success",
                title: _t("Connection Successful")
            });

        } catch (error) {
            this.notification.add(error.message || _t("Connection test failed"), {
                type: "danger",
                title: _t("Connection Failed")
            });
        }
    }

    async clearGoogleDriveConfig() {
        if (!confirm(_t("Are you sure you want to clear all Google Drive configuration? This action cannot be undone."))) {
            return;
        }

        try {
            const result = await rpc('/document_extractor/settings/clear_drive_config');

            if (result.error) {
                throw new Error(result.message);
            }

            // Clear Drive fields in UI
            this.state.google_drive_configured = false;
            this.state.google_drive_service_account_email = 'Not configured';
            this.state.google_drive_form01_folder_id = '';
            this.state.google_drive_form02_folder_id = '';
            this.state.google_drive_processed_folder_id = '';

            this.onFieldChange();

            this.notification.add(result.message, {
                type: "info",
                title: _t("Configuration Cleared")
            });

        } catch (error) {
            this.notification.add(error.message || _t("Failed to clear configuration"), {
                type: "danger",
                title: _t("Clear Failed")
            });
        }
    }

    async handleServiceAccountUpload(ev) {
        const file = ev.target.files[0];
        if (!file) return;

        // Validate file type
        if (!file.name.endsWith('.json')) {
            this.notification.add(_t("Please select a valid JSON file"), {
                type: "danger",
                title: _t("Invalid File")
            });
            return;
        }

        try {
            // Read file content
            const fileContent = await this.readFileAsText(file);

            // Upload to server for validation and storage
            const result = await rpc('/document_extractor/settings/upload_service_account', {
                json_content: fileContent
            });

            if (result.error) {
                throw new Error(result.message);
            }

            // Update state with new service account info
            this.state.google_drive_configured = true;
            this.state.google_drive_service_account_email = result.service_account_email;
            this.onFieldChange();

            this.notification.add(result.message, {
                type: "success",
                title: _t("Success")
            });

            // Clear file input
            ev.target.value = '';

        } catch (error) {
            this.notification.add(error.message || _t("Failed to upload service account"), {
                type: "danger",
                title: _t("Upload Failed")
            });
            // Clear file input on error
            ev.target.value = '';
        }
    }

    readFileAsText(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = (e) => resolve(e.target.result);
            reader.onerror = (e) => reject(new Error('Failed to read file'));
            reader.readAsText(file);
        });
    }

    get geminiModelOptions() {
        return [
            { value: 'gemini-3.0-flash', label: _t('Gemini 3.0 Flash') },
            { value: 'gemini-3.0-pro', label: _t('Gemini 3.0 Pro') },
            { value: 'gemini-2.5-flash', label: _t('Gemini 2.5 Flash (Recommended)') },
            { value: 'gemini-2.5-pro', label: _t('Gemini 2.5 Pro') },
            { value: 'gemini-2.0-flash-exp', label: _t('Gemini 2.0 Flash Experimental') },
        ];
    }

    get cronIntervalTypeOptions() {
        return [
            { value: 'minutes', label: _t('Minutes') },
            { value: 'hours', label: _t('Hours') },
            { value: 'days', label: _t('Days') },
            { value: 'weeks', label: _t('Weeks') },
            { value: 'months', label: _t('Months') },
        ];
    }
}
