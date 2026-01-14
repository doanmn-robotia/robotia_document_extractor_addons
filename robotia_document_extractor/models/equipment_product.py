# -*- coding: utf-8 -*-

from odoo import models, fields, api
from .document_extraction import auto_detect_title_selection


class EquipmentProduct(models.Model):
    """Table 1.2: Equipment/Product Info"""
    _name = 'equipment.product'
    _inherit = ['equipment.capacity.mixin']
    _description = 'Equipment/Product Info'
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
    production_type = fields.Selection(
        selection=[
            ('production', 'Sản xuất'),
            ('import', 'Nhập khẩu'),
        ],
        string='Activity',
        index=True,
        help='Production or Import equipment category'
    )
    equipment_type_id = fields.Many2one(
        comodel_name='equipment.type',
        string='Equipment Type',
        ondelete='restrict',
        index=True,
        help='Link to equipment type master data'
    )
    product_type = fields.Char(
        string='Product/Equipment Type',
        help='Title text for section headers (production/import equipment)'
    )
    hs_code_id = fields.Many2one(
        comodel_name='hs.code',
        string='HS Code',
        ondelete='restrict',
        index=True,
        help='Link to HS code master data'
    )
    hs_code = fields.Char(
        string='HS Code Text',
        compute='_compute_hs_code',
        store=True,
        readonly=False,
        help='HS code (auto-filled from hs_code_id)'
    )
    capacity = fields.Char(
        string='Cooling Capacity/Power Capacity',
        help='Combined capacity when PDF has merged column (e.g., "5 HP/3.5 kW"). Only use when is_capacity_merged = True.'
    )
    cooling_capacity = fields.Char(
        string='Cooling Capacity',
        help='Cooling capacity with unit (e.g., 5 HP, 10 kW, 18000 BTU). Extract value AND unit from PDF.'
    )
    power_capacity = fields.Char(
        string='Power Capacity',
        help='Power capacity with unit (e.g., 3.5 kW, 2.5 HP). Extract value AND unit from PDF.'
    )
    quantity = fields.Float(
        string='Quantity',
        digits=(16, 4)
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
    substance_quantity_per_unit = fields.Char(
        string='Substance Quantity per Unit',
        help='Substance quantity per unit - supports both numeric and text values (e.g., "100", "10-15", "N/A")'
    )
    notes = fields.Text(
        string='Notes'
    )

    @api.depends('hs_code_id')
    def _compute_hs_code(self):
        """Auto-fill hs_code from hs_code_id"""
        for record in self:
            if record.hs_code_id:
                record.hs_code = record.hs_code_id.code

    @api.depends('substance_id')
    def _compute_substance_name(self):
        """Auto-fill substance_name from substance_id"""
        for record in self:
            if record.substance_id:
                record.substance_name = record.substance_id.name

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to auto-create master data if not exists and normalize capacity"""
        
        for vals in vals_list:
            # Auto-detect selection for title rows
            if vals.get('is_title'):
                text_value = vals.get('product_type', '')
                current_value = vals.get('production_type')
                
                detected_value = auto_detect_title_selection(
                    'equipment.product',
                    text_value,
                    current_value
                )
                
                if detected_value:
                    vals['production_type'] = detected_value
                
                continue  # Skip master data creation for title rows

            # TODO-TITLE: Handle Equipment Type auto-creation (commented for now, will be handled later)
            # if not vals.get('equipment_type_id') and vals.get('product_type'):
            #     equipment_type = self._find_or_create_equipment_type(vals.get('product_type'))
            #     vals['equipment_type_id'] = equipment_type.id

        # Super call will trigger mixin's create which normalizes capacity
        return super(EquipmentProduct, self).create(vals_list)

    def write(self, vals):
        """Override write to auto-detect selection for title rows"""
        title_records = self.env['equipment.product']
        non_title_records = self.env['equipment.product']
        
        for record in self:
            is_title = vals.get('is_title', record.is_title)
            
            if is_title:
                title_records |= record
            else:
                non_title_records |= record
        
        # Process title records individually
        for record in title_records:
            text_value = vals.get('product_type', record.product_type)
            current_value = vals.get('production_type', record.production_type)
            
            detected_value = auto_detect_title_selection(
                'equipment.product',
                text_value,
                current_value
            )
            
            if detected_value:
                # Create copy of vals for this record
                record_vals = vals.copy()
                record_vals['production_type'] = detected_value
                super(EquipmentProduct, record).write(record_vals)
            else:
                super(EquipmentProduct, record).write(vals)
        
        # Process non-title records in batch
        if non_title_records:
            super(EquipmentProduct, non_title_records).write(vals)
        
        return True

    def _find_or_create_equipment_type(self, type_text):
        """Search for equipment type, create if not found"""
        type_text = type_text.strip()
        equipment_type = self.env['equipment.type'].search([
            '|',
            ('name', '=ilike', type_text),
            ('code', '=ilike', type_text)
        ], limit=1)

        if equipment_type:
            return equipment_type

        return self.env['equipment.type'].create({
            'name': type_text,
            'code': type_text,
            'active': True,
            'needs_review': True,
            'created_from_extraction': True
        })

