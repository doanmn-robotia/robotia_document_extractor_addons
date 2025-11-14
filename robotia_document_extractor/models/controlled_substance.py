# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ControlledSubstance(models.Model):
    """Master data for controlled substances (HFC, HCFC, etc.)"""
    _name = 'controlled.substance'
    _description = 'Controlled Substance'
    _order = 'name'

    name = fields.Char(
        string='Substance Name',
        required=True,
        index=True
    )
    code = fields.Char(
        string='Code',
        index=True
    )
    formula = fields.Char(
        string='Chemical Formula'
    )
    cas_number = fields.Char(
        string='CAS Number'
    )
    form_type = fields.Selection(
        selection=[
            ('01', 'Form 01'),
            ('02', 'Form 02'),
            ('both', 'Both Forms')
        ],
        string='Form Type',
        default='both'
    )
    gwp = fields.Float(
        string='Global Warming Potential (GWP)',
        help='GWP value for CO2 equivalent calculation'
    )
    active = fields.Boolean(
        string='Active',
        default=True
    )

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'The substance code must be unique!')
    ]
