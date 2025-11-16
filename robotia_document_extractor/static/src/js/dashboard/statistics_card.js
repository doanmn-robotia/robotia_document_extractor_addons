/** @odoo-module **/

import { Component } from "@odoo/owl";


export class StatisticsCard extends Component {
    static template = "robotia_document_extractor.StatisticsCard";
    static props = {
        title: { type: String },
        count: { type: Number },
        docType: { type: String },
        onClick: { type: Function },
        disabled: { type: Boolean, optional: true }
    };

    handleClick() {
        // Don't trigger click if disabled
        if (this.props.disabled) {
            return;
        }
        this.props.onClick(this.props.docType);
    }
}
