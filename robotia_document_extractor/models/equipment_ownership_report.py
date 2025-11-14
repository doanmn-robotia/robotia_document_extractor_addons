# -*- coding: utf-8 -*-

from odoo import models, fields


class EquipmentOwnershipReport(models.Model):
    """Table 2.3: Equipment Ownership Report (Form 02)"""
    _name = 'equipment.ownership.report'
    _description = 'Equipment Ownership Report'
    _order = 'document_id, equipment_type'

    document_id = fields.Many2one(
        comodel_name='document.extraction',
        string='Document',
        required=True,
        ondelete='cascade',
        index=True
    )
    equipment_type = fields.Char(
        string='Equipment Type',
        required=True,
        help='Equipment model and manufacturer'
    )
    equipment_quantity = fields.Integer(
        string='Quantity'
    )
    substance_name = fields.Char(
        string='Controlled Substance'
    )
    capacity = fields.Char(
        string='Cooling Capacity/Power'
    )
    start_year = fields.Integer(
        string='Year Started'
    )
    refill_frequency = fields.Float(
        string='Refill Frequency (times/year)'
    )
    substance_quantity_per_refill = fields.Float(
        string='Substance Quantity per Refill'
    )
    notes = fields.Text(
        string='Notes'
    )
