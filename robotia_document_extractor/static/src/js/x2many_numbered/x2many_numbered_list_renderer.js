/** @odoo-module **/

import { ListRenderer } from "@web/views/list/list_renderer";

/**
 * Custom List Renderer that adds a "#" column showing row numbers
 *
 * Features:
 * - Adds a sequential number column as the first column
 * - Numbers are 1-indexed (starts from 1, not 0)
 * - Automatically updates when rows are added/removed/reordered
 *
 * Usage:
 * Use with X2ManyNumberedField widget:
 * <field name="line_ids" widget="x2many_numbered"/>
 */
export class X2ManyNumberedListRenderer extends ListRenderer {
    static template = "robotia_document_extractor.X2ManyNumberedListRenderer";

    /**
     * Override getColumns to inject the "#" column at the beginning
     */
    getColumns(record) {
        const columns = super.getColumns(record);

        // Create the sequence number column
        const sequenceColumn = {
            id: '__sequence_number__',
            name: '__sequence_number__',
            type: 'sequence',
            label: '#',
            width: '50px',
            className: 'o_list_number_th text-center',
            optional: false,
            hasLabel: true,
        };

        // Insert at the beginning
        return [sequenceColumn, ...columns];
    }

    /**
     * Override getCellClass to add styling for sequence column
     */
    getCellClass(column, record) {
        let classNames = super.getCellClass(column, record);

        if (column.name === '__sequence_number__') {
            classNames += ' o_list_number text-center text-muted fw-bold';
        }

        return classNames;
    }

    /**
     * Get the sequence number for a record
     * Returns 1-indexed position in the visible list
     */
    getSequenceNumber(record) {
        const records = this.props.list.records;
        const index = records.indexOf(record);
        return index + 1;
    }

    /**
     * Override evalInContext to provide sequence number value for rendering
     */
    evalInContext(record, column) {
        if (column.name === '__sequence_number__') {
            return this.getSequenceNumber(record);
        }
        return super.evalInContext(...arguments);
    }

    /**
     * Check if this is the sequence number column
     */
    isSequenceColumn(column) {
        return column.name === '__sequence_number__';
    }
}
