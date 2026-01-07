# -*- coding: utf-8 -*-

from odoo import models, fields, api


class EquipmentOwnershipReport(models.Model):
    """Table 2.3: Equipment Ownership Report (Form 02)"""
    _name = 'equipment.ownership.report'
    _inherit = ['equipment.capacity.mixin']
    _description = 'Equipment Ownership Report'
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
        help='If True, this row is a section title (Air Conditioner/Refrigeration)'
    )
    ownership_type = fields.Selection(
        selection=[
            ('air_conditioner', 'Air Conditioner'),
            ('refrigeration', 'Refrigeration')
        ],
        string='Ownership Type',
        required=False,
        index=True,
        help='Type of equipment ownership. Auto-filled by AI extraction if available.'
    )
    equipment_type_id = fields.Many2one('equipment.type', string='Equipment Type', ondelete='restrict', index=True)
    equipment_type = fields.Char(string='Equipment Type Text', compute='_compute_equipment_type', store=True, readonly=False)
    equipment_quantity = fields.Integer(string='Quantity')
    substance_id = fields.Many2one('controlled.substance', string='Controlled Substance', ondelete='restrict', index=True)
    substance_name = fields.Char(string='Substance Name', compute='_compute_substance_name', store=True, readonly=False)
    capacity = fields.Char(string='Cooling Capacity/Power Capacity', help='Combined capacity when PDF has merged column (e.g., "5 HP/3.5 kW"). Only use when is_capacity_merged = True.')
    cooling_capacity = fields.Char(string='Cooling Capacity', help='Cooling capacity with unit (e.g., 5 HP, 10 kW, 18000 BTU). Extract value AND unit from PDF.')
    power_capacity = fields.Char(string='Power Capacity', help='Power capacity with unit (e.g., 3.5 kW, 2.5 HP). Extract value AND unit from PDF.')
    start_year = fields.Integer(string='Year Started')
    refill_frequency = fields.Char(string='Refill Frequency (times/year)')
    substance_quantity_per_refill = fields.Char(string='Substance Quantity per Refill')
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
        """Override create to auto-create master data if not exists and normalize capacity"""
        for vals in vals_list:
            # Normalize capacity (from mixin will be called via super)

            if vals.get('is_title'):
                continue
            if not vals.get('equipment_type_id') and vals.get('equipment_type'):
                vals['equipment_type_id'] = self._find_or_create('equipment.type', vals['equipment_type']).id

        # Super call will trigger mixin's create which normalizes capacity
        return super(EquipmentOwnershipReport, self).create(vals_list)

    def _find_or_create(self, model, text):
        text = text.strip()
        rec = self.env[model].search(['|', ('name', '=ilike', text), ('code', '=ilike', text)], limit=1)
        return rec or self.env[model].create({'name': text, 'code': text, 'active': True, 'needs_review': True, 'created_from_extraction': True})
