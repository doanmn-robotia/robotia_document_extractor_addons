# -*- coding: utf-8 -*-

from odoo import models, fields, api


class EquipmentProduct(models.Model):
    """Table 1.2: Equipment/Product Info"""
    _name = 'equipment.product'
    _description = 'Equipment/Product Info'
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
    product_type = fields.Char(
        string='Product/Equipment Type',
        compute='_compute_product_type',
        store=True,
        readonly=False,
        help='Equipment model number and manufacturer (auto-filled from equipment_type_id)'
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
        string='Cooling Capacity/Power'
    )
    quantity = fields.Float(
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
    substance_quantity_per_unit = fields.Float(
        string='Substance Quantity per Unit'
    )
    notes = fields.Text(
        string='Notes'
    )

    @api.depends('equipment_type_id')
    def _compute_product_type(self):
        """Auto-fill product_type from equipment_type_id"""
        for record in self:
            if record.equipment_type_id:
                record.product_type = record.equipment_type_id.name

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
        """Override create to auto-create master data if not exists"""
        for vals in vals_list:
            if vals.get('is_title'):
                continue

            # 1. Handle Substance
            if not vals.get('substance_id') and vals.get('substance_name'):
                substance = self._find_or_create_substance(vals.get('substance_name'))
                vals['substance_id'] = substance.id

            # 2. Handle Equipment Type
            if not vals.get('equipment_type_id') and vals.get('product_type'):
                equipment_type = self._find_or_create_equipment_type(vals.get('product_type'))
                vals['equipment_type_id'] = equipment_type.id

            # 3. Handle HS Code
            if not vals.get('hs_code_id') and vals.get('hs_code'):
                hs_code = self._find_or_create_hs_code(vals.get('hs_code'))
                vals['hs_code_id'] = hs_code.id

        return super(EquipmentProduct, self).create(vals_list)

    def _find_or_create_substance(self, substance_text):
        """Search for substance, create if not found"""
        substance_text = substance_text.strip()
        substance = self.env['controlled.substance'].search([
            '|',
            ('name', '=ilike', substance_text),
            ('code', '=ilike', substance_text)
        ], limit=1)

        if substance:
            return substance

        return self.env['controlled.substance'].create({
            'name': substance_text,
            'code': substance_text,
            'active': True,
            'needs_review': True,
            'created_from_extraction': True
        })

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

    def _find_or_create_hs_code(self, code_text):
        """Search for HS code, create if not found"""
        code_text = code_text.strip()
        hs_code = self.env['hs.code'].search([('code', '=', code_text)], limit=1)

        if hs_code:
            return hs_code

        return self.env['hs.code'].create({
            'code': code_text,
            'name': code_text,  # Use code as name initially
            'active': True,
            'needs_review': True,
            'created_from_extraction': True
        })
