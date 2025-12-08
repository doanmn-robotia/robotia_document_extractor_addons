# -*- coding: utf-8 -*-

from odoo import models, fields, api


class CollectionLocation(models.Model):
    """Master data for collection/storage locations"""
    _name = 'collection.location'
    _description = 'Collection/Storage Location'
    _rec_name = 'name'
    _order = 'city, name'

    name = fields.Char(
        string='Location Name',
        required=True,
        index=True,
        help='Name of collection or storage location'
    )
    code = fields.Char(
        string='Code',
        index=True,
        help='Short code for location'
    )
    location_type = fields.Selection(
        selection=[
            ('collection', 'Collection Point'),
            ('storage', 'Storage Facility'),
            ('processing', 'Processing Site')
        ],
        string='Location Type',
        help='Type of location'
    )
    address = fields.Char(
        string='Address',
        help='Full address'
    )
    city = fields.Char(
        string='City/Province',
        index=True,
        help='City or province'
    )
    district = fields.Char(
        string='District',
        help='District or county'
    )
    country_id = fields.Many2one(
        comodel_name='res.country',
        string='Country',
        default=lambda self: self.env.ref('base.vn', raise_if_not_found=False),
        help='Country'
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
        # Try to extract city from name if possible (e.g., "Hanoi - District 1")
        city = name
        if ' - ' in name:
            city = name.split(' - ')[0].strip()

        record = self.create({
            'name': name,
            'code': name,
            'city': city,
            'needs_review': True,
            'created_from_extraction': True
        })
        return record.id, record.display_name
