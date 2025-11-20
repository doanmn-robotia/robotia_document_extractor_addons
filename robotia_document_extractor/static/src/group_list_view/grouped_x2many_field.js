/** @odoo-module **/

import { registry } from "@web/core/registry";
import { X2ManyField, x2ManyField } from "@web/views/fields/x2many/x2many_field";
import { GroupedListRenderer } from "./group_list_renderer";

/**
 * Custom X2Many Field Widget with grouped column headers
 *
 * This widget extends X2ManyField to support grouped column headers in list view.
 * It uses GroupedListRenderer which displays columns in groups with colspan headers.
 *
 * Usage in XML views:
 * <field name="one2many_field" widget="grouped_x2many">
 *   <list editable="bottom">
 *     <field name="name"/>
 *     <field name="col_x" context="{'group_start': True, 'group_label_field': 'category_id', 'group_class': 'bg-info-subtle'}"/>
 *     <field name="col_y" context="{'group_end': True}"/>
 *     <field name="other_field"/>
 *   </list>
 * </field>
 *
 * Context options for grouping:
 * - group_start: Mark the first column in the group
 * - group_end: Mark the last column in the group
 * - group_label_field: Field name to get the label from (dynamic label from field definition)
 * - group_header: Static label for the group (alternative to group_label_field)
 * - group_class: CSS class to apply to the grouped columns
 */
export class GroupedX2ManyField extends X2ManyField {
    static components = {
        ...X2ManyField.components,
        ListRenderer: GroupedListRenderer,
    };
}

export const groupedX2ManyField = {
    ...x2ManyField,
    component: GroupedX2ManyField,
    displayName: "Relational table with grouped headers",
};

// Register the widget for both one2many and many2many
registry.category("fields").add("grouped_x2many", groupedX2ManyField);
registry.category("fields").add("grouped_one2many", groupedX2ManyField);
registry.category("fields").add("grouped_many2many", groupedX2ManyField);
