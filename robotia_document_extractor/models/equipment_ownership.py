# -*- coding: utf-8 -*-

from odoo import models, fields


class EquipmentOwnership(models.Model):
    """Table 1.3: Equipment Ownership"""
    _name = 'equipment.ownership'
    _description = 'Equipment Ownership'
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
    equipment_type = fields.Char(
        string='Equipment Type',
        help='Equipment model and manufacturer'
    )
    start_year = fields.Integer(
        string='Year Started'
    )
    capacity = fields.Char(
        string='Cooling Capacity/Power'
    )
    equipment_quantity = fields.Integer(
        string='Quantity'
    )
    substance_name = fields.Char(
        string='Controlled Substance'
    )
    refill_frequency = fields.Float(
        string='Refill Frequency (times/year)'
    )
    substance_quantity_per_refill = fields.Float(
        string='Substance Quantity per Refill'
    )
