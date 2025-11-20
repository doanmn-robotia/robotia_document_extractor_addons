/** @odoo-module **/

import { makeContext } from "@web/core/context";
import { useEffect } from "@odoo/owl";
import { NoMagicColumnListRenderer } from "../../no_magic_width_list/no_magic_width_list";
import { X2ManyNumberedListRenderer } from "../x2many_numbered/x2many_numbered_list_renderer";

/**
 * Custom List Renderer for extraction tables with section/title rows
 *
 * Toggles column visibility based on row type:
 * - Title rows (is_title=True): Show titleField (Char), hide removeField (Many2one)
 * - Data rows (is_title=False): Hide titleField (Char), show removeField (Many2one)
 *
 * Features:
 * - Uses 'is_title' as discriminant to identify title/data rows
 * - Title rows displayed with bold text and special styling (o_is_section, fw-bold)
 * - Adds 'o_section_list_view' class to table
 * - Extends X2ManyNumberedListRenderer (includes row numbers)
 *
 * Configuration via environment:
 * - this.titleField: Name of Char field (default: 'substance_name')
 * - this.removeField: Name of Many2one field to hide in title rows
 *
 * Used for tables: substance.usage, equipment.product, equipment.ownership, collection.recycling, quota.usage
 */
export class ExtractionSectionListRenderer extends X2ManyNumberedListRenderer {
    setup() {
        super.setup();

        // Discriminant field to identify title/section rows
        this.discriminant = "is_title";

        // Title field (Char field shown in section rows, hidden in data rows)
        // Examples: 'substance_name', 'product_type', 'equipment_type'
        this.titleField = this.env.titleField || "substance_name";

        // Remove field (Many2one field hidden in section rows, shown in data rows)
        // Examples: 'substance_id', 'equipment_type_id'
        this.removeField = this.env.removeField;

        // Add 'o_section_list_view' class to table
        useEffect(
            (table) => {
                if (table) {
                    table.classList.add("o_section_list_view");
                }
            },
            () => [this.tableRef.el]
        );
    }

    /**
     * Check if a record is a section/title row
     */
    isSection(record) {
        return record.data[this.discriminant];
    }

    /**
     * Get row class - add special classes for section rows
     */
    getRowClass(record) {
        const classNames = super.getRowClass(record).split(" ");
        if (this.isSection(record)) {
            classNames.push(`o_is_section`, `fw-bold`);
        }
        return classNames.join(" ");
    }

    /**
     * Get columns for a record - toggle visibility based on row type
     */
    getColumns(record) {
        let columns = super.getColumns(record);
        if (this.isSection(record)) {
            columns = this.getSectionColumns(columns);
        } else {
            columns = this.getDataColumns(columns);
        }
        return columns;
    }

    /**
     * Get cell class for styling
     */
    getCellClass(column, record) {
        const classNames = super.getCellClass(column, record);
        if (column.type === "button_group") {
            return `${classNames} text-end`;
        }
        return classNames;
    }

    /**
     * Get columns for section/title rows
     * Hide the removeField column (usually Many2one like substance_id)
     * Show the titleField column (usually Char like substance_name)
     */
    getSectionColumns(columns) {
        if (!this.removeField) {
            return columns; // No removeField specified, return as-is
        }

        return columns.map(col => {
            if (col.name === this.removeField) {
                // Hide the removeField column (e.g., substance_id)
                return { ...col, type: 'invisible' };
            }
            return col;
        });
    }

    /**
     * Get columns for data rows
     * Hide the titleField column (usually Char like substance_name)
     * Show the removeField column (usually Many2one like substance_id)
     */
    getDataColumns(columns) {
        const titleField = this.titleField;
        if (!titleField) {
            return columns; // No titleField specified, return as-is
        }

        return columns.map(col => {
            if (col.name === titleField) {
                // Hide the titleField column (e.g., substance_name)
                return { ...col, type: 'invisible' };
            }
            return col;
        });
    }

    /**
     * Override add() to handle context for section rows
     */
    add(params) {
        let editable = false;
        if (params.context && !this.env.isSmall) {
            const evaluatedContext = makeContext([params.context]);
            if (evaluatedContext[`default_${this.discriminant}`]) {
                editable = this.props.editable;
            }
        }
        super.add({ ...params, editable });
    }

    /**
     * Override focusCell to handle column name matching
     */
    focusCell(column, forward = true) {
        const actualColumn = column.name
            ? this.columns.find((col) => col.name === column.name)
            : column;
        super.focusCell(actualColumn, forward);
    }

    /**
     * Handle keyboard navigation in edit mode
     */
    onCellKeydownEditMode(hotkey) {
        switch (hotkey) {
            case "enter":
            case "tab":
            case "shift+tab": {
                this.props.list.leaveEditMode();
                return true;
            }
        }
        return super.onCellKeydownEditMode(...arguments);
    }
}



