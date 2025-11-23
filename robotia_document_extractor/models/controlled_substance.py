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
    hs_code_id = fields.Many2one(
        comodel_name='hs.code',
        string='HS Code',
        ondelete='restrict',
        index=True,
        help='Harmonized System Code for customs/trade classification'
    )
    sub_hs_code_ids = fields.Many2many(
        comodel_name='hs.code',
        relation='controlled_substance_sub_hs_code_rel',
        column1='substance_id',
        column2='hs_code_id',
        string='Alternative HS Codes',
        help='Alternative HS codes for this substance. Used in fuzzy search when primary HS code does not match.'
    )
    hs_code_display = fields.Char(
        string='HS Code (Display)',
        compute='_compute_hs_code_display',
        store=True,
        readonly=True,
        help='HS Code for display purposes, including alternatives'
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
    substance_group_id = fields.Many2one(
        comodel_name='substance.group',
        string='Substance Group',
        ondelete='restrict',
        index=True,
        help='Group classification (HFC, HCFC, CFC, PFC, HFO, etc.)'
    )
    active = fields.Boolean(
        string='Active',
        default=True
    )
    needs_review = fields.Boolean(
        string='Needs Review',
        default=False,
        help='Auto-created substance that needs admin review and GWP configuration'
    )
    created_from_extraction = fields.Boolean(
        string='Created from Extraction',
        default=False,
        help='Created automatically during document extraction'
    )

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'The substance code must be unique!')
    ]

    @api.depends('hs_code_id', 'sub_hs_code_ids')
    def _compute_hs_code_display(self):
        """Compute HS code display with primary and alternative codes"""
        for record in self:
            if record.hs_code_id:
                display = record.hs_code_id.code
                if record.sub_hs_code_ids:
                    alt_codes = ', '.join(record.sub_hs_code_ids.mapped('code'))
                    display = f"{display} (Alt: {alt_codes})"
                record.hs_code_display = display
            else:
                record.hs_code_display = False

    @api.model
    def name_create(self, name):
        """Override name_create to set created_from_extraction flag"""
        record = self.create({
            'name': name,
            'code': name,  # Use name as code initially
            'needs_review': True,
            'created_from_extraction': True
        })
        return record.id, record.display_name

    def action_view_dashboard(self):
        """Open substance dashboard with analytics"""
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'document_extractor.substance_dashboard',
            'context': {
                'default_substance_id': self.id,
                'default_substance_name': self.name,
            },
            'name': f'Dashboard - {self.name}'
        }
