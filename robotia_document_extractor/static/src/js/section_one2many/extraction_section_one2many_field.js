/** @odoo-module **/

import { registry } from "@web/core/registry";
import { X2ManyField, x2ManyField } from "@web/views/fields/x2many/x2many_field";
import { ExtractionSectionListRenderer } from "./extraction_section_list_renderer";
import { useSubEnv } from "@odoo/owl";

/**
 * Custom One2many Field Widget for extraction tables with section/title rows
 *
 * Uses ExtractionSectionListRenderer to display title rows with special styling
 *
 * Usage in XML views:
 * <field name="substance_usage_ids" widget="extraction_section_one2many">
 *   <list editable="bottom">
 *     <field name="is_title" column_invisible="1"/>
 *     <field name="sequence" column_invisible="1"/>
 *     <field name="usage_type" column_invisible="1"/>
 *     <field name="substance_name"/>
 *     <field name="year_1_quantity_kg"/>
 *     ...
 *   </list>
 * </field>
 */
export class ExtractionSectionOneToManyField extends X2ManyField {
    static components = {
        ...X2ManyField.components,
        ListRenderer: ExtractionSectionListRenderer,
    };

    static props = {
        ...X2ManyField.props,
        titleField: { type: String, optional: true }
    }

    static defaultProps = {
        ...X2ManyField.defaultProps,
        editable: "bottom",
    };

    setup() {
        super.setup()
        useSubEnv({
            titleField: this.props.titleField
        })
    }

}

export const extractionSectionOneToManyField = {
    ...x2ManyField,
    component: ExtractionSectionOneToManyField,
    additionalClasses: [...x2ManyField.additionalClasses || [], "o_field_one2many"],
    extractProps(args, dynamicInfo) {
        const props = x2ManyField.extractProps(args, dynamicInfo);
        // Extract titleField from options and pass to renderer
        if (args.options?.titleField) {
            props.titleField = args.options.titleField;
        }
        return props;
    },
};

// Register the widget
registry.category("fields").add("extraction_section_one2many", extractionSectionOneToManyField);
