/** @odoo-module **/

import { ListRenderer } from "@web/views/list/list_renderer";

export class GroupedListRenderer extends ListRenderer {
    static useMagicColumnWidths = false

    get hasGroupedHeaders() {
        return this.columns.some(col => col.groupStart);
    }

    get headerColumns1() {
        const columns = []

        let index = 0

        for(index = 0; index < this.columns.length; index++) {
            let col = this.columns[index]

            if (!col.groupStart) {
                col.rowspan = 2
                columns.push(col)
            } else {
                let j = index + 1
                let colspan = 2
                for (j = index + 1; j < this.columns.length; j++) {
                    this.columns[j].groupClass = col.groupClass
                    if (this.columns[j].groupEnd || (this.columns[j].type == 'button_group' && this.columns[j].buttons.filter((btn) => btn.groupEnd))) {
                        index = j
                        break
                    }
                    
                    colspan += 1
                }

                // Get label: use dynamic field label if groupLabelField is set, otherwise use groupName
                let groupLabel = col.groupName;
                if (col.groupLabelField && this.props.list.fields[col.groupLabelField]) {
                    groupLabel = this.props.list.fields[col.groupLabelField].string;
                }

                columns.push({
                    colspan: colspan,
                    type: "field_group",
                    label: groupLabel,
                    groupClass: col.groupClass || "",
                    id: `column_group_${index}`
                })
            }
        }

        return columns
    }

    get headerColumns2() {
        const columns = []
        let index = 0
        for(index = 0; index < this.columns.length; index++) {
            let col = this.columns[index]
            if (col.groupStart) {
                let j = index
                for (j = index; j < this.columns.length; j++) {
                    this.columns[j].groupClass = col.groupClass
                    if (this.columns[j].groupEnd || (this.columns[j].type == 'button_group' && this.columns[j].buttons.filter((btn) => btn.groupEnd))) {
                        index = j
                        columns.push(this.columns[j])
                        break
                    }
                    columns.push(this.columns[j])
                }
            }
        }

        return columns
    }

    getColumnClass(column) {
        let className = super.getColumnClass(column)
        if (column.groupClass) {
            className += ` ${column.groupClass}`
        }
        return className
    }

    getCellClass(column, record) {
        let className = super.getCellClass(column, record)
        if (column.groupClass) {
            className += ` ${column.groupClass}`
        }
        return className
    }

}
