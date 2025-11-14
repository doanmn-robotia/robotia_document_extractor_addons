# -*- coding: utf-8 -*-

from odoo import models, fields


class EquipmentProduct(models.Model):
    """Table 1.2: Equipment/Product Info"""
    _name = 'equipment.product'
    _description = 'Equipment/Product Info'
    _order = 'document_id, sequence, id'

    document_id = fields.Many2one(
        comodel_name='document.extraction',
        string='Document',
        required=True,
        ondelete='cascade',
        index=True
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help='Used to order rows'
    )
    is_title = fields.Boolean(
        string='Is Title Row',
        default=False,
        help='If True, this row is a section title'
    )
    product_type = fields.Char(
        string='Product/Equipment Type',
        help='Equipment model number and manufacturer'
    )
    hs_code = fields.Char(
        string='HS Code'
    )
    capacity = fields.Char(
        string='Cooling Capacity/Power'
    )
    quantity = fields.Float(
        string='Quantity'
    )
    substance_name = fields.Char(
        string='Controlled Substance'
    )
    substance_quantity_per_unit = fields.Float(
        string='Substance Quantity per Unit'
    )
    notes = fields.Text(
        string='Notes'
    )
