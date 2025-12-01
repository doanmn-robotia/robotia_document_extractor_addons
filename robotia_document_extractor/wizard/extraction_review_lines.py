# -*- coding: utf-8 -*-

from odoo import models, fields, api

class ReviewSubstanceUsage(models.TransientModel):
    _name = 'extraction.review.substance.usage'
    _description = 'Review: Substance Usage'
    _order = 'sequence, id'

    wizard_id = fields.Many2one('extraction.review.wizard', string='Wizard', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    
    # Mirror fields from substance.usage
    is_title = fields.Boolean(default=False)
    usage_type = fields.Selection([
        ('production', 'Production'),
        ('import', 'Import'),
        ('export', 'Export')
    ], string='Usage Type')
    usage_type_raw = fields.Char(string='Usage Type (RAW)', readonly=True)
    
    substance_id = fields.Many2one('controlled.substance', string='Controlled Substance')
    substance_name = fields.Char(string='Substance Name')
    substance_name_raw = fields.Char(string='Substance Name (RAW)', readonly=True)
    
    # Year 1
    year_1_quantity_kg = fields.Float(string='Year 1 (kg)', digits=(16, 4))
    year_1_quantity_kg_raw = fields.Char(string='Year 1 (kg) (RAW)', readonly=True)
    year_1_quantity_co2 = fields.Float(string='Year 1 (ton CO2)', digits=(16, 4))
    
    # Year 2
    year_2_quantity_kg = fields.Float(string='Year 2 (kg)', digits=(16, 4))
    year_2_quantity_co2 = fields.Float(string='Year 2 (ton CO2)', digits=(16, 4))
    
    # Year 3
    year_3_quantity_kg = fields.Float(string='Year 3 (kg)', digits=(16, 4))
    year_3_quantity_co2 = fields.Float(string='Year 3 (ton CO2)', digits=(16, 4))
    
    # Average
    avg_quantity_kg = fields.Float(string='Avg (kg)', digits=(16, 4))
    avg_quantity_co2 = fields.Float(string='Avg (ton CO2)', digits=(16, 4))


class ReviewEquipmentProduct(models.TransientModel):
    _name = 'extraction.review.equipment.product'
    _description = 'Review: Equipment/Product'
    _order = 'sequence, id'

    wizard_id = fields.Many2one('extraction.review.wizard', string='Wizard', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    
    is_title = fields.Boolean(default=False)
    equipment_type_id = fields.Many2one('equipment.type', string='Equipment Type')
    product_type = fields.Char(string='Product/Equipment Type')
    product_type_raw = fields.Char(string='Product/Equipment Type (RAW)', readonly=True)
    
    hs_code_id = fields.Many2one('hs.code', string='HS Code')
    hs_code = fields.Char(string='HS Code Text')
    
    capacity = fields.Char(string='Capacity (Merged)')
    cooling_capacity = fields.Char(string='Cooling Capacity')
    power_capacity = fields.Char(string='Power Capacity')
    
    quantity = fields.Float(string='Quantity', digits=(16, 4))
    quantity_raw = fields.Char(string='Quantity (RAW)', readonly=True)
    
    substance_id = fields.Many2one('controlled.substance', string='Controlled Substance')
    substance_name = fields.Char(string='Substance Name')
    substance_quantity_per_unit = fields.Float(string='Substance Qty/Unit', digits=(16, 4))
    
    notes = fields.Text(string='Notes')


class ReviewEquipmentOwnership(models.TransientModel):
    _name = 'extraction.review.equipment.ownership'
    _description = 'Review: Equipment Ownership'
    _order = 'sequence, id'

    wizard_id = fields.Many2one('extraction.review.wizard', string='Wizard', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    
    is_title = fields.Boolean(default=False)
    equipment_type_id = fields.Many2one('equipment.type', string='Equipment Type')
    product_type = fields.Char(string='Product/Equipment Type')
    product_type_raw = fields.Char(string='Product/Equipment Type (RAW)', readonly=True)
    
    capacity = fields.Char(string='Capacity (Merged)')
    cooling_capacity = fields.Char(string='Cooling Capacity')
    power_capacity = fields.Char(string='Power Capacity')
    
    quantity = fields.Float(string='Quantity', digits=(16, 4))
    quantity_raw = fields.Char(string='Quantity (RAW)', readonly=True)
    
    substance_id = fields.Many2one('controlled.substance', string='Controlled Substance')
    substance_name = fields.Char(string='Substance Name')
    substance_quantity_per_unit = fields.Float(string='Substance Qty/Unit', digits=(16, 4))
    total_substance_quantity = fields.Float(string='Total Substance Qty', digits=(16, 4))
    
    operation_status = fields.Char(string='Operation Status')
    notes = fields.Text(string='Notes')


class ReviewCollectionRecycling(models.TransientModel):
    _name = 'extraction.review.collection.recycling'
    _description = 'Review: Collection & Recycling'
    _order = 'sequence, id'

    wizard_id = fields.Many2one('extraction.review.wizard', string='Wizard', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    
    activity_type = fields.Selection([
        ('collection', 'Collection'),
        ('recycling', 'Recycling'),
        ('reuse', 'Reuse'),
        ('disposal', 'Disposal')
    ], string='Activity Type')
    
    substance_id = fields.Many2one('controlled.substance', string='Controlled Substance')
    substance_name = fields.Char(string='Substance Name')
    substance_name_raw = fields.Char(string='Substance Name (RAW)', readonly=True)
    
    quantity_kg = fields.Float(string='Quantity (kg)', digits=(16, 4))
    quantity_kg_raw = fields.Char(string='Quantity (kg) (RAW)', readonly=True)
    
    facility_id = fields.Many2one('recycling.facility', string='Facility')
    facility_name = fields.Char(string='Facility Name')
    
    technology_id = fields.Many2one('recycling.technology', string='Technology')
    technology_name = fields.Char(string='Technology Name')
    
    notes = fields.Text(string='Notes')


class ReviewQuotaUsage(models.TransientModel):
    _name = 'extraction.review.quota.usage'
    _description = 'Review: Quota Usage'
    _order = 'sequence, id'

    wizard_id = fields.Many2one('extraction.review.wizard', string='Wizard', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    
    is_title = fields.Boolean(default=False)
    usage_type = fields.Selection([
        ('production', 'Production'),
        ('import', 'Import'),
        ('export', 'Export')
    ], string='Usage Type')
    usage_type_raw = fields.Char(string='Usage Type (RAW)', readonly=True)
    
    substance_id = fields.Many2one('controlled.substance', string='Controlled Substance')
    substance_name = fields.Char(string='Substance Name')
    substance_name_raw = fields.Char(string='Substance Name (RAW)', readonly=True)
    
    hs_code_id = fields.Many2one('hs.code', string='HS Code')
    hs_code = fields.Char(string='HS Code Text')
    hs_code_raw = fields.Char(string='HS Code (RAW)', readonly=True)
    
    allocated_quota_kg = fields.Float(string='Allocated (kg)', digits=(16, 4))
    allocated_quota_kg_raw = fields.Char(string='Allocated (kg) (RAW)', readonly=True)
    allocated_quota_co2 = fields.Float(string='Allocated (ton CO2)', digits=(16, 4))
    allocated_quota_co2_raw = fields.Char(string='Allocated (ton CO2) (RAW)', readonly=True)
    
    adjusted_quota_kg = fields.Float(string='Adjusted (kg)', digits=(16, 4))
    adjusted_quota_kg_raw = fields.Char(string='Adjusted (kg) (RAW)', readonly=True)
    adjusted_quota_co2 = fields.Float(string='Adjusted (ton CO2)', digits=(16, 4))
    adjusted_quota_co2_raw = fields.Char(string='Adjusted (ton CO2) (RAW)', readonly=True)
    
    total_quota_kg = fields.Float(string='Total (kg)', digits=(16, 4))
    total_quota_kg_raw = fields.Char(string='Total (kg) (RAW)', readonly=True)
    total_quota_co2 = fields.Float(string='Total (ton CO2)', digits=(16, 4))
    
    average_price = fields.Float(string='Avg Price', digits=(16, 4))
    country_text = fields.Char(string='Country')
    customs_declaration_number = fields.Char(string='Customs Decl. No.')
    
    next_year_quota_kg = fields.Float(string='Next Year (kg)', digits=(16, 4))
    next_year_quota_co2 = fields.Float(string='Next Year (ton CO2)', digits=(16, 4))


# Form 02 Report Tables

class ReviewEquipmentProductReport(models.TransientModel):
    """Table 2.2: Equipment/Product Report (Form 02)"""
    _name = 'extraction.review.equipment.product.report'
    _description = 'Review: Equipment/Product Report'
    _order = 'sequence, id'

    wizard_id = fields.Many2one('extraction.review.wizard', string='Wizard', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    
    is_title = fields.Boolean(default=False)
    production_type = fields.Selection([
        ('production', 'Production'),
        ('import', 'Import')
    ], string='Production Type')
    
    equipment_type_id = fields.Many2one('equipment.type', string='Equipment Type')
    product_type = fields.Char(string='Product/Equipment Type')
    product_type_raw = fields.Char(string='Product/Equipment Type (RAW)', readonly=True)
    
    hs_code_id = fields.Many2one('hs.code', string='HS Code')
    hs_code = fields.Char(string='HS Code Text')
    
    capacity = fields.Char(string='Capacity (Merged)')
    cooling_capacity = fields.Char(string='Cooling Capacity')
    power_capacity = fields.Char(string='Power Capacity')
    
    quantity = fields.Float(string='Quantity', digits=(16, 4))
    quantity_raw = fields.Char(string='Quantity (RAW)', readonly=True)
    
    substance_id = fields.Many2one('controlled.substance', string='Controlled Substance')
    substance_name = fields.Char(string='Substance Name')
    substance_quantity_per_unit = fields.Float(string='Substance Qty/Unit', digits=(16, 4))
    
    notes = fields.Text(string='Notes')


class ReviewEquipmentOwnershipReport(models.TransientModel):
    """Table 2.3: Equipment Ownership Report (Form 02)"""
    _name = 'extraction.review.equipment.ownership.report'
    _description = 'Review: Equipment Ownership Report'
    _order = 'sequence, id'

    wizard_id = fields.Many2one('extraction.review.wizard', string='Wizard', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    
    is_title = fields.Boolean(default=False)
    ownership_type = fields.Selection([
        ('air_conditioner', 'Air Conditioner'),
        ('refrigeration', 'Refrigeration')
    ], string='Ownership Type')
    
    equipment_type_id = fields.Many2one('equipment.type', string='Equipment Type')
    equipment_type = fields.Char(string='Equipment Type Text')
    equipment_type_raw = fields.Char(string='Equipment Type (RAW)', readonly=True)
    
    equipment_quantity = fields.Integer(string='Quantity')
    equipment_quantity_raw = fields.Char(string='Quantity (RAW)', readonly=True)
    
    substance_id = fields.Many2one('controlled.substance', string='Controlled Substance')
    substance_name = fields.Char(string='Substance Name')
    
    capacity = fields.Char(string='Capacity (Merged)')
    cooling_capacity = fields.Char(string='Cooling Capacity')
    power_capacity = fields.Char(string='Power Capacity')
    
    start_year = fields.Integer(string='Year Started')
    refill_frequency = fields.Float(string='Refill Frequency', digits=(16, 4))
    substance_quantity_per_refill = fields.Float(string='Substance Qty/Refill', digits=(16, 4))
    
    notes = fields.Text(string='Notes')


class ReviewCollectionRecyclingReport(models.TransientModel):
    """Table 2.4: Collection & Recycling Report (Form 02)"""
    _name = 'extraction.review.collection.recycling.report'
    _description = 'Review: Collection & Recycling Report'
    _order = 'substance_name'

    wizard_id = fields.Many2one('extraction.review.wizard', string='Wizard', required=True, ondelete='cascade')
    
    substance_id = fields.Many2one('controlled.substance', string='Controlled Substance')
    substance_name = fields.Char(string='Substance Name')
    substance_name_raw = fields.Char(string='Substance Name (RAW)', readonly=True)
    
    # Collection
    collection_quantity_kg = fields.Float(string='Collection Qty (kg)', digits=(16, 4))
    collection_quantity_kg_raw = fields.Char(string='Collection Qty (kg) (RAW)', readonly=True)
    collection_location = fields.Char(string='Collection Location')
    storage_location = fields.Char(string='Storage Location')
    
    # Reuse
    reuse_quantity_kg = fields.Float(string='Reuse Qty (kg)', digits=(16, 4))
    reuse_technology = fields.Char(string='Reuse Technology')
    
    # Recycle
    recycle_quantity_kg = fields.Float(string='Recycle Qty (kg)', digits=(16, 4))
    recycle_technology = fields.Char(string='Recycle Technology')
    recycle_usage_location = fields.Char(string='Usage Location After Recycling')
    
    # Disposal
    disposal_quantity_kg = fields.Float(string='Disposal Qty (kg)', digits=(16, 4))
    disposal_technology = fields.Char(string='Disposal Technology')
    disposal_facility = fields.Char(string='Disposal Facility')

