/** @odoo-module **/

import { registry } from "@web/core/registry";
import { X2ManyField, x2ManyField } from "@web/views/fields/x2many/x2many_field";
import { GroupedListRenderer } from "./group_list_renderer";

/**
 * Patch X2Many Field to support grouped column headers automatically
 *
 * This patches the default X2ManyField to use GroupedListRenderer,
 * which automatically detects and displays grouped headers when context attributes are present.
 *
 * Usage in XML views (no widget needed):
 * <field name="one2many_field">
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
export class PatchedX2ManyField extends X2ManyField {
    static components = {
        ...X2ManyField.components,
        ListRenderer: GroupedListRenderer,
    };
}

export const patchedX2ManyField = {
    ...x2ManyField,
    component: PatchedX2ManyField,
    displayName: "X2Many with auto-grouped headers support",
};

// Patch all default X2Many field types
registry.category("fields").add("one2many", patchedX2ManyField, { force: true });
registry.category("fields").add("many2many", patchedX2ManyField, { force: true });
