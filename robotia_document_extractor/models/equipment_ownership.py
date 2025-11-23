# -*- coding: utf-8 -*-

from odoo import models, fields, api


class EquipmentOwnership(models.Model):
    """Table 1.3: Equipment Ownership"""
    _name = 'equipment.ownership'
    _description = 'Equipment Ownership'
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
        help='Used to order rows'
    )
    is_title = fields.Boolean(
        string='Is Title Row',
        default=False,
        help='If True, this row is a section title'
    )
    equipment_type_id = fields.Many2one(
        comodel_name='equipment.type',
        string='Equipment Type',
        ondelete='restrict',
        index=True,
        help='Link to equipment type master data'
    )
    equipment_type = fields.Char(
        string='Equipment Type Text',
        compute='_compute_equipment_type',
        store=True,
        readonly=False,
        help='Equipment model and manufacturer (auto-filled from equipment_type_id)'
    )
    start_year = fields.Integer(
        string='Year Started'
    )
    cooling_capacity = fields.Char(
        string='Cooling Capacity'
    )
    power_capacity = fields.Char(
        string='Power Capacity'
    )
    equipment_quantity = fields.Integer(
        string='Quantity'
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
    refill_frequency = fields.Float(
        string='Refill Frequency (times/year)',
        digits=(16, 4)
    )
    substance_quantity_per_refill = fields.Float(
        string='Substance Quantity per Refill',
        digits=(16, 4)
    )

    @api.depends('equipment_type_id')
    def _compute_equipment_type(self):
        for record in self:
            if record.equipment_type_id:
                record.equipment_type = record.equipment_type_id.name

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

            # Handle Equipment Type
            if not vals.get('equipment_type_id') and vals.get('equipment_type'):
                equipment_type = self._find_or_create_equipment_type(vals.get('equipment_type'))
                vals['equipment_type_id'] = equipment_type.id

        return super(EquipmentOwnership, self).create(vals_list)

    def _find_or_create_equipment_type(self, type_text):
        type_text = type_text.strip()
        equipment_type = self.env['equipment.type'].search([
            '|', ('name', '=ilike', type_text), ('code', '=ilike', type_text)
        ], limit=1)
        if equipment_type:
            return equipment_type
        return self.env['equipment.type'].create({
            'name': type_text, 'code': type_text, 'active': True,
            'needs_review': True, 'created_from_extraction': True
        })
