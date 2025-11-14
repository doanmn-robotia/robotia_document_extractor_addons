/** @odoo-module **/

import { Component } from "@odoo/owl";


export class StatisticsCard extends Component {
    static template = "robotia_document_extractor.StatisticsCard";
    static props = {
        title: { type: String },
        count: { type: Number },
        docType: { type: String },
        onClick: { type: Function }
    };

    handleClick() {
        this.props.onClick(this.props.docType);
    }
}
