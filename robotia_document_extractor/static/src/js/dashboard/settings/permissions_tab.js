/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class PermissionsTab extends Component {
    static template = "robotia_document_extractor.SettingsPermissionsTab";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            groups: [],
            accessRights: [],
            loading: true
        });

        onWillStart(async () => {
            await this.loadGroupsAndPermissions();
            this.state.loading = false;
        });
    }

    async loadGroupsAndPermissions() {
        // Load Document Extractor groups
        this.state.groups = await this.orm.searchRead(
            "res.groups",
            [["category_id.name", "=", "Document Extractor"]],
            ["id", "name", "comment"]
        );

        // Load model access rights for these groups
        if (this.state.groups.length > 0) {
            const groupIds = this.state.groups.map(g => g.id);
            this.state.accessRights = await this.orm.searchRead(
                "ir.model.access",
                [["group_id", "in", groupIds]],
                ["id", "name", "model_id", "group_id", "perm_read", "perm_write", "perm_create", "perm_unlink"]
            );
        }
    }

    openGroupsSettings() {
        this.action.doAction({
            name: "Access Rights",
            type: 'ir.actions.act_window',
            res_model: 'res.groups',
            views: [[false, 'list'], [false, 'form']],
            target: 'current',
            domain: [["category_id.name", "=", "Document Extractor"]]
        });
    }

    openGroupForm(groupId) {
        // Click on group card opens group form view
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'res.groups',
            res_id: groupId,
            views: [[false, 'form']],
            view_mode: 'form',
            target: 'current'
        });
    }

    getAccessRightsForGroup(groupId) {
        return this.state.accessRights.filter(ar => ar.group_id[0] === groupId);
    }
}
