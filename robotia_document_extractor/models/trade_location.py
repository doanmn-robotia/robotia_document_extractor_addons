# -*- coding: utf-8 -*-

from odoo import models, fields, api


class TradeLocation(models.Model):
    """Master data for import/export locations (ports, customs, borders)"""
    _name = 'trade.location'
    _description = 'Import/Export Location (Port/Customs)'
    _rec_name = 'name'
    _order = 'country_id, name'

    name = fields.Char(
        string='Location Name',
        required=True,
        index=True,
        help='Name of port, airport, or customs office'
    )
    code = fields.Char(
        string='Code',
        index=True,
        help='Short code or UN/LOCODE'
    )
    location_type = fields.Selection(
        selection=[
            ('port', 'Seaport'),
            ('airport', 'Airport'),
            ('border', 'Land Border Crossing'),
            ('customs', 'Customs Office')
        ],
        string='Type',
        help='Type of import/export location'
    )
    country_id = fields.Many2one(
        comodel_name='res.country',
        string='Country',
        required=True,
        help='Country where location is situated'
    )
    city = fields.Char(
        string='City',
        help='City or region'
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
        # Default to Vietnam if no country specified
        default_country = self.env.ref('base.vn', raise_if_not_found=False)

        record = self.create({
            'name': name,
            'code': name,
            'country_id': default_country.id if default_country else False,
            'needs_review': True,
            'created_from_extraction': True
        })
        return record.id, record.display_name
