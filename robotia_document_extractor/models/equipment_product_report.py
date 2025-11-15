# -*- coding: utf-8 -*-

from odoo import models, fields


class EquipmentProductReport(models.Model):
    """Table 2.2: Equipment/Product Report (Form 02) - Same structure as Table 1.2"""
    _name = 'equipment.product.report'
    _description = 'Equipment/Product Report'
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
        help='If True, this row is a section title (Production/Import)'
    )
    production_type = fields.Selection(
        selection=[
            ('production', 'Production'),
            ('import', 'Import')
        ],
        string='Production Type',
        required=True,
        index=True
    )
    product_type = fields.Char(
        string='Product/Equipment Type',
        help='For title rows, this contains the section name. For data rows, equipment model and manufacturer'
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
