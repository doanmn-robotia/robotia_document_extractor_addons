/** @odoo-module **/

import { makeContext } from "@web/core/context";
import { useEffect } from "@odoo/owl";
import { NoMagicColumnListRenderer } from "../../no_magic_width_list/no_magic_width_list";

/**
 * Custom List Renderer for extraction tables with section/title rows
 *
 * Similar to survey's QuestionPageListRenderer but adapted for document extraction:
 * - Uses 'is_title' as discriminant to identify title rows
 * - Title rows are displayed with bold text and colspan
 * - Adds 'o_section_list_view' class to table
 *
 * Used for tables: substance.usage, equipment.product, equipment.ownership, collection.recycling
 */
export class ExtractionSectionListRenderer extends NoMagicColumnListRenderer {
    setup() {
        super.setup();

        // Discriminant field to identify title/section rows
        this.discriminant = "is_title";

        // Fields to show in section rows (if any special handling needed)
        this.fieldsToShow = [];

        // Title field that will have colspan in section rows
        // For substance.usage: 'substance_name' contains section title
        this.titleField = "substance_name";

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
     * Get columns for a record - section rows have modified columns with colspan
     */
    getColumns(record) {
        const columns = super.getColumns(record);
        if (this.isSection(record)) {
            return this.getSectionColumns(columns);
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
     * Modify columns for section rows:
     * - Find title column
     * - Add colspan to span across hidden columns
     * - Hide data columns that don't make sense for title rows
     */
    getSectionColumns(columns) {
        let titleColumnIndex = 0;
        let found = false;
        let colspan = 1;

        // Find title column and calculate colspan
        for (let index = 0; index < columns.length; index++) {
            const col = columns[index];
            if (!found && col.name !== this.titleField) {
                continue;
            }
            if (!found) {
                found = true;
                titleColumnIndex = index;
                continue;
            }
            // Skip columns that should be shown in section rows
            if (col.type !== "field" || this.fieldsToShow.includes(col.name)) {
                break;
            }
            colspan += 1;
        }

        // Create new columns array with modified title column
        const sectionColumns = columns
            .slice(0, titleColumnIndex + 1)
            .concat(columns.slice(titleColumnIndex + colspan));

        // Add colspan to title column
        sectionColumns[titleColumnIndex] = { ...sectionColumns[titleColumnIndex], colspan };
        return sectionColumns;
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

export class ExtractionSectionListRendererEquipmentType extends ExtractionSectionListRenderer {
    setup() {
        super.setup()
        this.titleField = 'equipment_type'
    }
}


