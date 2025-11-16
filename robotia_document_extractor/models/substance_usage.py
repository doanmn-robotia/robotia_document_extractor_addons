# -*- coding: utf-8 -*-

from odoo import models, fields, api


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
    substance_id = fields.Many2one(
        comodel_name='controlled.substance',
        string='Controlled Substance',
        ondelete='restrict',
        index=True,
        help='Link to controlled substance master data'
    )
    substance_name = fields.Char(
        string='Substance Name',
        compute='_compute_substance_name',
        store=True,
        readonly=False,
        index=True,  # Add index for frequent filtering/searching
        help='Substance name (auto-filled from substance_id or manually entered)'
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

    @api.depends('substance_id')
    def _compute_substance_name(self):
        """Auto-fill substance_name from substance_id"""
        for record in self:
            if record.substance_id:
                record.substance_name = record.substance_id.name

    @api.model_create_multi
    def create(self, vals_list):
        """
        Override create to auto-create controlled.substance if not exists

        Logic (similar to organization):
        - If substance_id empty but substance_name exists:
          - Search controlled.substance by name (case insensitive)
          - If found → set substance_id
          - If not found → create new substance → set substance_id
        """
        for vals in vals_list:
            # Skip title rows (they don't represent actual substances)
            if vals.get('is_title'):
                continue

            if not vals.get('substance_id') and vals.get('substance_name'):
                substance_name = vals.get('substance_name').strip()

                # Search existing substance by name or code (case insensitive)
                substance = self.env['controlled.substance'].search([
                    '|',
                    ('name', '=ilike', substance_name),
                    ('code', '=ilike', substance_name)
                ], limit=1)

                if substance:
                    # Substance found → use it
                    vals['substance_id'] = substance.id
                else:
                    # Substance not found → create new
                    substance_vals = {
                        'name': substance_name,
                        'code': substance_name,  # Use name as code initially
                        'active': True,
                        'needs_review': True,
                        'created_from_extraction': True
                    }
                    new_substance = self.env['controlled.substance'].create(substance_vals)
                    vals['substance_id'] = new_substance.id

        return super(SubstanceUsage, self).create(vals_list)
