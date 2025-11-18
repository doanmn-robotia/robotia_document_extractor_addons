X2MANY NUMBERED WIDGET - USAGE GUIDE
=====================================

This widget adds an automatic row number column ("#") to One2many and Many2many fields.

FEATURES:
- Automatic sequential numbering (1, 2, 3, ...)
- Updates automatically when rows are added/removed/reordered
- Clean, professional styling
- Works with both One2many and Many2many fields
- Compatible with editable lists

USAGE IN XML VIEWS:
-------------------

1. Basic One2many usage:

<field name="order_line_ids" widget="x2many_numbered">
    <tree editable="bottom">
        <field name="product_id"/>
        <field name="quantity"/>
        <field name="price"/>
    </tree>
</field>

2. Many2many usage:

<field name="tag_ids" widget="many2many_numbered">
    <tree>
        <field name="name"/>
        <field name="color"/>
    </tree>
</field>

3. With other options:

<field name="invoice_line_ids" widget="one2many_numbered" context="{'default_type': 'out_invoice'}">
    <tree editable="top" decoration-info="qty &gt; 0">
        <field name="product_id"/>
        <field name="qty"/>
        <field name="price_unit"/>
        <field name="price_subtotal"/>
    </tree>
</field>

WIDGET NAMES:
-------------
You can use any of these widget names (they're all the same):
- x2many_numbered
- one2many_numbered
- many2many_numbered

EXAMPLE IN DOCUMENT EXTRACTION MODULE:
--------------------------------------

<field name="substance_usage_production_ids" widget="x2many_numbered">
    <tree editable="bottom">
        <field name="substance_id"/>
        <field name="year_1_quantity_kg"/>
        <field name="year_2_quantity_kg"/>
    </tree>
</field>

STYLING CUSTOMIZATION:
----------------------
The widget uses these CSS classes:
- .o_field_x2many_numbered - Main container
- .o_list_number_th - Header cell for "#" column
- .o_list_number - Body cells for numbers

You can override styling in your module's SCSS:

.o_field_x2many_numbered .o_list_number {
    background-color: #f0f0f0;
    font-weight: bold;
}

NOTES:
------
- The "#" column is always the first column
- Numbers are 1-indexed (start from 1)
- The column width is fixed at 50px
- Numbers update automatically, no manual intervention needed
