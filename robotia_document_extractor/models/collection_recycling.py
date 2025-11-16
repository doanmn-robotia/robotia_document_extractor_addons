# -*- coding: utf-8 -*-

from odoo import models, fields, api


class CollectionRecycling(models.Model):
    """Table 1.4: Collection, Recycling, Reuse, Disposal

    IMPORTANT: Uses activity_type field to group records.
    One row in PDF may create 4 records (collection, reuse, recycle, disposal)
    """
    _name = 'collection.recycling'
    _description = 'Collection & Recycling'
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
        help='If True, this row is a section title (Collection/Reuse/Recycle/Disposal)'
    )
    activity_type = fields.Selection(
        selection=[
            ('collection', 'Collection'),
            ('reuse', 'Reuse'),
            ('recycle', 'Recycle'),
            ('disposal', 'Disposal')
        ],
        string='Activity Type',
        required=True,
        index=True,
        help='Type of activity: Collection, Reuse, Recycle, or Disposal'
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
        help='Substance name (auto-filled from substance_id)'
    )
    quantity_kg = fields.Float(
        string='Quantity (kg)'
    )
    quantity_co2 = fields.Float(
        string='Quantity (ton CO2)'
    )

    @api.depends('substance_id')
    def _compute_substance_name(self):
        for record in self:
            if record.substance_id:
                record.substance_name = record.substance_id.name

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('is_title'):
                continue
            if not vals.get('substance_id') and vals.get('substance_name'):
                substance = self._find_or_create_substance(vals.get('substance_name'))
                vals['substance_id'] = substance.id
        return super(CollectionRecycling, self).create(vals_list)

    def _find_or_create_substance(self, substance_text):
        substance_text = substance_text.strip()
        substance = self.env['controlled.substance'].search([
            '|', ('name', '=ilike', substance_text), ('code', '=ilike', substance_text)
        ], limit=1)
        if substance:
            return substance
        return self.env['controlled.substance'].create({
            'name': substance_text, 'code': substance_text, 'active': True,
            'needs_review': True, 'created_from_extraction': True
        })
