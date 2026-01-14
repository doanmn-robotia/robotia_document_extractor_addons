# -*- coding: utf-8 -*-

from odoo import models, fields, api
from .document_extraction import auto_detect_title_selection


class CollectionRecycling(models.Model):
    """Table 1.4: Collection, Recycling, Reuse, Disposal

    IMPORTANT: Uses activity_type field to group records.
    One row in PDF may create 4 records (collection, reuse, recycle, disposal)
    """
    _name = 'collection.recycling'
    _description = 'Collection & Recycling'
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
        help='Used to order rows (title rows first in each section)'
    )
    is_title = fields.Boolean(
        string='Is Title Row',
        default=False,
        help='If True, this row is a section title (Collection/Reuse/Recycle/Disposal)'
    )
    activity_type = fields.Selection(
        selection=[
            ('collection', 'Thu gom'),
            ('reuse', 'Tái sử dụng'),
            ('recycle', 'Tái chế'),
            ('disposal', 'Xử lý/Tiêu hủy')
        ],
        string='Activity',
        index=True,
        help='Type of activity: Collection, Reuse, Recycle, or Disposal'
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
    quantity_kg = fields.Float(
        string='Quantity (kg)',
        digits=(16, 4)
    )
    quantity_co2 = fields.Float(
        string='Quantity (ton CO2)',
        digits=(16, 4)
    )
    notes = fields.Text(
        string='Other information'
    )

    @api.depends('substance_id')
    def _compute_substance_name(self):
        for record in self:
            if record.substance_id:
                record.substance_name = record.substance_id.name

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to auto-detect selection for title rows"""
        
        for vals in vals_list:
            # Auto-detect selection for title rows
            if vals.get('is_title'):
                text_value = vals.get('substance_name', '')
                current_value = vals.get('activity_type')
                
                detected_value = auto_detect_title_selection(
                    'collection.recycling',
                    text_value,
                    current_value
                )
                
                if detected_value:
                    vals['activity_type'] = detected_value
        
        return super(CollectionRecycling, self).create(vals_list)

    def write(self, vals):
        """Override write to auto-detect selection for title rows"""
        title_records = self.env['collection.recycling']
        non_title_records = self.env['collection.recycling']
        
        for record in self:
            is_title = vals.get('is_title', record.is_title)
            
            if is_title:
                title_records |= record
            else:
                non_title_records |= record
        
        # Process title records individually
        for record in title_records:
            text_value = vals.get('substance_name', record.substance_name)
            current_value = vals.get('activity_type', record.activity_type)
            
            detected_value = auto_detect_title_selection(
                'collection.recycling',
                text_value,
                current_value
            )
            
            if detected_value:
                # Create copy of vals for this record
                record_vals = vals.copy()
                record_vals['activity_type'] = detected_value
                super(CollectionRecycling, record).write(record_vals)
            else:
                super(CollectionRecycling, record).write(vals)
        
        # Process non-title records in batch
        if non_title_records:
            super(CollectionRecycling, non_title_records).write(vals)
        
        return True
