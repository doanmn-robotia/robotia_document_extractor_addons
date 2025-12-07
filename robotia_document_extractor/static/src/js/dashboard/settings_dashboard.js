/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { UsersTab } from "./settings/users_tab";
import { AITab } from "./settings/ai_tab";
import { BackupTab } from "./settings/backup_tab";
import { LogsTab } from "./settings/logs_tab";
// OCRTab and PermissionsTab REMOVED

export class SettingsDashboard extends Component {
    static template = "robotia_document_extractor.SettingsDashboard";
    static components = { UsersTab, AITab, BackupTab, LogsTab };

    setup() {
        this.state = useState({
            activeTab: null,
            isSystemAdmin: false,
            isDocAdmin: false,
            loading: true
        });

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
            this.state.activeTab = tabName;
        }
    }
}

registry.category("actions").add("document_extractor.settings_dashboard", SettingsDashboard);
