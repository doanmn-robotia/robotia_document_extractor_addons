# -*- coding: utf-8 -*-

from odoo import models, fields, api


class EquipmentType(models.Model):
    """Master data for equipment types (Air conditioner, Refrigeration, etc.)"""
    _name = 'equipment.type'
    _description = 'Equipment Type Master'
    _order = 'sequence, name'

    name = fields.Char(
        string='Equipment Type Name',
        required=True,
        index=True,
        help='Name of equipment type (e.g., Air Conditioner, Industrial Refrigeration)'
    )
    code = fields.Char(
        string='Code',
        index=True,
        help='Short code for equipment type'
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help='Display order'
    )
    description = fields.Text(
        string='Description',
        help='Detailed description of this equipment type'
    )
    category = fields.Selection(
        selection=[
            ('ac', 'Air Conditioner'),
            ('refrigeration', 'Refrigeration'),
            ('industrial', 'Industrial Equipment'),
            ('other', 'Other')
        ],
        string='Category',
        help='Equipment category'
    )
    min_capacity = fields.Float(
        string='Min Capacity (kW)',
        help='Minimum cooling/heating capacity in kW'
    )
    max_capacity = fields.Float(
        string='Max Capacity (kW)',
        help='Maximum cooling/heating capacity in kW'
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
        ('code_unique', 'unique(code)', 'Equipment type code must be unique!')
    ]

    @api.model
    def name_create(self, name):
        """Override name_create to set created_from_extraction flag"""
        record = self.create({
            'name': name,
            'code': name,
            'needs_review': True,
            'created_from_extraction': True
        })
        return record.id, record.display_name

    def action_view_dashboard(self):
        """Open equipment type dashboard with analytics"""
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'document_extractor.equipment_dashboard',
            'context': {
                'default_equipment_type_id': self.id,
                'default_equipment_type_name': self.name,
            },
            'name': f'Dashboard - {self.name}'
        }
