# -*- coding: utf-8 -*-

import re
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
        translate=True,
        help='Product description'
    )
    product_category = fields.Char(
        string='Product Category',
        translate=True,
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
        string='Related Controlled Substances',
        compute='_compute_controlled_substance_ids',
        help='Substances using this HS code as main or sub HS code'
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

    def _normalize_code(self, hs_code_text):
        """
        Normalize HS code to standard 8-digit format.

        Handles various input formats:
        - "2903.45.00" -> "29034500"
        - "2903-45-00" -> "29034500"
        - "290345" -> "29034500" (pads with 00)
        - "2903.45" -> "29034500"

        Args:
            hs_code_text (str): HS code in any format

        Returns:
            str: Normalized 8-digit HS code, or original if invalid
        """
        if not hs_code_text:
            return hs_code_text

        # Remove dots, dashes, spaces
        cleaned = re.sub(r'[.\-\s]', '', str(hs_code_text).strip())

        # Keep only digits
        digits_only = re.sub(r'\D', '', cleaned)

        if not digits_only:
            return hs_code_text  # Return original if no digits found

        # Pad to 8 digits if shorter (e.g., "290345" -> "29034500")
        if len(digits_only) < 8:
            digits_only = digits_only.ljust(8, '0')

        # Truncate to 8 digits if longer
        return digits_only[:8]

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to normalize HS code before saving"""
        for vals in vals_list:
            if 'code' in vals:
                vals['code'] = self._normalize_code(vals['code'])
        return super(HSCode, self).create(vals_list)

    def write(self, vals):
        """Override write to normalize HS code on update"""
        if 'code' in vals:
            vals['code'] = self._normalize_code(vals['code'])
        return super(HSCode, self).write(vals)

    @api.depends('code')
    def _compute_chapter(self):
        """Extract chapter (first 2 digits) from HS code"""
        for record in self:
            record.chapter = record.code[:2] if record.code and len(record.code) >= 2 else ''

    def _compute_controlled_substance_ids(self):
        """
        Compute controlled substances that use this HS code.
        Includes substances where:
        - hs_code_id = this HS code (main HS code)
        - sub_hs_code_ids contains this HS code (sub HS codes)
        """
        for record in self:
            ControlledSubstance = self.env['controlled.substance']

            # Find substances with this HS code as main code
            substances_main = ControlledSubstance.search([
                ('hs_code_id', '=', record.id)
            ])

            # Find substances with this HS code in sub codes
            substances_sub = ControlledSubstance.search([
                ('sub_hs_code_ids', 'in', record.id)
            ])

            # Combine and remove duplicates
            record.controlled_substance_ids = substances_main | substances_sub

    @api.model
    def name_create(self, name):
        """Override name_create to set created_from_extraction flag and normalize code"""
        normalized_code = self._normalize_code(name)
        record = self.create({
            'code': normalized_code,
            'name': normalized_code,  # Use normalized code as name initially
            'needs_review': True,
            'created_from_extraction': True
        })
        return record.id, record.display_name
