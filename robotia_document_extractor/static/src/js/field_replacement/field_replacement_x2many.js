/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { X2ManyField, x2ManyField } from "@web/views/fields/x2many/x2many_field";
import { useSubEnv } from "@odoo/owl";

/**
 * Global patch for X2ManyField to support field replacement, header replacement, and grouped columns via options
 *
 * FEATURE 1: Field Replacement
 * Usage in XML:
 * <field name="my_ids" widget="one2many"
 *        options="{'replace_field_year_1': 'actual_year_1', 'replace_field_year_2': 'actual_year_2'}">
 *     <list>
 *         <field name="year_1"/>  <!-- Will be replaced by actual_year_1 -->
 *         <field name="actual_year_1" column_invisible="1"/>
 *         <field name="year_2"/>  <!-- Will be replaced by actual_year_2 -->
 *         <field name="actual_year_2" column_invisible="1"/>
 *     </list>
 * </field>
 *
 * FEATURE 2: Header Replacement from Parent Record
 * Usage in XML:
 * <field name="my_ids" widget="one2many"
 *        options="{'replace_header_year_1_quantity_kg': 'year_1', 'replace_header_year_1_quantity_co2': 'year_1'}">
 *     <list>
 *         <field name="year_1_quantity_kg"/>  <!-- Header becomes value of parent.year_1 (e.g., "2023") -->
 *         <field name="year_1_quantity_co2"/>  <!-- Header becomes value of parent.year_1 (e.g., "2023") -->
 *     </list>
 * </field>
 *
 * FEATURE 3: Grouped Columns with 2-Level Headers
 * Usage in XML:
 * <field name="my_ids" widget="one2many"
 *        options="{'group_columns': {'year_1': ['year_1_quantity_kg', 'year_1_quantity_co2']}}">
 *     <list>
 *         <field name="year_1_quantity_kg"/>  <!-- Grouped under parent.year_1 header -->
 *         <field name="year_1_quantity_co2"/>
 *     </list>
 * </field>
 *
 * How it works:
 * - extractProps: Extracts replace_field_*, replace_header_*, and group_columns options
 * - setup: Resolves parent field values and uses useSubEnv to make replacements available to ListRenderer
 * - ListRenderer reads this.env.fieldReplacements, this.env.headerReplacements, and this.env.groupColumnConfig
 */

// Patch X2ManyField component to handle field replacements, header replacements, and grouped columns
patch(X2ManyField.prototype, {
    /**
     * Setup hook - add fieldReplacements, headerReplacements, and groupColumnConfig to environment
     */
    setup() {
        super.setup();

        const envAdditions = {};

        // Add fieldReplacements to environment if provided
        if (this.props.fieldReplacements) {
            envAdditions.fieldReplacements = this.props.fieldReplacements;
        }

        // Add headerReplacements to environment if provided
        // Resolve parent field values at setup time
        if (this.props.headerReplacements) {
            const resolvedHeaders = {};
            for (const [fieldName, parentFieldName] of Object.entries(this.props.headerReplacements)) {
                // Access parent record data via this.props.record.data
                const parentValue = this.props.record.data[parentFieldName];

                // Only add if parent field has a value (not null, undefined, false, or empty string)
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
});

// Patch x2ManyField extractProps to extract replace_field_* and replace_header_* options
const originalExtractProps = x2ManyField.extractProps;

X2ManyField.props = {
    ...X2ManyField.props,
    headerReplacements: { type: Object, optional: true }
}

x2ManyField.extractProps = function(args, dynamicInfo) {
    const props = originalExtractProps.call(this, args, dynamicInfo);

    // Extract field replacement and header replacement options
    if (args.options) {
        const fieldReplacements = {};
        const headerReplacements = {};
        let hasFieldReplacements = false;
        let hasHeaderReplacements = false;

        for (const [key, value] of Object.entries(args.options)) {
            // Check if option key starts with 'replace_field_'
            if (key.startsWith('replace_field_')) {
                // Extract the field name (remove 'replace_field_' prefix)
                const originalFieldName = key.substring('replace_field_'.length);
                fieldReplacements[originalFieldName] = value;
                hasFieldReplacements = true;
            }
            // Check if option key starts with 'replace_header_'
            else if (key.startsWith('replace_header_')) {
                // Extract the field name (remove 'replace_header_' prefix)
                const fieldName = key.substring('replace_header_'.length);
                // value is the parent field name to read from
                headerReplacements[fieldName] = value;
                hasHeaderReplacements = true;
            }
        }

        // Only add fieldReplacements prop if we found any
        if (hasFieldReplacements) {
            props.fieldReplacements = fieldReplacements;
        }

        // Only add headerReplacements prop if we found any
        if (hasHeaderReplacements) {
            props.headerReplacements = headerReplacements;
        }
    }

    return props;
};
