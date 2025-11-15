# -*- coding: utf-8 -*-

from odoo import models, fields


class EquipmentOwnershipReport(models.Model):
    """Table 2.3: Equipment Ownership Report (Form 02)"""
    _name = 'equipment.ownership.report'
    _description = 'Equipment Ownership Report'
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
        help='Used to order rows (title rows first in each section)'
    )
    is_title = fields.Boolean(
        string='Is Title Row',
        default=False,
        help='If True, this row is a section title (Air Conditioner/Refrigeration)'
    )
    ownership_type = fields.Selection(
        selection=[
            ('air_conditioner', 'Air Conditioner'),
            ('refrigeration', 'Refrigeration')
        ],
        string='Ownership Type',
        required=True,
        index=True
    )
    equipment_type = fields.Char(
        string='Equipment Type',
        help='For title rows, this contains the section name. For data rows, equipment model and manufacturer'
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
