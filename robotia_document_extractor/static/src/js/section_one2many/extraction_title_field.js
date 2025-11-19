/** @odoo-module */

import { CharField, charField } from "@web/views/fields/char/char_field";
import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";
import { many2OneField, Many2OneField } from "@web/views/fields/many2one/many2one_field";

/**
 * Custom CharField for title/section fields in extraction tables
 *
 * Similar to survey's DescriptionPageField:
 * - Shows external link button to open record in edit mode
 * - Shows pencil icon for title rows
 *
 * Used for: substance_name, equipment_type, product_type fields
 */
class ExtractionTitleField extends Component {
    static template = "robotia_document_extractor.ExtractionTitleField";

    static props = {"*": {optional: true}}

    static components = { CharField, Many2OneField }

    setup() {
        
    }

}

registry.category("fields").add("extraction_title_field", {
    ...charField,
    component: ExtractionTitleField,
    extractProps(options, dynamicInfo) {
        return {
            ...charField.extractProps(options, dynamicInfo),
            ...many2OneField.extractProps(options, dynamicInfo)
        }
    }
});
