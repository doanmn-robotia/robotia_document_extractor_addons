# -*- coding: utf-8 -*-

from odoo import models, fields


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
    substance_name = fields.Char(
        string='Substance Name',
        required=True
    )

    # Collection
    collection_quantity_kg = fields.Float(
        string='Collection Quantity (kg)'
    )
    collection_location = fields.Char(
        string='Collection Location'
    )
    storage_location = fields.Char(
        string='Storage Location'
    )

    # Reuse
    reuse_quantity_kg = fields.Float(
        string='Reuse Quantity (kg)'
    )
    reuse_technology = fields.Char(
        string='Reuse Technology/Location'
    )

    # Recycle
    recycle_quantity_kg = fields.Float(
        string='Recycle Quantity (kg)'
    )
    recycle_technology = fields.Char(
        string='Recycle Technology/Facility'
    )
    recycle_usage_location = fields.Char(
        string='Usage Location After Recycling'
    )

    # Disposal
    disposal_quantity_kg = fields.Float(
        string='Disposal Quantity (kg)'
    )
    disposal_technology = fields.Char(
        string='Disposal Technology'
    )
    disposal_facility = fields.Char(
        string='Disposal Facility'
    )
