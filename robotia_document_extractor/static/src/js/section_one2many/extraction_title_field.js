/** @odoo-module */

import { CharField, charField } from "@web/views/fields/char/char_field";
import { registry } from "@web/core/registry";
import { useEffect, useRef } from "@odoo/owl";

/**
 * Custom CharField for title/section fields in extraction tables
 *
 * Similar to survey's DescriptionPageField:
 * - Shows external link button to open record in edit mode
 * - Shows pencil icon for title rows
 *
 * Used for: substance_name, equipment_type, product_type fields
 */
class ExtractionTitleField extends CharField {
    static template = "robotia_document_extractor.ExtractionTitleField";

    setup() {
        super.setup();
        const inputRef = useRef("input");
        useEffect(
            (input) => {
                if (input) {
                    input.classList.add("col");
                }
            },
            () => [inputRef.el]
        );
    }

    /**
     * Open record in form view when external button is clicked
     */
    onExternalBtnClick() {
        this.env.openRecord(this.props.record);
    }
}

registry.category("fields").add("extraction_title_field", {
    ...charField,
    component: ExtractionTitleField,
});
