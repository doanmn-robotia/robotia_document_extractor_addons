/** @odoo-module **/

import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class AITab extends Component {
    static template = "robotia_document_extractor.SettingsAITab";

    setup() {
        this.action = useService("action");
    }

    openAISettings() {
        this.action.doAction({
            name: "Document Extractor Settings",
            type: 'ir.actions.act_window',
            res_model: 'res.config.settings',
            views: [[false, 'form']],
            target: 'current'
        });
    }
}
