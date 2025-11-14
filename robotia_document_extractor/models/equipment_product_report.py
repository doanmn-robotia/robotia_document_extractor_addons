# -*- coding: utf-8 -*-

from odoo import models, fields


class EquipmentProductReport(models.Model):
    """Table 2.2: Equipment/Product Report (Form 02) - Same structure as Table 1.2"""
    _name = 'equipment.product.report'
    _description = 'Equipment/Product Report'
    _order = 'document_id, product_type'

    document_id = fields.Many2one(
        comodel_name='document.extraction',
        string='Document',
        required=True,
        ondelete='cascade',
        index=True
    )
    product_type = fields.Char(
        string='Product/Equipment Type',
        required=True,
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
