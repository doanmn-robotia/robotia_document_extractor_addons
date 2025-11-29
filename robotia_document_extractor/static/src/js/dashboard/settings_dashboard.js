/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { UsersTab } from "./settings/users_tab";
import { PermissionsTab } from "./settings/permissions_tab";
import { AITab } from "./settings/ai_tab";
import { OCRTab } from "./settings/ocr_tab";
import { BackupTab } from "./settings/backup_tab";
import { LogsTab } from "./settings/logs_tab";

export class SettingsDashboard extends Component {
    static template = "robotia_document_extractor.SettingsDashboard";
    static components = { UsersTab, PermissionsTab, AITab, OCRTab, BackupTab, LogsTab };

    setup() {
        this.state = useState({
            activeTab: 'USERS'
        });
    }

    switchTab(tabName) {
        this.state.activeTab = tabName;
    }
}

registry.category("actions").add("document_extractor.settings_dashboard", SettingsDashboard);
