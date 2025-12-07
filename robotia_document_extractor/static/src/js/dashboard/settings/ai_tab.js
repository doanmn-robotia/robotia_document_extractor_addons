/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { View } from "@web/views/view";

export class AITab extends Component {
    static template = "robotia_document_extractor.SettingsAITab";
    static components = { View };

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            viewId: null,
            loading: true
        });

        onWillStart(async () => {
            // Get the view ID for our standalone settings form
            const views = await this.orm.searchRead(
                "ir.ui.view",
                [["model", "=", "res.config.settings"],
                 ["name", "=", "document.extractor.config.form.standalone"]],
                ["id"]
            );

            if (views.length > 0) {
                this.state.viewId = views[0].id;
            }

            this.state.loading = false;
        });
    }

    get viewProps() {
        return {
            resModel: "res.config.settings",
            type: "form",
            viewId: this.state.viewId,
            mode: "edit",
            context: {
                module: "robotia_document_extractor"
            }
        };
    }
}
