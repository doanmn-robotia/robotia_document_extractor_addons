# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class QuotaUsage(models.Model):
    """Table 2.1: Quota Usage Report (Form 02 only)"""
    _name = 'quota.usage'
    _description = 'Quota Usage'
    _order = 'sequence, id'

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
        default="import",
        index=True
    )
    substance_id = fields.Many2one('controlled.substance', string='Controlled Substance', ondelete='cascade', index=True)
    substance_name = fields.Char(string='Substance Name', compute='_compute_substance_name', store=True, readonly=False, index=True)
    hs_code_id = fields.Many2one('hs.code', string='HS Code', ondelete='restrict', index=True)
    hs_code = fields.Char(string='HS Code Text', compute='_compute_hs_code', store=True, readonly=False)

    # Allocated Quota
    allocated_quota_kg = fields.Float(
        string='Allocated Quota (kg)',
        digits=(16, 4)
    )
    allocated_quota_co2 = fields.Float(
        string='Allocated Quota (ton CO2)',
        digits=(16, 4)
    )

    # Adjusted Quota
    adjusted_quota_kg = fields.Float(
        string='Adjusted Quota (kg)',
        digits=(16, 4)
    )
    adjusted_quota_co2 = fields.Float(
        string='Adjusted Quota (ton CO2)',
        digits=(16, 4)
    )

    # Total Quota Usage
    total_quota_kg = fields.Float(
        string='Total Quota (kg)',
        digits=(16, 4),
        index=True  # Add index for sorting/filtering in dashboards
    )
    total_quota_co2 = fields.Float(
        string='Total Quota (ton CO2)',
        digits=(16, 4)
    )
    average_price = fields.Float(
        string='Average Price',
        digits=(16, 4)
    )
    country_text = fields.Char(
        string='Export/Import Country',
        help='Country for import/export trade (ISO code)'
    )
    customs_declaration_number = fields.Char(
        string='Customs Declaration Number'
    )

    # Next Year Registration
    next_year_quota_kg = fields.Float(
        string='Next Year Quota (kg)',
        digits=(16, 4)
    )
    next_year_quota_co2 = fields.Float(
        string='Next Year Quota (ton CO2)',
        digits=(16, 4)
    )

    # SQL Constraints for data validation
    _sql_constraints = [
        ('allocated_quota_kg_positive',
         'CHECK(allocated_quota_kg IS NULL OR allocated_quota_kg >= 0)',
         'Allocated quota (kg) must be positive or null'),
        ('adjusted_quota_kg_check',
         'CHECK(adjusted_quota_kg IS NULL OR TRUE)',  # Can be positive or negative
         'Adjusted quota (kg) must be a valid number'),
        ('total_quota_kg_positive',
         'CHECK(total_quota_kg IS NULL OR total_quota_kg >= 0)',
         'Total quota (kg) must be positive or null'),
        ('allocated_quota_co2_positive',
         'CHECK(allocated_quota_co2 IS NULL OR allocated_quota_co2 >= 0)',
         'Allocated quota (CO2) must be positive or null'),
        ('total_quota_co2_positive',
         'CHECK(total_quota_co2 IS NULL OR total_quota_co2 >= 0)',
         'Total quota (CO2) must be positive or null'),
        ('average_price_positive',
         'CHECK(average_price IS NULL OR average_price >= 0)',
         'Average price must be positive or null'),
    ]

    @api.depends('substance_id')
    def _compute_substance_name(self):
        for r in self:
            r.substance_name = r.substance_id.name if r.substance_id else ''

    @api.depends('hs_code_id')
    def _compute_hs_code(self):
        for r in self:
            r.hs_code = r.hs_code_id.code if r.hs_code_id else ''
