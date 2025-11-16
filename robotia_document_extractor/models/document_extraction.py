# -*- coding: utf-8 -*-

from odoo import models, fields, api


class DocumentExtraction(models.Model):
    """Main model for document extraction (Form 01 & Form 02)"""
    _name = 'document.extraction'
    _description = 'Document Extraction'
    _order = 'extraction_date desc, id desc'
    _rec_name = 'name'

    # ===== Metadata Fields =====
    name = fields.Char(
        string='Document Name',
        compute='_compute_name',
        store=True,
        index=True
    )
    document_type = fields.Selection(
        selection=[
            ('01', 'Registration (Form 01)'),
            ('02', 'Report (Form 02)')
        ],
        string='Document Type',
        required=True,
        index=True
    )
    pdf_file = fields.Binary(
        string='PDF File',
        attachment=True,
        compute='_compute_pdf_file',
        inverse='_inverse_pdf_file',
        store=False
    )
    pdf_attachment_id = fields.Many2one(
        comodel_name='ir.attachment',
        string='PDF Attachment',
        ondelete='cascade'
    )
    pdf_url = fields.Char(
        string='PDF URL',
        compute='_compute_pdf_url',
        store=False
    )
    pdf_filename = fields.Char(
        string='PDF Filename'
    )
    extraction_date = fields.Datetime(
        string='Extraction Date',
        default=fields.Datetime.now,
        readonly=True
    )
    year = fields.Integer(
        string='Year',
        required=True,
        index=True
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('validated', 'Validated'),
            ('completed', 'Completed')
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True
    )

    # ===== Organization Information (4.1.1 & 4.2.1) =====
    organization_id = fields.Many2one(
        comodel_name='res.partner',
        string='Organization',
        ondelete='restrict',
        index=True,
        domain=[('x_partner_type', '=', 'organization')],
        context={
            'form_view_ref': 'robotia_document_extractor.view_partner_organization_form',
            'tree_view_ref': 'robotia_document_extractor.view_partner_organization_list',
            'search_view_ref': 'robotia_document_extractor.view_partner_organization_search',
            'default_x_partner_type': 'organization',
        }
    )
    organization_name = fields.Char(
        string='Organization Name',
        help='Tên đầy đủ của tổ chức'
    )
    business_license_number = fields.Char(
        string='Business License Number'
    )
    business_license_date = fields.Date(
        string='Business License Date'
    )
    business_license_place = fields.Char(
        string='Business License Place'
    )
    legal_representative_name = fields.Char(
        string='Legal Representative'
    )
    legal_representative_position = fields.Char(
        string='Position'
    )
    contact_person_name = fields.Char(
        string='Contact Person'
    )
    contact_address = fields.Char(
        string='Contact Address'
    )
    contact_phone = fields.Char(
        string='Phone'
    )
    contact_fax = fields.Char(
        string='Fax'
    )
    contact_email = fields.Char(
        string='Email'
    )

    # ===== Activity Fields (4.1.2) =====
    activity_field_ids = fields.Many2many(
        comodel_name='activity.field',
        relation='document_extraction_activity_field_rel',
        column1='document_id',
        column2='activity_field_id',
        string='Activity Fields'
    )

    # ===== Registration Table Selection (Form 01 only) =====
    has_table_1_1 = fields.Boolean(
        string='Has Table 1.1 (Substance Usage)',
        default=False,
        help='Organization registers substance usage (production, import, export)'
    )
    has_table_1_2 = fields.Boolean(
        string='Has Table 1.2 (Equipment/Product)',
        default=False,
        help='Organization registers equipment/product info'
    )
    has_table_1_3 = fields.Boolean(
        string='Has Table 1.3 (Equipment Ownership)',
        default=False,
        help='Organization registers equipment ownership'
    )
    has_table_1_4 = fields.Boolean(
        string='Has Table 1.4 (Collection & Recycling)',
        default=False,
        help='Organization registers collection, recycling, reuse, disposal'
    )

    # ===== Report Table Selection (Form 02 only) =====
    has_table_2_1 = fields.Boolean(
        string='Has Table 2.1 (Quota Usage Report)',
        default=False,
        help='Organization reports quota usage (production, import, export)'
    )
    has_table_2_2 = fields.Boolean(
        string='Has Table 2.2 (Equipment/Product Report)',
        default=False,
        help='Organization reports equipment/product manufacturing or import'
    )
    has_table_2_3 = fields.Boolean(
        string='Has Table 2.3 (Equipment Ownership Report)',
        default=False,
        help='Organization reports owned equipment'
    )
    has_table_2_4 = fields.Boolean(
        string='Has Table 2.4 (Collection & Recycling Report)',
        default=False,
        help='Organization reports collection, recycling, reuse, disposal'
    )

    # ===== Table 1.1: Substance Usage (Production, Import, Export) =====
    substance_usage_ids = fields.One2many(
        comodel_name='substance.usage',
        inverse_name='document_id',
        string='Substance Usage'
    )

    # ===== Table 1.2: Equipment/Product Info =====
    equipment_product_ids = fields.One2many(
        comodel_name='equipment.product',
        inverse_name='document_id',
        string='Equipment/Product'
    )

    # ===== Table 1.3: Equipment Ownership =====
    equipment_ownership_ids = fields.One2many(
        comodel_name='equipment.ownership',
        inverse_name='document_id',
        string='Equipment Ownership'
    )

    # ===== Table 1.4: Collection, Recycling, Reuse, Disposal =====
    collection_recycling_ids = fields.One2many(
        comodel_name='collection.recycling',
        inverse_name='document_id',
        string='Collection & Recycling'
    )

    # ===== Table 2.1: Quota Usage Report (Form 02 only) =====
    quota_usage_ids = fields.One2many(
        comodel_name='quota.usage',
        inverse_name='document_id',
        string='Quota Usage'
    )

    # ===== Table 2.2: Equipment/Product Report (Form 02) =====
    equipment_product_report_ids = fields.One2many(
        comodel_name='equipment.product.report',
        inverse_name='document_id',
        string='Equipment/Product Report'
    )

    # ===== Table 2.3: Equipment Ownership Report (Form 02) =====
    equipment_ownership_report_ids = fields.One2many(
        comodel_name='equipment.ownership.report',
        inverse_name='document_id',
        string='Equipment Ownership Report'
    )

    # ===== Table 2.4: Collection & Recycling Report (Form 02) =====
    collection_recycling_report_ids = fields.One2many(
        comodel_name='collection.recycling.report',
        inverse_name='document_id',
        string='Collection & Recycling Report'
    )

    # ===== Computed Fields =====
    @api.depends('document_type', 'organization_id', 'organization_name', 'year')
    def _compute_name(self):
        for record in self:
            doc_type_label = 'Form 01' if record.document_type == '01' else 'Form 02'
            org_name = record.organization_id.name if record.organization_id else (record.organization_name or 'Unknown')
            year = record.year or 'N/A'
            record.name = f"{doc_type_label} - {org_name} - {year}"

    @api.depends('pdf_attachment_id')
    def _compute_pdf_file(self):
        """Compute pdf_file from attachment"""
        for record in self:
            if record.pdf_attachment_id:
                record.pdf_file = record.pdf_attachment_id.datas
            else:
                record.pdf_file = False

    @api.depends('pdf_attachment_id')
    def _compute_pdf_url(self):
        """Compute PDF URL for iframe viewing"""
        for record in self:
            if record.pdf_attachment_id:
                # Generate URL to view attachment
                base_url = record.env['ir.config_parameter'].sudo().get_param('web.base.url')
                record.pdf_url = f"{base_url}/web/content/{record.pdf_attachment_id.id}?download=false"
            else:
                record.pdf_url = False

    def _inverse_pdf_file(self):
        """Update attachment when pdf_file is set directly"""
        for record in self:
            if record.pdf_file and record.pdf_attachment_id:
                record.pdf_attachment_id.write({
                    'datas': record.pdf_file
                })
            elif record.pdf_file and not record.pdf_attachment_id:
                # Create new attachment if pdf_file is set but no attachment exists
                attachment = self.env['ir.attachment'].create({
                    'name': record.pdf_filename or 'document.pdf',
                    'type': 'binary',
                    'datas': record.pdf_file,
                    'res_model': self._name,
                    'res_id': record.id,
                    'public': True,
                    'mimetype': 'application/pdf',
                })
                record.pdf_attachment_id = attachment.id

    # ===== Onchange Methods =====
    @api.onchange('organization_id')
    def _onchange_organization_id(self):
        """Fill organization info from partner when organization_id changes"""
        if self.organization_id:
            partner = self.organization_id
            self.organization_name = partner.name
            self.business_license_number = partner.business_license_number
            self.business_license_date = partner.business_license_date
            self.business_license_place = partner.business_license_place
            self.legal_representative_name = partner.legal_representative_name
            self.legal_representative_position = partner.legal_representative_position
            self.contact_person_name = partner.contact_person_name
            self.contact_address = partner.street or partner.street2 or ''
            self.contact_phone = partner.phone
            self.contact_fax = partner.fax
            self.contact_email = partner.email

    # ===== Override Create =====
    @api.model_create_multi
    def create(self, vals_list):
        """
        Override create to:
        1. Auto-create organization if not exists
        2. Link PDF attachment to the newly created record

        Logic:
        - If organization_id empty but business_license_number exists:
          - Search partner by business_license_number
          - If found → set organization_id
          - If not found → create new partner → set organization_id
        - If pdf_attachment_id exists, update it with the new res_id
        """
        for vals in vals_list:
            if not vals.get('organization_id') and vals.get('business_license_number'):
                # Search existing partner by business license number
                partner = self.env['res.partner'].search([
                    ('business_license_number', '=', vals.get('business_license_number'))
                ], limit=1)

                if partner:
                    # Partner found → use it
                    vals['organization_id'] = partner.id
                else:
                    # Partner not found → create new
                    partner_vals = {
                        'name': vals.get('organization_name') or 'Unknown Organization',
                        'business_license_number': vals.get('business_license_number'),
                        'business_license_date': vals.get('business_license_date'),
                        'business_license_place': vals.get('business_license_place'),
                        'legal_representative_name': vals.get('legal_representative_name'),
                        'legal_representative_position': vals.get('legal_representative_position'),
                        'contact_person_name': vals.get('contact_person_name'),
                        'street': vals.get('contact_address'),
                        'phone': vals.get('contact_phone'),
                        'fax': vals.get('contact_fax'),
                        'email': vals.get('contact_email'),
                        'is_company': True,
                        'company_type': 'company',
                        'x_partner_type': 'organization'
                    }
                    new_partner = self.env['res.partner'].create(partner_vals)
                    vals['organization_id'] = new_partner.id

        # Create records
        records = super(DocumentExtraction, self).create(vals_list)

        # Link PDF attachments to created records
        for record in records:
            if record.pdf_attachment_id and record.pdf_attachment_id.res_id == 0:
                # Update attachment with actual res_id
                record.pdf_attachment_id.sudo().write({
                    'res_id': record.id,
                    'public': False,  # Make private now that it's linked to a record
                })

        return records

    # ===== Validation Methods =====
    def action_validate(self):
        """Mark document as validated"""
        self.write({'state': 'validated'})

    def action_complete(self):
        """Mark document as completed"""
        self.write({'state': 'completed'})

    def action_draft(self):
        """Reset document to draft"""
        self.write({'state': 'draft'})
