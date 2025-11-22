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
        required=True,
        index=True
    )
    substance_id = fields.Many2one('controlled.substance', string='Controlled Substance', ondelete='cascade', index=True)
    substance_name = fields.Char(string='Substance Name', compute='_compute_substance_name', store=True, readonly=False, index=True)
    hs_code_id = fields.Many2one('hs.code', string='HS Code', ondelete='restrict', index=True)
    hs_code = fields.Char(string='HS Code Text', compute='_compute_hs_code', store=True, readonly=False)

    # Allocated Quota
    allocated_quota_kg = fields.Float(
        string='Allocated Quota (kg)'
    )
    allocated_quota_co2 = fields.Float(
        string='Allocated Quota (ton CO2)'
    )

    # Adjusted Quota
    adjusted_quota_kg = fields.Float(
        string='Adjusted Quota (kg)'
    )
    adjusted_quota_co2 = fields.Float(
        string='Adjusted Quota (ton CO2)'
    )

    # Total Quota Usage
    total_quota_kg = fields.Float(
        string='Total Quota (kg)',
        index=True  # Add index for sorting/filtering in dashboards
    )
    total_quota_co2 = fields.Float(
        string='Total Quota (ton CO2)'
    )
    average_price = fields.Float(
        string='Average Price'
    )
    country_id = fields.Many2one(
        comodel_name='res.country',
        string='Export/Import Country',
        ondelete='restrict',
        index=True,
        help='Country for import/export trade (ISO code)'
    )
    country_code = fields.Char(
        string='Country Code',
        compute='_compute_country_code',
        store=True,
        readonly=False,
        help='ISO 2-letter country code (e.g., VN, US, CN)'
    )
    customs_declaration_number = fields.Char(
        string='Customs Declaration Number'
    )

    # Next Year Registration
    next_year_quota_kg = fields.Float(
        string='Next Year Quota (kg)'
    )
    next_year_quota_co2 = fields.Float(
        string='Next Year Quota (ton CO2)'
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

    @api.depends('country_id')
    def _compute_country_code(self):
        for r in self:
            r.country_code = r.country_id.code if r.country_id else ''

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('is_title'):
                continue
            if not vals.get('hs_code_id') and vals.get('hs_code'):
                vals['hs_code_id'] = self._find_or_create_hs_code(vals['hs_code']).id
            if not vals.get('country_id') and vals.get('country_code'):
                vals['country_id'] = self._find_country_by_code(vals['country_code']).id
        return super(QuotaUsage, self).create(vals_list)

    def _find_or_create_hs_code(self, text):
        text = text.strip()
        rec = self.env['hs.code'].search([('code', '=', text)], limit=1)
        return rec or self.env['hs.code'].create({'code': text, 'name': text, 'active': True, 'needs_review': True, 'created_from_extraction': True})

    def _find_country_by_code(self, code):
        """
        Find country by ISO code (case-insensitive)

        Args:
            code (str): ISO 2-letter country code (e.g., 'VN', 'US', 'CN')

        Returns:
            res.country: Found country record or empty recordset
        """
        if not code:
            return self.env['res.country']

        code = code.strip().upper()
        # Search by code (case-insensitive)
        country = self.env['res.country'].search([('code', '=ilike', code)], limit=1)

        if not country:
            # Log warning if country code not found
            import logging
            _logger = logging.getLogger(__name__)
            _logger.warning(f"Country code '{code}' not found in system. Please check ISO country codes.")

        return country

