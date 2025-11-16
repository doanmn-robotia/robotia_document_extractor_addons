# -*- coding: utf-8 -*-

from odoo import models, fields, api


class RecyclingFacility(models.Model):
    """Master data for recycling/disposal facilities"""
    _name = 'recycling.facility'
    _description = 'Recycling/Disposal Facility'
    _rec_name = 'name'
    _order = 'name'

    name = fields.Char(
        string='Facility Name',
        required=True,
        index=True,
        help='Name of recycling/disposal facility'
    )
    code = fields.Char(
        string='Code',
        index=True,
        help='Short code for facility'
    )
    facility_type = fields.Selection(
        selection=[
            ('recycling', 'Recycling'),
            ('disposal', 'Disposal'),
            ('recovery', 'Recovery'),
            ('mixed', 'Mixed Services')
        ],
        string='Facility Type',
        help='Type of services provided'
    )
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Operating Company',
        help='Company operating this facility',
        domain=[('x_partner_type', '=', 'organization')],
        context={
            'form_view_ref': 'robotia_document_extractor.view_partner_organization_form',
            'tree_view_ref': 'robotia_document_extractor.view_partner_organization_list',
            'search_view_ref': 'robotia_document_extractor.view_partner_organization_search',
            'default_x_partner_type': 'organization',
        }
    )
    address = fields.Char(
        string='Address',
        help='Full address of facility'
    )
    city = fields.Char(
        string='City/Province',
        help='City or province where facility is located'
    )
    country_id = fields.Many2one(
        comodel_name='res.country',
        string='Country',
        default=lambda self: self.env.ref('base.vn', raise_if_not_found=False),
        help='Country where facility is located'
    )
    technology_ids = fields.Many2many(
        comodel_name='recycling.technology',
        relation='facility_technology_rel',
        column1='facility_id',
        column2='technology_id',
        string='Available Technologies',
        help='Technologies available at this facility'
    )
    capacity = fields.Float(
        string='Annual Capacity (kg)',
        help='Annual processing capacity in kilograms'
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
