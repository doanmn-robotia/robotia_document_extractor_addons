/** @odoo-module **/

import { registry } from "@web/core/registry";
import { X2ManyField, x2ManyField } from "@web/views/fields/x2many/x2many_field";
import { ExtractionSectionListRenderer } from "./extraction_section_list_renderer";
import { useSubEnv } from "@odoo/owl";

/**
 * Custom One2many Field Widget for extraction tables with section/title rows
 *
 * Uses ExtractionSectionListRenderer to toggle visibility between two fields:
 * - Title rows (is_title=True): Show titleField (Char), hide removeField (Many2one)
 * - Data rows (is_title=False): Show removeField (Many2one), hide titleField (Char)
 *
 * Usage in XML views:
 * <field name="substance_usage_ids" widget="extraction_section_one2many"
 *        options="{'titleField': 'substance_name', 'removeField': 'substance_id'}">
 *   <list editable="bottom">
 *     <field name="is_title" column_invisible="1"/>
 *     <field name="substance_name" widget="extraction_title_field"/>  <!-- Shown in title rows -->
 *     <field name="substance_id" required="1"/>                       <!-- Shown in data rows -->
 *     <field name="year_1_quantity_kg"/>
 *     ...
 *   </list>
 * </field>
 *
 * Options:
 * - titleField: Name of Char field to show in title rows (e.g., 'substance_name')
 * - removeField: Name of Many2one field to hide in title rows (e.g., 'substance_id')
 */
export class ExtractionSectionOneToManyField extends X2ManyField {
    static components = {
        ...X2ManyField.components,
        ListRenderer: ExtractionSectionListRenderer,
    };

    static props = {
        ...X2ManyField.props,
        titleField: { type: String, optional: true },
        removeField: { type: String, optional: true }
    }

    static defaultProps = {
        ...X2ManyField.defaultProps,
        editable: "bottom",
    };

    setup() {
        super.setup()
        useSubEnv({
            titleField: this.props.titleField,
            removeField: this.props.removeField
        })
    }

}

export const extractionSectionOneToManyField = {
    ...x2ManyField,
    component: ExtractionSectionOneToManyField,
    additionalClasses: [...x2ManyField.additionalClasses || [], "o_field_one2many"],
    extractProps(args, dynamicInfo) {
        const props = x2ManyField.extractProps(args, dynamicInfo);
        // Extract titleField and removeField from options
        if (args.options?.titleField) {
            props.titleField = args.options.titleField;
        }
        if (args.options?.removeField) {
            props.removeField = args.options.removeField;
        }
        return props;
    },
};

// Register the widget
registry.category("fields").add("extraction_section_one2many", extractionSectionOneToManyField);
