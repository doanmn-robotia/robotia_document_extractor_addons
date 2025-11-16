# -*- coding: utf-8 -*-

from odoo import models, fields, api


class RecyclingTechnology(models.Model):
    """Master data for recycling/recovery technologies"""
    _name = 'recycling.technology'
    _description = 'Recycling/Recovery Technology'
    _order = 'sequence, name'

    name = fields.Char(
        string='Technology Name',
        required=True,
        index=True,
        help='Name of recycling/recovery technology (e.g., Recovery Unit A1, Plasma, Incinerator)'
    )
    code = fields.Char(
        string='Code',
        index=True,
        help='Short code for technology'
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help='Display order'
    )
    technology_type = fields.Selection(
        selection=[
            ('collection', 'Collection/Recovery'),
            ('reuse', 'Reuse'),
            ('recycle', 'Recycling'),
            ('disposal', 'Disposal/Destruction')
        ],
        string='Technology Type',
        required=True,
        default='recycle',
        help='Type of recovery/recycling process'
    )
    description = fields.Text(
        string='Description',
        help='Detailed description of technology'
    )
    efficiency_rate = fields.Float(
        string='Efficiency Rate (%)',
        help='Recovery/recycling efficiency percentage'
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
