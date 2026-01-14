# -*- coding: utf-8 -*-

from odoo import models, fields, api
from .document_extraction import auto_detect_title_selection


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
        string='Activity',
        required=False,
        index=True,
        help='Type of equipment ownership. Auto-filled by AI extraction if available.'
    )
    equipment_type_id = fields.Many2one('equipment.type', string='Equipment Type', ondelete='restrict', index=True)
    equipment_type = fields.Char(string='Equipment Type', help='Title text for section headers (air conditioner/refrigeration)')
    equipment_quantity = fields.Integer(string='Quantity')
    substance_id = fields.Many2one('controlled.substance', string='Controlled Substance', ondelete='restrict', index=True)
    substance_name = fields.Char(string='Substance Name', compute='_compute_substance_name', store=True, readonly=False)
    capacity = fields.Char(string='Cooling Capacity/Power Capacity', help='Combined capacity when PDF has merged column (e.g., "5 HP/3.5 kW"). Only use when is_capacity_merged = True.')
    cooling_capacity = fields.Char(string='Cooling Capacity', help='Cooling capacity with unit (e.g., 5 HP, 10 kW, 18000 BTU). Extract value AND unit from PDF.')
    power_capacity = fields.Char(string='Power Capacity', help='Power capacity with unit (e.g., 3.5 kW, 2.5 HP). Extract value AND unit from PDF.')
    start_year = fields.Integer(string='Year Started', aggregator=False)
    refill_frequency = fields.Char(string='Refill Frequency (times/year)')
    substance_quantity_per_refill = fields.Char(string='Substance Quantity per Refill')
    notes = fields.Text(string='Notes')

    @api.depends('substance_id')
    def _compute_substance_name(self):
        for r in self:
            r.substance_name = r.substance_id.name if r.substance_id else ''

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to auto-create master data if not exists and normalize capacity"""
        
        for vals in vals_list:
            # Auto-detect selection for title rows
            if vals.get('is_title'):
                text_value = vals.get('equipment_type', '')
                current_value = vals.get('ownership_type')
                
                detected_value = auto_detect_title_selection(
                    'equipment.ownership.report',
                    text_value,
                    current_value
                )
                
                if detected_value:
                    vals['ownership_type'] = detected_value
                
                continue  # Skip master data creation for title rows
            
            # TODO-TITLE: Handle Equipment Type auto-creation (commented for now, will be handled later)
            # if not vals.get('equipment_type_id') and vals.get('equipment_type'):
            #     vals['equipment_type_id'] = self._find_or_create('equipment.type', vals['equipment_type']).id

        # Super call will trigger mixin's create which normalizes capacity
        return super(EquipmentOwnershipReport, self).create(vals_list)

    def write(self, vals):
        """Override write to auto-detect selection for title rows"""
        title_records = self.env['equipment.ownership.report']
        non_title_records = self.env['equipment.ownership.report']
        
        for record in self:
            is_title = vals.get('is_title', record.is_title)
            
            if is_title:
                title_records |= record
            else:
                non_title_records |= record
        
        # Process title records individually
        for record in title_records:
            text_value = vals.get('equipment_type', record.equipment_type)
            current_value = vals.get('ownership_type', record.ownership_type)
            
            detected_value = auto_detect_title_selection(
                'equipment.ownership.report',
                text_value,
                current_value
            )
            
            if detected_value:
                # Create copy of vals for this record
                record_vals = vals.copy()
                record_vals['ownership_type'] = detected_value
                super(EquipmentOwnershipReport, record).write(record_vals)
            else:
                super(EquipmentOwnershipReport, record).write(vals)
        
        # Process non-title records in batch
        if non_title_records:
            super(EquipmentOwnershipReport, non_title_records).write(vals)
        
        return True

    def _find_or_create(self, model, text):
        text = text.strip()
        rec = self.env[model].search(['|', ('name', '=ilike', text), ('code', '=ilike', text)], limit=1)
        return rec or self.env[model].create({'name': text, 'code': text, 'active': True, 'needs_review': True, 'created_from_extraction': True})
