/** @odoo-module **/

import { registry } from "@web/core/registry";
import { X2ManyField, x2ManyField } from "@web/views/fields/x2many/x2many_field";
import { X2ManyNumberedListRenderer } from "./x2many_numbered_list_renderer";

/**
 * Custom X2Many Field Widget with automatic row numbering
 *
 * This widget adds a "#" column at the beginning of One2many/Many2many tables
 * showing sequential row numbers (1, 2, 3, etc.)
 *
 * Usage in XML views:
 * <field name="line_ids" widget="x2many_numbered">
 *   <tree editable="bottom">
 *     <field name="product_id"/>
 *     <field name="quantity"/>
 *     <field name="price"/>
 *   </tree>
 * </field>
 *
 * OR for compatibility with One2many:
 * <field name="order_line_ids" widget="one2many_numbered">
 *   <tree>
 *     <field name="name"/>
 *     <field name="qty"/>
 *   </tree>
 * </field>
 */
export class X2ManyNumberedField extends X2ManyField {
    static components = {
        ...X2ManyField.components,
        ListRenderer: X2ManyNumberedListRenderer,
    };

    static template = "web.X2ManyField";
}

/**
 * Field definition for registry
 */
export const x2ManyNumberedField = {
    ...x2ManyField,
    component: X2ManyNumberedField,
    additionalClasses: [...x2ManyField.additionalClasses || [], "o_field_x2many_numbered"],
};

// Register the widget with multiple names for flexibility
registry.category("fields").add("x2many_numbered", x2ManyNumberedField);
registry.category("fields").add("one2many_numbered", x2ManyNumberedField);
registry.category("fields").add("many2many_numbered", x2ManyNumberedField);
