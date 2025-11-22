/** @odoo-module **/

import { registry } from "@web/core/registry";
import { ExtractionSectionOneToManyField, extractionSectionOneToManyField } from "../section_one2many/extraction_section_one2many_field";
import { ExtractionGroupedListRenderer } from "./extraction_grouped_list_renderer";
import { useSubEnv } from "@odoo/owl";

/**
 * Custom One2many Field Widget for extraction tables with:
 * - Section/title rows (from ExtractionSectionOneToManyField)
 * - Row numbering (from X2ManyNumberedListRenderer)
 * - Grouped columns with 2-level headers (new)
 * - Header replacement from parent record (new)
 *
 * Usage in XML views:
 * <field name="substance_usage_ids" widget="extraction_grouped_one2many"
 *        options="{
 *            'titleField': 'substance_name',
 *            'group_columns': {
 *                'year_1': ['year_1_quantity_kg', 'year_1_quantity_co2'],
 *                'year_2': ['year_2_quantity_kg', 'year_2_quantity_co2']
 *            },
 *            'replace_header_year_1_quantity_kg': 'year_1',
 *            'replace_header_year_1_quantity_co2': 'year_1'
 *        }">
 *     <list editable="bottom">
 *         <field name="is_title" column_invisible="1"/>
 *         <field name="substance_name" column_invisible="1"/>
 *         <field name="substance_id" widget="extraction_title_field"/>
 *         <field name="year_1_quantity_kg"/>
 *         <field name="year_1_quantity_co2"/>
 *     </list>
 * </field>
 */
export class ExtractionGroupedOneToManyField extends ExtractionSectionOneToManyField {
    static components = {
        ...ExtractionSectionOneToManyField.components,
        ListRenderer: ExtractionGroupedListRenderer,
    };

    static props = {
        ...ExtractionSectionOneToManyField.props,
        groupColumnConfig: { type: Object, optional: true },
        headerReplacements: { type: Object, optional: true },
    };

    static defaultProps = {
        ...ExtractionSectionOneToManyField.defaultProps,
        editable: "bottom",
    };

    setup() {
        super.setup();

        const envAdditions = {};

        // Add groupColumnConfig to environment if provided
        if (this.props.groupColumnConfig) {
            envAdditions.groupColumnConfig = this.props.groupColumnConfig;
            // Store parent record for label resolution
            envAdditions.parentRecord = this.props.record;
        }

        // Add headerReplacements to environment if provided
        // Resolve parent field values at setup time
        if (this.props.headerReplacements) {
            const resolvedHeaders = {};
            for (const [fieldName, parentFieldName] of Object.entries(this.props.headerReplacements)) {
                // Access parent record data via this.props.record.data
                const parentValue = this.props.record.data[parentFieldName];

                // Only add if parent field has a value
                if (parentValue !== undefined && parentValue !== null && parentValue !== false && parentValue !== '') {
                    resolvedHeaders[fieldName] = String(parentValue);
                }
            }

            // Only add to environment if we have any resolved values
            if (Object.keys(resolvedHeaders).length > 0) {
                envAdditions.headerReplacements = resolvedHeaders;
            }
        }

        // Apply environment additions if any
        if (Object.keys(envAdditions).length > 0) {
            useSubEnv(envAdditions);
        }
    }
}

export const extractionGroupedOneToManyField = {
    ...extractionSectionOneToManyField,
    component: ExtractionGroupedOneToManyField,
    additionalClasses: [...extractionSectionOneToManyField.additionalClasses || [], "o_field_one2many"],
    extractProps(args, dynamicInfo) {
        const props = extractionSectionOneToManyField.extractProps(args, dynamicInfo);

        // Extract group_columns option
        if (args.options?.group_columns) {
            props.groupColumnConfig = args.options.group_columns;
        }

        // Extract titleField from options (inherit from parent)
        if (args.options?.titleField) {
            props.titleField = args.options.titleField;
        }

        // Extract replace_header_* options
        const headerReplacements = {};
        let hasHeaderReplacements = false;

        for (const [key, value] of Object.entries(args.options || {})) {
            if (key.startsWith('replace_header_')) {
                // Extract the field name (remove 'replace_header_' prefix)
                const fieldName = key.substring('replace_header_'.length);
                // value is the parent field name to read from
                headerReplacements[fieldName] = value;
                hasHeaderReplacements = true;
            }
        }

        // Only add headerReplacements prop if we found any
        if (hasHeaderReplacements) {
            props.headerReplacements = headerReplacements;
        }

        return props;
    },
};

// Register the widget
registry.category("fields").add("extraction_grouped_one2many", extractionGroupedOneToManyField);
