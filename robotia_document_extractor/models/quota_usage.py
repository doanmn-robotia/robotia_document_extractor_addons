# -*- coding: utf-8 -*-

from odoo import models, fields, api


class QuotaUsage(models.Model):
    """Table 2.1: Quota Usage Report (Form 02 only)"""
    _name = 'quota.usage'
    _description = 'Quota Usage'
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
    export_import_location = fields.Char(
        string='Export/Import Location'
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
    trade_location_id = fields.Many2one('trade.location', string='Export/Import Location Link', ondelete='restrict')
    export_import_location_text = fields.Char(compute='_compute_location_text', store=True, readonly=False)

    @api.depends('substance_id')
    def _compute_substance_name(self):
        for r in self:
            r.substance_name = r.substance_id.name if r.substance_id else ''

    @api.depends('hs_code_id')
    def _compute_hs_code(self):
        for r in self:
            r.hs_code = r.hs_code_id.code if r.hs_code_id else ''

    @api.depends('trade_location_id')
    def _compute_location_text(self):
        for r in self:
            r.export_import_location_text = r.trade_location_id.name if r.trade_location_id else r.export_import_location or ''

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('is_title'):
                continue
            if not vals.get('substance_id') and vals.get('substance_name'):
                vals['substance_id'] = self._find_or_create_substance(vals['substance_name']).id
            if not vals.get('hs_code_id') and vals.get('hs_code'):
                vals['hs_code_id'] = self._find_or_create_hs_code(vals['hs_code']).id
            if not vals.get('trade_location_id') and vals.get('export_import_location'):
                vals['trade_location_id'] = self._find_or_create_trade_location(vals['export_import_location']).id
        return super(QuotaUsage, self).create(vals_list)

    def _find_or_create_substance(self, text):
        text = text.strip()
        rec = self.env['controlled.substance'].search(['|', ('name', '=ilike', text), ('code', '=ilike', text)], limit=1)
        return rec or self.env['controlled.substance'].create({'name': text, 'code': text, 'active': True, 'needs_review': True, 'created_from_extraction': True})

    def _find_or_create_hs_code(self, text):
        text = text.strip()
        rec = self.env['hs.code'].search([('code', '=', text)], limit=1)
        return rec or self.env['hs.code'].create({'code': text, 'name': text, 'active': True, 'needs_review': True, 'created_from_extraction': True})

    def _find_or_create_trade_location(self, text):
        text = text.strip()
        rec = self.env['trade.location'].search([('name', '=ilike', text)], limit=1)
        return rec or self.env['trade.location'].create({'name': text, 'code': text, 'needs_review': True, 'created_from_extraction': True})
