/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

export class ValidationStatsWidget extends Component {
    static template = "robotia_document_extractor.ValidationStatsWidget";
    static components = {};
    static props = {
        ...standardWidgetProps
    };

    get stats() {
        return {
            clean: this.props.record.data.stat_clean || 0,
            autoFixed: this.props.record.data.stat_auto_fixed || 0,
            needsReview: this.props.record.data.stat_needs_review || 0
        };
    }
}

registry.category("view_widgets").add("validation_stats_widget", {
    component: ValidationStatsWidget,
});
