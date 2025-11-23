# -*- coding: utf-8 -*-

from odoo import models, fields, api


class EquipmentProductReport(models.Model):
    """Table 2.2: Equipment/Product Report (Form 02) - Same structure as Table 1.2"""
    _name = 'equipment.product.report'
    _description = 'Equipment/Product Report'
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
        help='If True, this row is a section title (Production/Import)'
    )
    production_type = fields.Selection(
        selection=[
            ('production', 'Production'),
            ('import', 'Import')
        ],
        string='Production Type',
        required=True,
        index=True
    )
    equipment_type_id = fields.Many2one('equipment.type', string='Equipment Type', ondelete='restrict', index=True)
    product_type = fields.Char(string='Product/Equipment Type', compute='_compute_product_type', store=True, readonly=False)
    hs_code_id = fields.Many2one('hs.code', string='HS Code', ondelete='restrict', index=True)
    hs_code = fields.Char(string='HS Code Text', compute='_compute_hs_code', store=True, readonly=False)
    cooling_capacity = fields.Char(string='Cooling Capacity')
    power_capacity = fields.Char(string='Power Capacity')
    quantity = fields.Float(string='Quantity', digits=(16, 4))
    substance_id = fields.Many2one('controlled.substance', string='Controlled Substance', ondelete='restrict', index=True)
    substance_name = fields.Char(string='Substance Name', compute='_compute_substance_name', store=True, readonly=False)
    substance_quantity_per_unit = fields.Float(string='Substance Quantity per Unit', digits=(16, 4))
    notes = fields.Text(string='Notes')

    @api.depends('equipment_type_id')
    def _compute_product_type(self):
        for r in self:
            r.product_type = r.equipment_type_id.name if r.equipment_type_id else ''

    @api.depends('hs_code_id')
    def _compute_hs_code(self):
        for r in self:
            r.hs_code = r.hs_code_id.code if r.hs_code_id else ''

    @api.depends('substance_id')
    def _compute_substance_name(self):
        for r in self:
            r.substance_name = r.substance_id.name if r.substance_id else ''

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('is_title'):
                continue
            if not vals.get('equipment_type_id') and vals.get('product_type'):
                vals['equipment_type_id'] = self._find_or_create('equipment.type', vals['product_type']).id
        return super(EquipmentProductReport, self).create(vals_list)

    def _find_or_create(self, model, text):
        text = text.strip()
        rec = self.env[model].search(['|', ('name', '=ilike', text), ('code', '=ilike', text)], limit=1)
        return rec or self.env[model].create({'name': text, 'code': text, 'active': True, 'needs_review': True, 'created_from_extraction': True})


