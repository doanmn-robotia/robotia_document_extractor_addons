/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ListRenderer } from "@web/views/list/list_renderer";

/**
 * Global patch for ListRenderer to support field replacement and header replacement in X2ManyField
 *
 * FEATURE 1: Field Replacement
 * Usage in XML:
 * <field name="my_ids" widget="one2many" options="{'replace_field_year_1': 'actual_year_1'}">
 *     <list>
 *         <field name="year_1"/>  <!-- Will show actual_year_1's data -->
 *         <field name="actual_year_1" column_invisible="1"/>  <!-- Hidden, provides data -->
 *     </list>
 * </field>
 *
 * FEATURE 2: Header Replacement from Parent Record
 * Usage in XML:
 * <field name="my_ids" widget="one2many" options="{'replace_header_year_1_quantity_kg': 'year_1'}">
 *     <list>
 *         <field name="year_1_quantity_kg"/>  <!-- Header becomes value of parent.year_1 (e.g., "2023") -->
 *     </list>
 * </field>
 *
 * How it works:
 * - Reads fieldReplacements and headerReplacements from environment (set by X2ManyField patch)
 * - In getActiveColumns(), checks if any visible column should have field or header replaced
 * - Field replacement: Finds replacement column in allColumns and replaces entire column
 * - Header replacement: Replaces only column.label with parent field value
 */
patch(ListRenderer.prototype, {
    /**
     * Override getActiveColumns to apply field replacements and header replacements
     *
     * For each column, checks if there's a replacement defined in this.env.fieldReplacements or this.env.headerReplacements
     * - Field replacement: Replaces entire column with replacement column from allColumns
     * - Header replacement: Replaces only column.label with parent field value
     *
     * @param {Object} list - The list model
     * @returns {Array} Array of active columns with replacements applied
     */
    getActiveColumns(list) {
        let columns = super.getActiveColumns(list);

        // Apply field replacements (existing logic)
        const fieldReplacements = this.env.fieldReplacements;
        if (fieldReplacements && Object.keys(fieldReplacements).length > 0) {
            columns = columns.map(col => {
                // Skip non-field columns (buttons, widgets, etc.)
                if (col.type !== "field") {
                    return col;
                }

                // Check if this column should be replaced
                const replacementFieldName = fieldReplacements[col.name];
                if (!replacementFieldName || replacementFieldName === col.name) {
                    return col;
                }

                // Find the replacement field in allColumns (includes invisible columns)
                const replacementCol = this.allColumns.find(
                    c => c.name === replacementFieldName && c.type === "field"
                );

                if (!replacementCol) {
                    console.warn(
                        `Field replacement: Cannot find replacement field '${replacementFieldName}' ` +
                        `for '${col.name}'. Available fields: ${this.allColumns.map(c => c.name).join(', ')}`
                    );
                    return col;
                }

                // Replace with the replacement column
                // Use all properties from the replacement column
                return {
                    ...replacementCol,
                    // Keep the original column's ID to maintain uniqueness
                    id: col.id,
                };
            });
        }

        // Apply header replacements (new logic)
        const headerReplacements = this.env.headerReplacements;
        if (headerReplacements && Object.keys(headerReplacements).length > 0) {
            columns = columns.map(col => {
                // Skip non-field columns (buttons, widgets, etc.)
                if (col.type !== "field") {
                    return col;
                }

                // Check if this column has a header replacement
                const newHeaderValue = headerReplacements[col.name];
                if (newHeaderValue) {
                    // Create a new column object with replaced label
                    return {
                        ...col,
                        label: newHeaderValue,
                        // Store original label for potential future use (tooltips, etc.)
                        originalLabel: col.label
                    };
                }

                return col;
            });
        }

        return columns;
    }
});
