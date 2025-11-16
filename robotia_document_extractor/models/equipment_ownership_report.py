# -*- coding: utf-8 -*-

from odoo import models, fields, api


class EquipmentOwnershipReport(models.Model):
    """Table 2.3: Equipment Ownership Report (Form 02)"""
    _name = 'equipment.ownership.report'
    _description = 'Equipment Ownership Report'
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
        help='If True, this row is a section title (Air Conditioner/Refrigeration)'
    )
    ownership_type = fields.Selection(
        selection=[
            ('air_conditioner', 'Air Conditioner'),
            ('refrigeration', 'Refrigeration')
        ],
        string='Ownership Type',
        required=True,
        index=True
    )
    equipment_type_id = fields.Many2one('equipment.type', string='Equipment Type', ondelete='restrict', index=True)
    equipment_type = fields.Char(string='Equipment Type Text', compute='_compute_equipment_type', store=True, readonly=False)
    equipment_quantity = fields.Integer(string='Quantity')
    substance_id = fields.Many2one('controlled.substance', string='Controlled Substance', ondelete='restrict', index=True)
    substance_name = fields.Char(string='Substance Name', compute='_compute_substance_name', store=True, readonly=False)
    capacity = fields.Char(string='Cooling Capacity/Power')
    start_year = fields.Integer(string='Year Started')
    refill_frequency = fields.Float(string='Refill Frequency (times/year)')
    substance_quantity_per_refill = fields.Float(string='Substance Quantity per Refill')
    notes = fields.Text(string='Notes')

    @api.depends('equipment_type_id')
    def _compute_equipment_type(self):
        for r in self:
            r.equipment_type = r.equipment_type_id.name if r.equipment_type_id else ''

    @api.depends('substance_id')
    def _compute_substance_name(self):
        for r in self:
            r.substance_name = r.substance_id.name if r.substance_id else ''

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('is_title'):
                continue
            if not vals.get('substance_id') and vals.get('substance_name'):
                vals['substance_id'] = self._find_or_create('controlled.substance', vals['substance_name']).id
            if not vals.get('equipment_type_id') and vals.get('equipment_type'):
                vals['equipment_type_id'] = self._find_or_create('equipment.type', vals['equipment_type']).id
        return super(EquipmentOwnershipReport, self).create(vals_list)

    def _find_or_create(self, model, text):
        text = text.strip()
        rec = self.env[model].search(['|', ('name', '=ilike', text), ('code', '=ilike', text)], limit=1)
        return rec or self.env[model].create({'name': text, 'code': text, 'active': True, 'needs_review': True, 'created_from_extraction': True})
