/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { ExtractionSectionListRenderer } from "../section_one2many/extraction_section_list_renderer";

/**
 * Custom List Renderer with grouped columns and 2-level headers
 * Extends ExtractionSectionListRenderer to keep section titles + row numbering features
 *
 * Features:
 * - Row numbering (from X2ManyNumberedListRenderer)
 * - Section/title rows (from ExtractionSectionListRenderer)
 * - Grouped columns with 2-level headers (new feature)
 * - Header replacement from parent record (new feature)
 *
 * Logic inspired by group_list_view:
 * - Row 1: Non-grouped columns with rowspan=2, Group headers with colspan
 * - Row 2: Only grouped columns (children of groups)
 *
 * Usage: Only with extraction_grouped_one2many widget
 */
export class ExtractionGroupedListRenderer extends ExtractionSectionListRenderer {
    static template = "robotia_document_extractor.ExtractionGroupedListRenderer";

    /**
     * Check if we have any grouped columns
     */
    get hasGroupedHeaders() {
        const groupConfig = this.env.groupColumnConfig;
        return groupConfig && Object.keys(groupConfig).length > 0;
    }

    /**
     * Get columns for Row 1 (parent header row)
     * - Non-grouped columns: rowspan=2
     * - Group headers: colspan=number of columns in group
     */
    get headerColumns1() {
        const columns = [];
        let index = 0;

        while (index < this.columns.length) {
            const col = this.columns[index];
            const groupInfo = this.findColumnGroup(col.name);

            if (!groupInfo) {
                // Non-grouped column: add with rowspan=2
                columns.push({
                    ...col,
                    rowspan: 2
                });
                index++;
            } else {
                // Start of a group: add group header with colspan
                const groupLabel = this.getGroupLabel(groupInfo.groupKey);
                columns.push({
                    type: 'field_group',
                    label: groupLabel,
                    colspan: groupInfo.childColumns.length,
                    rowspan: 1,
                    groupClass: 'o_grouped_column_header text-center',
                    id: `column_group_${groupInfo.groupKey}`
                });

                // Skip all columns in this group
                index += groupInfo.childColumns.length;
            }
        }

        return columns;
    }

    /**
     * Get columns for Row 2 (child header row)
     * - Only columns that belong to groups
     */
    get headerColumns2() {
        const columns = [];

        for (const col of this.columns) {
            const groupInfo = this.findColumnGroup(col.name);
            if (groupInfo) {
                // This column is in a group, add it to row 2
                columns.push({
                    ...col,
                    rowspan: 1
                });
            }
        }

        return columns;
    }

    /**
     * Find which group a column belongs to
     *
     * @param {string} columnName - Name of the column to check
     * @returns {Object|null} Group info or null if column is not in any group
     */
    findColumnGroup(columnName) {
        const groupConfig = this.env.groupColumnConfig;
        if (!groupConfig) {
            return null;
        }

        for (const [groupKey, childNames] of Object.entries(groupConfig)) {
            const index = childNames.indexOf(columnName);
            if (index !== -1) {
                // Found the column in this group
                const childColumns = childNames.map(name =>
                    this.columns.find(col => col.name === name)
                ).filter(col => col !== undefined);  // Filter out undefined (column not found)

                return {
                    groupKey,
                    childColumns,
                    isFirst: index === 0  // This is the first column in the group
                };
            }
        }

        return null;
    }

    /**
     * Get label for a column group
     * Reads from parent record field if available
     *
     * @param {string} groupKey - The group key (e.g., 'year_1')
     * @returns {string} Label for the group
     */
    getGroupLabel(groupKey) {
        const parentRecord = this.env.parentRecord;
        if (parentRecord && parentRecord.data && parentRecord.data[groupKey]) {
            const value = parentRecord.data[groupKey];
            return _t('Year %s', String(value));
        }

        // Fallback to groupKey if parent field not found or empty
        return groupKey;
    }
}
