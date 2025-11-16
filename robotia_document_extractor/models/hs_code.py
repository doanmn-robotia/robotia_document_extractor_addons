# -*- coding: utf-8 -*-

from odoo import models, fields, api


class HSCode(models.Model):
    """Master data for Harmonized System (HS) codes"""
    _name = 'hs.code'
    _description = 'Harmonized System Code'
    _rec_name = 'code'
    _order = 'code'

    code = fields.Char(
        string='HS Code',
        required=True,
        index=True,
        size=12,
        help='Harmonized System code (e.g., 2903.39.90)'
    )
    name = fields.Char(
        string='Description',
        required=True,
        help='Product description'
    )
    product_category = fields.Char(
        string='Product Category',
        help='General product category'
    )
    chapter = fields.Char(
        string='Chapter (2 digits)',
        compute='_compute_chapter',
        store=True,
        help='HS Chapter (first 2 digits)'
    )
    controlled_substance_ids = fields.Many2many(
        comodel_name='controlled.substance',
        relation='hs_code_controlled_substance_rel',
        column1='hs_code_id',
        column2='substance_id',
        string='Related Controlled Substances',
        help='Substances typically associated with this HS code'
    )
    active = fields.Boolean(
        string='Active',
        default=True
    )
    needs_review = fields.Boolean(
        string='Needs Review',
        default=False,
        help='Auto-created record that needs admin review'
    )
    created_from_extraction = fields.Boolean(
        string='Created from Extraction',
        default=False,
        help='Created automatically during document extraction'
    )

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'HS Code must be unique!')
    ]

    @api.depends('code')
    def _compute_chapter(self):
        """Extract chapter (first 2 digits) from HS code"""
        for record in self:
            record.chapter = record.code[:2] if record.code and len(record.code) >= 2 else ''

    @api.model
    def name_create(self, name):
        """Override name_create to set created_from_extraction flag"""
        record = self.create({
            'code': name,
            'name': name,  # Use code as name initially
            'needs_review': True,
            'created_from_extraction': True
        })
        return record.id, record.display_name
