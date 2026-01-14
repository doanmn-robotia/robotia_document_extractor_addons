# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class SubstanceUsage(models.Model):
    """Table 1.1: Substance Usage (Production, Import, Export)"""
    _name = 'substance.usage'
    _description = 'Substance Usage'
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
        help='If True, this row is a section title (Production/Import/Export)'
    )
    usage_type = fields.Selection(
        selection=[
            ('production', 'Sản xuất'),
            ('import', 'Nhập khẩu'),
            ('export', 'Xuất khẩu')
        ],
        string='Activity',
        default="import",
        index=True
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
        index=True,  # Add index for frequent filtering/searching
        help='Substance name (auto-filled from substance_id or manually entered)'
    )
    notes = fields.Text(
        string='Other information'
    )

    # Year 1
    year_1_quantity_kg = fields.Float(
        string='Year 1 Quantity (kg)',
        aggregator=False,
        digits=(16, 4)
    )
    year_1_quantity_co2 = fields.Float(
        string='Year 1 Quantity (ton CO2)',
        aggregator=False,
        digits=(16, 4)
    )

    # Year 2
    year_2_quantity_kg = fields.Float(
        string='Year 2 Quantity (kg)',
        aggregator=False,
        digits=(16, 4)
    )
    year_2_quantity_co2 = fields.Float(
        string='Year 2 Quantity (ton CO2)',
        aggregator=False,
        digits=(16, 4)
    )

    # Year 3
    year_3_quantity_kg = fields.Float(
        string='Year 3 Quantity (kg)',
        aggregator=False,
        digits=(16, 4)
    )
    year_3_quantity_co2 = fields.Float(
        string='Year 3 Quantity (ton CO2)',
        aggregator=False,
        digits=(16, 4)
    )

    # Average
    avg_quantity_kg = fields.Float(
        string='Average Quantity (kg)',
        aggregator=False,
        digits=(16, 4)
    )
    avg_quantity_co2 = fields.Float(
        string='Average Quantity (ton CO2)',
        digits=(16, 4)
    )

    # SQL Constraints for data validation
    _sql_constraints = [
        ('year_1_quantity_kg_positive',
         'CHECK(year_1_quantity_kg IS NULL OR year_1_quantity_kg >= 0)',
         'Year 1 quantity (kg) must be positive or null'),
        ('year_2_quantity_kg_positive',
         'CHECK(year_2_quantity_kg IS NULL OR year_2_quantity_kg >= 0)',
         'Year 2 quantity (kg) must be positive or null'),
        ('year_3_quantity_kg_positive',
         'CHECK(year_3_quantity_kg IS NULL OR year_3_quantity_kg >= 0)',
         'Year 3 quantity (kg) must be positive or null'),
        ('avg_quantity_kg_positive',
         'CHECK(avg_quantity_kg IS NULL OR avg_quantity_kg >= 0)',
         'Average quantity (kg) must be positive or null'),
        ('year_1_quantity_co2_positive',
         'CHECK(year_1_quantity_co2 IS NULL OR year_1_quantity_co2 >= 0)',
         'Year 1 quantity (CO2) must be positive or null'),
        ('year_2_quantity_co2_positive',
         'CHECK(year_2_quantity_co2 IS NULL OR year_2_quantity_co2 >= 0)',
         'Year 2 quantity (CO2) must be positive or null'),
        ('year_3_quantity_co2_positive',
         'CHECK(year_3_quantity_co2 IS NULL OR year_3_quantity_co2 >= 0)',
         'Year 3 quantity (CO2) must be positive or null'),
        ('avg_quantity_co2_positive',
         'CHECK(avg_quantity_co2 IS NULL OR avg_quantity_co2 >= 0)',
         'Average quantity (CO2) must be positive or null'),
    ]

    @api.depends('substance_id')
    def _compute_substance_name(self):
        """Auto-fill substance_name from substance_id"""
        for record in self:
            if record.substance_id:
                record.substance_name = record.substance_id.name

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to auto-detect selection for title rows"""
        from .document_extraction import auto_detect_title_selection
        
        for vals in vals_list:
            # Auto-detect selection for title rows
            if vals.get('is_title'):
                text_value = vals.get('substance_name', '')
                current_value = vals.get('usage_type')
                
                detected_value = auto_detect_title_selection(
                    'substance.usage',
                    text_value,
                    current_value
                )
                
                if detected_value:
                    vals['usage_type'] = detected_value
        
        return super(SubstanceUsage, self).create(vals_list)

    def write(self, vals):
        """Override write to auto-detect selection for title rows"""
        from .document_extraction import auto_detect_title_selection
        
        title_records = self.env['substance.usage']
        non_title_records = self.env['substance.usage']
        
        for record in self:
            is_title = vals.get('is_title', record.is_title)
            
            if is_title:
                title_records |= record
            else:
                non_title_records |= record
        
        # Process title records individually
        for record in title_records:
            text_value = vals.get('substance_name', record.substance_name)
            current_value = vals.get('usage_type', record.usage_type)
            
            detected_value = auto_detect_title_selection(
                'substance.usage',
                text_value,
                current_value
            )
            
            if detected_value:
                # Create copy of vals for this record
                record_vals = vals.copy()
                record_vals['usage_type'] = detected_value
                super(SubstanceUsage, record).write(record_vals)
            else:
                super(SubstanceUsage, record).write(vals)
        
        # Process non-title records in batch
        if non_title_records:
            super(SubstanceUsage, non_title_records).write(vals)
        
        return True
