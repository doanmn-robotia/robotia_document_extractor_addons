# -*- coding: utf-8 -*-

from odoo import models, fields


class SubstanceUsage(models.Model):
    """Table 1.1: Substance Usage (Production, Import, Export)"""
    _name = 'substance.usage'
    _description = 'Substance Usage'
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
        help='If True, this row is a section title (Production/Import/Export)'
    )
    usage_type = fields.Selection(
        selection=[
            ('production', 'Production'),
            ('import', 'Import'),
            ('export', 'Export')
        ],
        string='Usage Type',
        required=True,
        index=True
    )
    substance_name = fields.Char(
        string='Substance Name',
        help='For title rows, this contains the section name (e.g., "Sản xuất", "Nhập khẩu", "Xuất khẩu")'
    )

    # Year 1
    year_1_quantity_kg = fields.Float(
        string='Year 1 Quantity (kg)'
    )
    year_1_quantity_co2 = fields.Float(
        string='Year 1 Quantity (ton CO2)'
    )

    # Year 2
    year_2_quantity_kg = fields.Float(
        string='Year 2 Quantity (kg)'
    )
    year_2_quantity_co2 = fields.Float(
        string='Year 2 Quantity (ton CO2)'
    )

    # Year 3
    year_3_quantity_kg = fields.Float(
        string='Year 3 Quantity (kg)'
    )
    year_3_quantity_co2 = fields.Float(
        string='Year 3 Quantity (ton CO2)'
    )

    # Average
    avg_quantity_kg = fields.Float(
        string='Average Quantity (kg)'
    )
    avg_quantity_co2 = fields.Float(
        string='Average Quantity (ton CO2)'
    )
