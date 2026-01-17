/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { UsersTab } from "./settings/users_tab";
import { AITab } from "./settings/ai_tab";
import { BackupTab } from "./settings/backup_tab";
import { LogsTab } from "./settings/logs_tab";
import { _t } from "@web/core/l10n/translation";

export class SettingsDashboard extends Component {
    static template = "robotia_document_extractor.SettingsDashboard";
    static components = { UsersTab, AITab, BackupTab, LogsTab };

    setup() {
        this.state = useState({
            activeTab: null,
            isSystemAdmin: false,
            isDocAdmin: false,
            loading: true,
            hasChanges: false  // Track if AI tab has unsaved changes
        });

        // Store callbacks from AITab
        this.aiTabCallbacks = {
            save: null,
            cancel: null
        };

        onWillStart(async () => {
            await this.loadUserPermissions();
            this.state.activeTab = this.getDefaultTab();
            this.state.loading = false;
        });
    }

    async loadUserPermissions() {
        // Use user.hasGroup() method instead of webSearchRead
        this.state.isSystemAdmin = await user.hasGroup("base.group_system");
        this.state.isDocAdmin = await user.hasGroup("robotia_document_extractor.group_document_extractor_admin");
    }

    getDefaultTab() {
        if (this.canViewTab('USERS')) return 'USERS';
        if (this.canViewTab('AI')) return 'AI';
        return 'LOGS';
    }

    canViewTab(tabName) {
        const { isSystemAdmin, isDocAdmin } = this.state;

        switch(tabName) {
            case 'USERS':
            case 'AI':
            case 'BACKUP':
                return isSystemAdmin || isDocAdmin;
            case 'LOGS':
                return true;
            default:
                return false;
        }
    }

    switchTab(tabName) {
        if (this.canViewTab(tabName)) {
            // Warn if leaving AI tab with unsaved changes
            if (this.state.activeTab === 'AI' && this.state.hasChanges) {
                const confirmed = confirm('You have unsaved changes. Are you sure you want to leave this page?');
                if (!confirmed) {
                    return;
                }
                this.state.hasChanges = false;
            }
            this.state.activeTab = tabName;
        }
    }

    handleDirtyChange(isDirty) {
        // Called by AITab when dirty state changes
        this.state.hasChanges = isDirty;
    }

    handleSaveRequest(saveCallback) {
        // AITab registers its save method
        this.aiTabCallbacks.save = saveCallback;
    }

    handleCancelRequest(cancelCallback) {
        // AITab registers its cancel method
        this.aiTabCallbacks.cancel = cancelCallback;
    }

    async handleSave() {
        if (this.state.activeTab === 'AI' && this.aiTabCallbacks.save) {
            // Trigger save on AITab component
            await this.aiTabCallbacks.save();
        }
    }

    handleCancel() {
        if (this.state.activeTab === 'AI' && this.aiTabCallbacks.cancel) {
            // Trigger cancel on AITab component
            this.aiTabCallbacks.cancel();
        }
    }

    getTabClass(tabName) {
        return this.state.activeTab === tabName
            ? 'settings-tab-button settings-tab-active'
            : 'settings-tab-button';
    }

    get tabs() {
        const allTabs = [
            { name: 'USERS', label: _t('Users'), icon: 'fa-users' },
            { name: 'AI', label: _t('AI Configuration'), icon: 'fa-magic' },
            { name: 'BACKUP', label: _t('Backup'), icon: 'fa-database' },
            { name: 'LOGS', label: _t('Device Logs'), icon: 'fa-history' },
        ];

        // Filter tabs based on permissions
        return allTabs.filter(tab => this.canViewTab(tab.name));
    }
}

registry.category("actions").add("document_extractor.settings_dashboard", SettingsDashboard);
