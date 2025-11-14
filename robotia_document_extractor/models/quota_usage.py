# -*- coding: utf-8 -*-

from odoo import models, fields


class QuotaUsage(models.Model):
    """Table 2.1: Quota Usage Report (Form 02 only)"""
    _name = 'quota.usage'
    _description = 'Quota Usage'
    _order = 'document_id, substance_name'

    document_id = fields.Many2one(
        comodel_name='document.extraction',
        string='Document',
        required=True,
        ondelete='cascade',
        index=True
    )
    substance_name = fields.Char(
        string='Substance Name',
        required=True
    )
    hs_code = fields.Char(
        string='HS Code'
    )

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
        string='Total Quota (kg)'
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
