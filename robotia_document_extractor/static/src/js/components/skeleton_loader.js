/** @odoo-module **/

import { Component } from "@odoo/owl";

/**
 * Skeleton loader component for extraction page
 * Displays loading placeholders matching the page selector layout
 */
export class ExtractionSkeleton extends Component {
    static template = "robotia_document_extractor.ExtractionSkeleton";
    static props = {
        showStepper: { type: Boolean, optional: true }, // Show progress stepper skeleton
    };
}
