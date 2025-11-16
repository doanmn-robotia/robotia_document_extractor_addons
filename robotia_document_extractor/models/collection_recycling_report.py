# -*- coding: utf-8 -*-

from odoo import models, fields, api


class CollectionRecyclingReport(models.Model):
    """Table 2.4: Collection & Recycling Report (Form 02)

    Complex structure with multiple columns for each activity type
    """
    _name = 'collection.recycling.report'
    _description = 'Collection & Recycling Report'
    _order = 'document_id, substance_name'

    document_id = fields.Many2one(
        comodel_name='document.extraction',
        string='Document',
        required=True,
        ondelete='cascade',
        index=True
    )
    substance_id = fields.Many2one('controlled.substance', string='Controlled Substance', ondelete='restrict', index=True)
    substance_name = fields.Char(string='Substance Name', compute='_compute_substance_name', store=True, readonly=False, required=True)

    # Collection
    collection_quantity_kg = fields.Float(string='Collection Quantity (kg)')
    collection_location_id = fields.Many2one('collection.location', string='Collection Location', ondelete='restrict')
    collection_location = fields.Char(string='Collection Location Text', compute='_compute_collection_location', store=True, readonly=False)
    storage_location_id = fields.Many2one('collection.location', string='Storage Location', ondelete='restrict')
    storage_location = fields.Char(string='Storage Location Text', compute='_compute_storage_location', store=True, readonly=False)

    # Reuse
    reuse_quantity_kg = fields.Float(string='Reuse Quantity (kg)')
    reuse_technology_id = fields.Many2one('recycling.technology', string='Reuse Technology', ondelete='restrict')
    reuse_technology = fields.Char(string='Reuse Technology Text', compute='_compute_reuse_technology', store=True, readonly=False)

    # Recycle
    recycle_quantity_kg = fields.Float(string='Recycle Quantity (kg)')
    recycle_technology_id = fields.Many2one('recycling.technology', string='Recycle Technology', ondelete='restrict')
    recycle_technology = fields.Char(string='Recycle Technology Text', compute='_compute_recycle_technology', store=True, readonly=False)
    recycle_facility_id = fields.Many2one('recycling.facility', string='Recycle Facility', ondelete='restrict')
    recycle_usage_location_id = fields.Many2one('collection.location', string='Usage Location After Recycling', ondelete='restrict')
    recycle_usage_location = fields.Char(string='Usage Location Text', compute='_compute_recycle_location', store=True, readonly=False)

    # Disposal
    disposal_quantity_kg = fields.Float(string='Disposal Quantity (kg)')
    disposal_technology_id = fields.Many2one('recycling.technology', string='Disposal Technology', ondelete='restrict')
    disposal_technology = fields.Char(string='Disposal Technology Text', compute='_compute_disposal_technology', store=True, readonly=False)
    disposal_facility_id = fields.Many2one('recycling.facility', string='Disposal Facility', ondelete='restrict')
    disposal_facility = fields.Char(string='Disposal Facility Text', compute='_compute_disposal_facility', store=True, readonly=False)

    @api.depends('substance_id')
    def _compute_substance_name(self):
        for r in self:
            r.substance_name = r.substance_id.name if r.substance_id else ''

    @api.depends('collection_location_id')
    def _compute_collection_location(self):
        for r in self:
            r.collection_location = r.collection_location_id.name if r.collection_location_id else ''

    @api.depends('storage_location_id')
    def _compute_storage_location(self):
        for r in self:
            r.storage_location = r.storage_location_id.name if r.storage_location_id else ''

    @api.depends('reuse_technology_id')
    def _compute_reuse_technology(self):
        for r in self:
            r.reuse_technology = r.reuse_technology_id.name if r.reuse_technology_id else ''

    @api.depends('recycle_technology_id')
    def _compute_recycle_technology(self):
        for r in self:
            r.recycle_technology = r.recycle_technology_id.name if r.recycle_technology_id else ''

    @api.depends('recycle_usage_location_id')
    def _compute_recycle_location(self):
        for r in self:
            r.recycle_usage_location = r.recycle_usage_location_id.name if r.recycle_usage_location_id else ''

    @api.depends('disposal_technology_id')
    def _compute_disposal_technology(self):
        for r in self:
            r.disposal_technology = r.disposal_technology_id.name if r.disposal_technology_id else ''

    @api.depends('disposal_facility_id')
    def _compute_disposal_facility(self):
        for r in self:
            r.disposal_facility = r.disposal_facility_id.name if r.disposal_facility_id else ''

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Substance
            if not vals.get('substance_id') and vals.get('substance_name'):
                vals['substance_id'] = self._find_or_create('controlled.substance', vals['substance_name']).id
            # Collection locations
            if not vals.get('collection_location_id') and vals.get('collection_location'):
                vals['collection_location_id'] = self._find_or_create('collection.location', vals['collection_location'], {'location_type': 'collection'}).id
            if not vals.get('storage_location_id') and vals.get('storage_location'):
                vals['storage_location_id'] = self._find_or_create('collection.location', vals['storage_location'], {'location_type': 'storage'}).id
            if not vals.get('recycle_usage_location_id') and vals.get('recycle_usage_location'):
                vals['recycle_usage_location_id'] = self._find_or_create('collection.location', vals['recycle_usage_location'], {}).id
            # Technologies
            if not vals.get('reuse_technology_id') and vals.get('reuse_technology'):
                vals['reuse_technology_id'] = self._find_or_create('recycling.technology', vals['reuse_technology'], {'technology_type': 'reuse'}).id
            if not vals.get('recycle_technology_id') and vals.get('recycle_technology'):
                vals['recycle_technology_id'] = self._find_or_create('recycling.technology', vals['recycle_technology'], {'technology_type': 'recycle'}).id
            if not vals.get('disposal_technology_id') and vals.get('disposal_technology'):
                vals['disposal_technology_id'] = self._find_or_create('recycling.technology', vals['disposal_technology'], {'technology_type': 'disposal'}).id
            # Facilities
            if not vals.get('recycle_facility_id') and vals.get('recycle_technology'):  # Use tech name as facility if not specified
                vals['recycle_facility_id'] = self._find_or_create('recycling.facility', vals.get('recycle_technology'), {'facility_type': 'recycling'}).id
            if not vals.get('disposal_facility_id') and vals.get('disposal_facility'):
                vals['disposal_facility_id'] = self._find_or_create('recycling.facility', vals['disposal_facility'], {'facility_type': 'disposal'}).id
        return super(CollectionRecyclingReport, self).create(vals_list)

    def _find_or_create(self, model, text, extra_vals=None):
        text = text.strip()
        rec = self.env[model].search(['|', ('name', '=ilike', text), ('code', '=ilike', text)], limit=1)
        if rec:
            return rec
        create_vals = {'name': text, 'code': text, 'active': True, 'needs_review': True, 'created_from_extraction': True}
        if extra_vals:
            create_vals.update(extra_vals)
        return self.env[model].create(create_vals)
