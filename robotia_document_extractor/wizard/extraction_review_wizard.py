# -*- coding: utf-8 -*-

from odoo import models, fields, api
import json

class ExtractionReviewWizard(models.TransientModel):
    _name = 'extraction.review.wizard'
    _description = 'Extraction Review Wizard'
    _rec_name = 'organization_name'

    # Statistics
    stat_clean = fields.Integer(compute='_compute_validation_stats', string='Clean Fields')
    stat_auto_fixed = fields.Integer(compute='_compute_validation_stats', string='Auto-Fixed')
    stat_needs_review = fields.Integer(compute='_compute_validation_stats', string='Needs Review')

    # Metadata
    document_type = fields.Selection([
        ('01', 'Registration (Form 01)'),
        ('02', 'Report (Form 02)')
    ], string='Document Type', required=True)
    
    year = fields.Integer(string='Year', required=True)
    year_raw = fields.Char(string='Year (RAW)', readonly=True)
    
    # Organization Info
    organization_name = fields.Char(string='Organization Name')
    organization_name_raw = fields.Char(string='Organization Name (RAW)', readonly=True)
    business_license_number = fields.Char(string='Business License Number')
    business_license_number_raw = fields.Char(string='Business License Number (RAW)', readonly=True)
    business_license_date = fields.Date(string='Business License Date')
    business_license_date_raw = fields.Char(string='Business License Date (RAW)', readonly=True)
    business_license_place = fields.Char(string='Business License Place')
    business_license_place_raw = fields.Char(string='Business License Place (RAW)', readonly=True)
    
    legal_representative_name = fields.Char(string='Legal Representative')
    legal_representative_name_raw = fields.Char(string='Legal Representative (RAW)', readonly=True)
    legal_representative_position = fields.Char(string='Position')
    legal_representative_position_raw = fields.Char(string='Position (RAW)', readonly=True)
    
    contact_person_name = fields.Char(string='Contact Person')
    contact_person_name_raw = fields.Char(string='Contact Person (RAW)', readonly=True)
    contact_address = fields.Char(string='Contact Address')
    contact_address_raw = fields.Char(string='Contact Address (RAW)', readonly=True)
    contact_phone = fields.Char(string='Phone')
    contact_phone_raw = fields.Char(string='Phone (RAW)', readonly=True)
    contact_fax = fields.Char(string='Fax')
    contact_fax_raw = fields.Char(string='Fax (RAW)', readonly=True)
    contact_email = fields.Char(string='Email')
    contact_email_raw = fields.Char(string='Email (RAW)', readonly=True)
    
    # PDF Data (for viewer)
    pdf_file = fields.Binary(string='PDF File')
    pdf_filename = fields.Char(string='Filename')
    
    # Review Lines (Form 01)
    substance_usage_ids = fields.One2many('extraction.review.substance.usage', 'wizard_id', string='Substance Usage')
    equipment_product_ids = fields.One2many('extraction.review.equipment.product', 'wizard_id', string='Equipment/Product')
    equipment_ownership_ids = fields.One2many('extraction.review.equipment.ownership', 'wizard_id', string='Equipment Ownership')
    collection_recycling_ids = fields.One2many('extraction.review.collection.recycling', 'wizard_id', string='Collection & Recycling')
    
    # Review Lines (Form 02)
    quota_usage_ids = fields.One2many('extraction.review.quota.usage', 'wizard_id', string='Quota Usage')
    equipment_product_report_ids = fields.One2many('extraction.review.equipment.product.report', 'wizard_id', string='Equipment/Product Report')
    equipment_ownership_report_ids = fields.One2many('extraction.review.equipment.ownership.report', 'wizard_id', string='Equipment Ownership Report')
    collection_recycling_report_ids = fields.One2many('extraction.review.collection.recycling.report', 'wizard_id', string='Collection & Recycling Report')
    
    # JSON Data (for the dual-pane view)
    extracted_data_json = fields.Text(string='Extracted Data (JSON)')

    def action_approve(self):
        """Confirm review and create actual document.extraction record"""
        self.ensure_one()
        
        # 1. Create document.extraction record
        vals = {
            'document_type': self.document_type,
            'year': self.year,
            'organization_name': self.organization_name,
            'business_license_number': self.business_license_number,
            'business_license_date': self.business_license_date,
            'business_license_place': self.business_license_place,
            'legal_representative_name': self.legal_representative_name,
            'legal_representative_position': self.legal_representative_position,
            'contact_person_name': self.contact_person_name,
            'contact_address': self.contact_address,
            'contact_phone': self.contact_phone,
            'contact_fax': self.contact_fax,
            'contact_email': self.contact_email,
            'pdf_file': self.pdf_file,
            'pdf_filename': self.pdf_filename,
            'source': 'from_user_upload',
            'state': 'validated',  # Auto-validate since user reviewed it
        }
        
        doc = self.env['document.extraction'].create(vals)
        
        # 2. Create related lines based on document type
        if self.document_type == '01':
            # Table 1.1: Substance Usage
            for line in self.substance_usage_ids:
                self.env['substance.usage'].create({
                    'document_id': doc.id,
                    'sequence': line.sequence,
                    'is_title': line.is_title,
                    'usage_type': line.usage_type,
                    'substance_id': line.substance_id.id if line.substance_id else False,
                    'substance_name': line.substance_name,
                    'year_1_quantity_kg': line.year_1_quantity_kg,
                    'year_1_quantity_co2': line.year_1_quantity_co2,
                    'year_2_quantity_kg': line.year_2_quantity_kg,
                    'year_2_quantity_co2': line.year_2_quantity_co2,
                    'year_3_quantity_kg': line.year_3_quantity_kg,
                    'year_3_quantity_co2': line.year_3_quantity_co2,
                    'avg_quantity_kg': line.avg_quantity_kg,
                    'avg_quantity_co2': line.avg_quantity_co2,
                })
            
            # Table 1.2: Equipment/Product
            for line in self.equipment_product_ids:
                self.env['equipment.product'].create({
                    'document_id': doc.id,
                    'sequence': line.sequence,
                    'is_title': line.is_title,
                    'equipment_type_id': line.equipment_type_id.id if line.equipment_type_id else False,
                    'product_type': line.product_type,
                    'hs_code_id': line.hs_code_id.id if line.hs_code_id else False,
                    'hs_code': line.hs_code,
                    'capacity': line.capacity,
                    'cooling_capacity': line.cooling_capacity,
                    'power_capacity': line.power_capacity,
                    'quantity': line.quantity,
                    'substance_id': line.substance_id.id if line.substance_id else False,
                    'substance_name': line.substance_name,
                    'substance_quantity_per_unit': line.substance_quantity_per_unit,
                    'notes': line.notes,
                })
            
            # Table 1.3: Equipment Ownership
            for line in self.equipment_ownership_ids:
                self.env['equipment.ownership'].create({
                    'document_id': doc.id,
                    'sequence': line.sequence,
                    'is_title': line.is_title,
                    'equipment_type_id': line.equipment_type_id.id if line.equipment_type_id else False,
                    'equipment_type': line.product_type,  # Map product_type to equipment_type
                    'start_year': 0,  # Not in review model, set default
                    'capacity': line.capacity,
                    'cooling_capacity': line.cooling_capacity,
                    'power_capacity': line.power_capacity,
                    'equipment_quantity': line.quantity,  # Map quantity to equipment_quantity
                    'substance_id': line.substance_id.id if line.substance_id else False,
                    'substance_name': line.substance_name,
                    'refill_frequency': 0,  # Not in review model, set default
                    'substance_quantity_per_refill': line.substance_quantity_per_unit,  # Map field name
                })
            
            # Table 1.4: Collection & Recycling
            for line in self.collection_recycling_ids:
                self.env['collection.recycling'].create({
                    'document_id': doc.id,
                    'sequence': line.sequence,
                    'activity_type': line.activity_type,
                    'substance_id': line.substance_id.id if line.substance_id else False,
                    'substance_name': line.substance_name,
                    'quantity_kg': line.quantity_kg,
                    # Note: collection.recycling model doesn't have facility/technology fields
                    # These are only in collection.recycling.report (Form 02)
                })
            
        elif self.document_type == '02':
            # Table 2.1: Quota Usage
            for line in self.quota_usage_ids:
                self.env['quota.usage'].create({
                    'document_id': doc.id,
                    'sequence': line.sequence,
                    'is_title': line.is_title,
                    'usage_type': line.usage_type,
                    'substance_id': line.substance_id.id if line.substance_id else False,
                    'substance_name': line.substance_name,
                    'hs_code_id': line.hs_code_id.id if line.hs_code_id else False,
                    'hs_code': line.hs_code,
                    'allocated_quota_kg': line.allocated_quota_kg,
                    'allocated_quota_co2': line.allocated_quota_co2,
                    'adjusted_quota_kg': line.adjusted_quota_kg,
                    'adjusted_quota_co2': line.adjusted_quota_co2,
                    'total_quota_kg': line.total_quota_kg,
                    'total_quota_co2': line.total_quota_co2,
                    'average_price': line.average_price,
                    'country_text': line.country_text,
                    'customs_declaration_number': line.customs_declaration_number,
                    'next_year_quota_kg': line.next_year_quota_kg,
                    'next_year_quota_co2': line.next_year_quota_co2,
                })
            
            # Table 2.2: Equipment/Product Report
            for line in self.equipment_product_report_ids:
                self.env['equipment.product.report'].create({
                    'document_id': doc.id,
                    'sequence': line.sequence,
                    'is_title': line.is_title,
                    'production_type': line.production_type,
                    'equipment_type_id': line.equipment_type_id.id if line.equipment_type_id else False,
                    'product_type': line.product_type,
                    'hs_code_id': line.hs_code_id.id if line.hs_code_id else False,
                    'hs_code': line.hs_code,
                    'capacity': line.capacity,
                    'cooling_capacity': line.cooling_capacity,
                    'power_capacity': line.power_capacity,
                    'quantity': line.quantity,
                    'substance_id': line.substance_id.id if line.substance_id else False,
                    'substance_name': line.substance_name,
                    'substance_quantity_per_unit': line.substance_quantity_per_unit,
                    'notes': line.notes,
                })
            
            # Table 2.3: Equipment Ownership Report
            for line in self.equipment_ownership_report_ids:
                self.env['equipment.ownership.report'].create({
                    'document_id': doc.id,
                    'sequence': line.sequence,
                    'is_title': line.is_title,
                    'ownership_type': line.ownership_type,
                    'equipment_type_id': line.equipment_type_id.id if line.equipment_type_id else False,
                    'equipment_type': line.equipment_type,
                    'equipment_quantity': line.equipment_quantity,
                    'substance_id': line.substance_id.id if line.substance_id else False,
                    'substance_name': line.substance_name,
                    'capacity': line.capacity,
                    'cooling_capacity': line.cooling_capacity,
                    'power_capacity': line.power_capacity,
                    'start_year': line.start_year,
                    'refill_frequency': line.refill_frequency,
                    'substance_quantity_per_refill': line.substance_quantity_per_refill,
                    'notes': line.notes,
                })
            
            # Table 2.4: Collection & Recycling Report
            for line in self.collection_recycling_report_ids:
                self.env['collection.recycling.report'].create({
                    'document_id': doc.id,
                    'substance_id': line.substance_id.id if line.substance_id else False,
                    'substance_name': line.substance_name,
                    'collection_quantity_kg': line.collection_quantity_kg,
                    'collection_location': line.collection_location,
                    'storage_location': line.storage_location,
                    'reuse_quantity_kg': line.reuse_quantity_kg,
                    'reuse_technology': line.reuse_technology,
                    'recycle_quantity_kg': line.recycle_quantity_kg,
                    'recycle_technology': line.recycle_technology,
                    'recycle_usage_location': line.recycle_usage_location,
                    'disposal_quantity_kg': line.disposal_quantity_kg,
                    'disposal_technology': line.disposal_technology,
                    'disposal_facility': line.disposal_facility,
                })


        return {
            'type': 'ir.actions.act_window',
            'res_model': 'document.extraction',
            'res_id': doc.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.depends('organization_name', 'business_license_number', 'substance_usage_ids', 'quota_usage_ids')
    def _compute_validation_stats(self):
        for wizard in self:
            clean = 0
            needs_review = 0
            auto_fixed = 0
            
            # Check metadata fields
            metadata_fields = [
                'organization_name', 'business_license_number', 'business_license_date',
                'business_license_place', 'legal_representative_name', 'legal_representative_position',
                'contact_person_name', 'contact_address', 'contact_phone', 'contact_fax', 'contact_email'
            ]
            
            for field in metadata_fields:
                if wizard[field]:
                    clean += 1
                else:
                    needs_review += 1
            
            # Check lines (Form 01)
            for line in wizard.substance_usage_ids:
                if line.substance_name:
                    clean += 1
                else:
                    needs_review += 1
            
            for line in wizard.equipment_product_ids:
                if line.product_type:
                    clean += 1
                else:
                    needs_review += 1
                    
            for line in wizard.equipment_ownership_ids:
                if line.product_type:
                    clean += 1
                else:
                    needs_review += 1
                    
            for line in wizard.collection_recycling_ids:
                if line.substance_name:
                    clean += 1
                else:
                    needs_review += 1

            # Check lines (Form 02)
            for line in wizard.quota_usage_ids:
                if line.substance_name:
                    clean += 1
                else:
                    needs_review += 1
            
            for line in wizard.equipment_product_report_ids:
                if line.product_type:
                    clean += 1
                else:
                    needs_review += 1
            
            for line in wizard.equipment_ownership_report_ids:
                if line.equipment_type:
                    clean += 1
                else:
                    needs_review += 1
            
            for line in wizard.collection_recycling_report_ids:
                if line.substance_name:
                    clean += 1
                else:
                    needs_review += 1
            
            wizard.stat_clean = clean
            wizard.stat_needs_review = needs_review
            wizard.stat_auto_fixed = auto_fixed
