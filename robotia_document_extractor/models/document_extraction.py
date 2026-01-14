# -*- coding: utf-8 -*-

import json
import base64
import logging

from odoo import models, fields, api
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


# ===== Title Selection Auto-Detection Configuration =====
# Keyword mappings for auto-detecting selection values from title text
TITLE_KEYWORD_CONFIG = {
    'substance.usage': {
        'field_name': 'substance_usage_ids',  # For cron job
        'text_field': 'substance_name',
        'selection_field': 'usage_type',
        'templates': {
            # Exact template texts from view XML (case-insensitive match)
            'production': 'Sản xuất chất được kiểm soát',
            'import': 'Nhập khẩu chất được kiểm soát',
            'export': 'Xuất khẩu chất được kiểm soát'
        },
        'mappings': {
            'production': ['sản xuất', 'production', 'produce', 'manufacturing', 'san xuat', 'sx'],
            'import': ['nhập khẩu', 'import', 'nhap khau', 'nk', 'importing'],
            'export': ['xuất khẩu', 'export', 'xuat khau', 'xk', 'exporting']
        },
        'default': 'import'
    },
    'equipment.product': {
        'field_name': 'equipment_product_ids',
        'text_field': 'product_type',
        'selection_field': 'production_type',
        'templates': {
            'production': 'Sản xuất thiết bị, sản phẩm có chứa hoặc sản xuất từ chất được kiểm soát',
            'import': 'Nhập khẩu thiết bị, sản phẩm có chứa hoặc sản xuất từ chất được kiểm soát'
        },
        'mappings': {
            'production': ['sản xuất thiết bị', 'sản xuất sản phẩm', 'production equipment',
                          'san xuat thiet bi', 'sx thiết bị', 'manufacturing'],
            'import': ['nhập khẩu thiết bị', 'nhập khẩu sản phẩm', 'import equipment',
                      'nhap khau thiet bi', 'nk thiết bị']
        },
        'default': 'production'
    },
    'equipment.ownership': {
        'field_name': 'equipment_ownership_ids',
        'text_field': 'equipment_type',
        'selection_field': 'ownership_type',
        'templates': {
            'air_conditioner': 'Máy điều hòa không khí có năng suất lạnh danh định lớn hơn 26,5 kW (90.000 BTU/h) và có tổng năng suất lạnh danh định của các thiết bị lớn hơn 586 kW (2.000.000 BTU/h)',
            'refrigeration': 'Thiết bị lạnh công nghiệp có công suất điện lớn hơn 40 kW'
        },
        'mappings': {
            'air_conditioner': ['máy điều hòa', 'điều hòa không khí', 'air conditioner',
                               'dieu hoa', '26,5 kw', '90.000 btu', '90000 btu', 'conditioning'],
            'refrigeration': ['thiết bị lạnh', 'lạnh công nghiệp', 'industrial cooling',
                             'refrigeration', 'thiet bi lanh', '40 kw', 'công suất điện']
        },
        'default': 'air_conditioner'
    },
    'collection.recycling': {
        'field_name': 'collection_recycling_ids',
        'text_field': 'substance_name',
        'selection_field': 'activity_type',
        'templates': {
            'collection': 'Thu gom chất được kiểm soát',
            'reuse': 'Tái sử dụng chất được kiểm soát sau thu gom',
            'recycle': 'Tái chế chất sau thu gom',
            'disposal': 'Xử lý chất được kiểm soát'
        },
        'mappings': {
            'collection': ['thu gom', 'collection', 'collect', 'thu hồi', 'thu gôm', 'collecting'],
            'reuse': ['tái sử dụng', 'reuse', 'tai su dung', 'tái dùng', 'reusing'],
            'recycle': ['tái chế', 'recycle', 'tai che', 'recycling', 'chế tạo lại'],
            'disposal': ['xử lý', 'tiêu hủy', 'disposal', 'xu ly', 'tieu huy',
                        'destroy', 'destruction', 'hủy', 'tiêu huỷ']
        },
        'default': 'collection'
    },
    'quota.usage': {
        'field_name': 'quota_usage_ids',
        'text_field': 'substance_name',
        'selection_field': 'usage_type',
        'templates': {
            'production': 'Sản xuất chất được kiểm soát',
            'import': 'Nhập khẩu chất được kiểm soát',
            'export': 'Xuất khẩu chất được kiểm soát'
        },
        'mappings': {
            'production': ['sản xuất', 'production', 'produce', 'manufacturing', 'san xuat', 'sx'],
            'import': ['nhập khẩu', 'import', 'nhap khau', 'nk', 'importing'],
            'export': ['xuất khẩu', 'export', 'xuat khau', 'xk', 'exporting']
        },
        'default': 'import'
    },
    'equipment.product.report': {
        'field_name': 'equipment_product_report_ids',
        'text_field': 'product_type',
        'selection_field': 'production_type',
        'templates': {
            'production': 'Sản xuất thiết bị, sản phẩm có chứa hoặc sản xuất từ chất được kiểm soát',
            'import': 'Nhập khẩu thiết bị, sản phẩm có chứa hoặc sản xuất từ chất được kiểm soát'
        },
        'mappings': {
            'production': ['sản xuất thiết bị', 'sản xuất sản phẩm', 'production equipment',
                          'san xuat thiet bi', 'sx thiết bị', 'manufacturing'],
            'import': ['nhập khẩu thiết bị', 'nhập khẩu sản phẩm', 'import equipment',
                      'nhap khau thiet bi', 'nk thiết bị']
        },
        'default': 'import'
    },
    'equipment.ownership.report': {
        'field_name': 'equipment_ownership_report_ids',
        'text_field': 'equipment_type',
        'selection_field': 'ownership_type',
        'templates': {
            'air_conditioner': 'Máy điều hòa không khí có năng suất lạnh danh định lớn hơn 26,5 kW (90.000 BTU/h) và có tổng năng suất lạnh danh định của các thiết bị lớn hơn 586 kW (2.000.000 BTU/h)',
            'refrigeration': 'Thiết bị lạnh công nghiệp có công suất điện lớn hơn 40 kW'
        },
        'mappings': {
            'air_conditioner': ['máy điều hòa', 'điều hòa không khí', 'air conditioner',
                               'dieu hoa', '26,5 kw', '90.000 btu', '90000 btu', 'conditioning'],
            'refrigeration': ['thiết bị lạnh', 'lạnh công nghiệp', 'industrial cooling',
                             'refrigeration', 'thiet bi lanh', '40 kw', 'công suất điện']
        },
        'default': 'air_conditioner'
    }
}


def match_title_selection(text, templates, mappings, default_value, use_default=True):
    """
    Module-level helper: Match text against templates and keyword mappings

    Matching Strategy (in priority order):
    1. Exact match with template texts (100% confidence) - case-insensitive
    2. Fuzzy match first 4 words against keywords (90-99% confidence)
    3. Fuzzy match full text against keywords (70-89% confidence)
    4. Default value (0% confidence) - only if use_default=True

    Args:
        text: Text to match (e.g., "Nhập khẩu thiết bị, sản phẩm có chứa hoặc sản xuất từ chất được kiểm soát")
        templates: Dict of {selection_value: template_text} from view XML
        mappings: Dict of {selection_value: [keywords]}
        default_value: Default selection value if no match found
        use_default: If False, return None instead of default when no match (default: True)

    Returns:
        tuple: (matched_value, confidence_score, match_type)
            - matched_value: The matched selection value, default, or None
            - confidence_score: 0-100 confidence percentage
            - match_type: 'template' | 'fuzzy_prefix' | 'fuzzy_full' | 'default' | 'no_match'
    """
    try:
        from rapidfuzz import fuzz
        from unidecode import unidecode
    except ImportError:
        _logger.warning("Missing dependencies: rapidfuzz or unidecode. Cannot auto-detect title selections.")
        return (default_value if use_default else None, 0, 'default' if use_default else 'no_match')

    if not text or not isinstance(text, str):
        return (default_value if use_default else None, 0, 'default' if use_default else 'no_match')

    # Normalize text for matching
    normalized_text = unidecode(text.lower().strip())

    # Strategy 1: Check exact match with template texts (100% confidence)
    if templates:
        for selection_value, template_text in templates.items():
            normalized_template = unidecode(template_text.lower().strip())
            if normalized_text == normalized_template:
                return (selection_value, 100, 'template')

    # Extract first 4 words for prefix matching
    words = normalized_text.split()
    first_4_words = ' '.join(words[:4]) if len(words) >= 4 else normalized_text

    best_match = None
    best_score = 0
    best_type = 'default'

    # Strategy 2: Fuzzy match first 4 words (prioritize beginning of text)
    for selection_value, keywords in mappings.items():
        for keyword in keywords:
            normalized_keyword = unidecode(keyword.lower().strip())

            # Try matching first 4 words
            score_prefix = fuzz.partial_ratio(first_4_words, normalized_keyword)

            if score_prefix > best_score:
                best_score = score_prefix
                best_match = selection_value
                best_type = 'fuzzy_prefix'

    # If prefix match is good enough (>= 80), return it
    if best_score >= 80 and best_match:
        return (best_match, best_score, best_type)

    # Strategy 3: Fuzzy match full text (fallback)
    for selection_value, keywords in mappings.items():
        for keyword in keywords:
            normalized_keyword = unidecode(keyword.lower().strip())

            # Full text fuzzy matching
            score_full = fuzz.partial_ratio(normalized_text, normalized_keyword)

            if score_full > best_score:
                best_score = score_full
                best_match = selection_value
                best_type = 'fuzzy_full'

    # Apply confidence threshold (70%)
    if best_score >= 70 and best_match:
        return (best_match, best_score, best_type)

    # Fallback to default or None
    if use_default:
        return (default_value, 0, 'default')
    else:
        return (None, 0, 'no_match')


def auto_detect_title_selection(model_name, text_value, current_value=None, use_default=True):
    """
    Auto-detect selection field value for title rows based on text content

    Logic:
    1. If match found (template/fuzzy >= 70%):
       - Always use matched value (override existing)
    2. If no match and use_default=True:
       - Use default value from config
    3. If no match and use_default=False:
       - Return current_value (keep existing or leave empty)

    Args:
        model_name: Model name (e.g., 'substance.usage')
        text_value: Text to match against (e.g., "Nhập khẩu thiết bị, sản phẩm có chứa hoặc sản xuất từ chất được kiểm soát")
        current_value: Current selection value (if any)
        use_default: If True, use default when no match; if False, return None/current_value (default: True)

    Returns:
        str: Selection value to use (matched, default, existing, or None)
    """
    if model_name not in TITLE_KEYWORD_CONFIG:
        return current_value

    config = TITLE_KEYWORD_CONFIG[model_name]
    matched_value, confidence, match_type = match_title_selection(
        text_value,
        config.get('templates', {}),  # Templates from view XML
        config['mappings'],
        config['default'],
        use_default  # Pass through use_default parameter
    )

    # Priority: Match result > Current value > Default (if enabled)
    if match_type in ['template', 'fuzzy_prefix', 'fuzzy_full']:
        # Found a good match
        return matched_value
    elif match_type == 'default':
        # No match, but default is enabled
        return matched_value  # This is the default value
    else:
        # No match and use_default=False
        return current_value  # Keep existing value or None


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

    # OCR Raw Data
    raw_ocr_data = fields.Text(
        string='Raw OCR Data',
        related="extraction_log_id.ocr_response_json",
        help='Structured OCR data with bounding boxes (JSON format). '
             'Contains text regions with coordinates for PDF highlighting.'
    )
    
    # AI Validation Result
    validation_result = fields.Text(
        string='AI Validation Result',
        related="extraction_log_id.validation_result_json",
        help='AI validation report comparing OCR output with PDF source (JSON format). '
             'Contains accuracy metrics, error list, and correction suggestions.'
    )
    
    extraction_date = fields.Datetime(
        string='Extraction Date',
        default=fields.Datetime.now,
        readonly=True
    )
    year = fields.Integer(
        string='Year',
        index=True,
        aggregator=False
    )
    year_1 = fields.Integer(
        string='Year 1 (Past Year)',
        help='Actual year represented by year_1 column (e.g., 2023)',
        aggregator=False
    )
    year_2 = fields.Integer(
        string='Year 2 (Current Year)',
        help='Actual year represented by year_2 column (e.g., 2024)',
        aggregator=False
    )
    year_3 = fields.Integer(
        string='Year 3 (Next Year)',
        help='Actual year represented by year_3 column (e.g., 2025)',
        aggregator=False
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
        tracking=True,
        index=True  # Performance: frequently filtered in dashboards
    )
    needs_review = fields.Boolean(
        string='Needs Manual Review',
        default=False,
        help='Flag this record if extraction has issues and needs human review',
        tracking=True
    )
    review_notes = fields.Text(
        string='Review Notes',
        help='Notes about extraction issues that need manual review'
    )
    extraction_log_id = fields.Many2one(
        'google.drive.extraction.log',
        string='Extraction Log',
        ondelete='set null',
        copy=False,
        index=True,
        help='Link to extraction log record (for both manual and automated extractions)'
    )

    extraction_log_json = fields.Text(related="extraction_log_id.ai_response_json")

    source = fields.Selection(
        selection=[
            ('from_user_upload', 'User Upload'),
            ('from_external_source', 'External Source (Google Drive)')
        ],
        string='Source',
        default='from_user_upload',
        required=True,
        index=True,
        help='Source of the document: manually uploaded by user or fetched from external source'
    )
    ocr_status = fields.Selection(
        selection=[
            ('pending', 'Pending OCR'),
            ('processing', 'Processing'),
            ('completed', 'OCR Completed'),
            ('error', 'OCR Error')
        ],
        string='OCR Status',
        default='pending',
        index=True,
        help='Status of OCR processing for documents from external sources'
    )
    ocr_error_message = fields.Text(
        string='OCR Error Message',
        help='Error message if OCR processing failed'
    )
    gdrive_file_id = fields.Char(
        string='Google Drive File ID',
        index=True,
        help='Google Drive file ID for documents fetched from Drive'
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
    business_id = fields.Char(
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
    contact_country_id = fields.Many2one(
        comodel_name='res.country',
        string='Country',
        help='Country extracted from contact address'
    )
    contact_state_id = fields.Many2one(
        comodel_name='res.country.state',
        string='Province/City',
        help='Province or city extracted from contact address'
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

    # ===== Capacity Column Format Flags =====
    is_capacity_merged_table_1_2 = fields.Boolean(
        string='Table 1.2: Capacity Columns Merged',
        default=True,
        help='True = PDF has 1 merged column. False = PDF has 2 separate columns for cooling and power capacity.'
    )
    is_capacity_merged_table_1_3 = fields.Boolean(
        string='Table 1.3: Capacity Columns Merged',
        default=True,
        help='True = merged column, False = separate columns.'
    )
    is_capacity_merged_table_2_2 = fields.Boolean(
        string='Table 2.2: Capacity Columns Merged',
        default=True,
        help='True = merged column, False = separate columns.'
    )
    is_capacity_merged_table_2_3 = fields.Boolean(
        string='Table 2.3: Capacity Columns Merged',
        default=True,
        help='True = merged column, False = separate columns.'
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

    extraction_job_ids = fields.One2many('extraction.job', 'extraction_id', 'Source job')

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
                # base_url = record.env['ir.config_parameter'].sudo().get_param('web.base.url')
                # if base_url:
                #     record.pdf_url = f"{base_url}/web/content/{record.pdf_attachment_id.id}?download=false"
                # else:
                    record.pdf_url = f'/web/content/{record.pdf_attachment_id.id}?download=false'
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
            self.business_id = partner.business_id
            self.business_license_date = partner.business_license_date
            self.business_license_place = partner.business_license_place
            self.legal_representative_name = partner.legal_representative_name
            self.legal_representative_position = partner.legal_representative_position
            self.contact_person_name = partner.contact_person_name
            self.contact_address = partner.street or partner.street2 or ''
            self.contact_phone = partner.phone
            self.contact_fax = partner.fax
            self.contact_email = partner.email

    # ===== Constraints =====
    @api.constrains('year')
    def _check_year(self):
        """Validate that year is within reasonable range"""
        for record in self:
            if record.year:
                current_year = fields.Date.today().year
                # Allow years from 2000 to current year + 5
                if record.year < 2000 or record.year > current_year + 5:
                    raise ValidationError(
                        f'Year must be between 2000 and {current_year + 5}. '
                        f'Got: {record.year}'
                    )
    @api.onchange('activity_field_ids', 'document_type')
    def _onchange_activity_fields(self):
        """
        Auto-update has_table_x flags when activity_field_ids changes

        This provides real-time UI feedback when user adds/removes activity fields
        """
        if not self.activity_field_ids or not self.document_type:
            return

        # Get activity field codes
        codes = self.activity_field_ids.mapped('code')

        # Update has_table flags based on document type
        if self.document_type == '01':
            self.has_table_1_1 = any(code in codes for code in ['production', 'import', 'export'])
            self.has_table_1_2 = any(code in codes for code in ['equipment_production', 'equipment_import'])
            self.has_table_1_3 = any(code in codes for code in ['ac_ownership', 'refrigeration_ownership'])
            self.has_table_1_4 = 'collection_recycling' in codes
        elif self.document_type == '02':
            self.has_table_2_1 = any(code in codes for code in ['production', 'import', 'export'])
            self.has_table_2_2 = any(code in codes for code in ['equipment_production', 'equipment_import'])
            self.has_table_2_3 = any(code in codes for code in ['ac_ownership', 'refrigeration_ownership'])
            self.has_table_2_4 = 'collection_recycling' in codes

    # ===== Override Create =====
    @api.model_create_multi
    def create(self, vals_list):
        """
        Override create to:
        1. Auto-create organization if not exists
        2. Link PDF attachment to the newly created record
        3. Set OCR status based on source

        Logic:
        - If organization_id empty but business_id exists:
          - Search partner by business_id
          - If found → set organization_id
          - If not found → create new partner → set organization_id
        - If pdf_attachment_id exists, update it with the new res_id
        - If source is 'from_user_upload', set ocr_status to 'completed'
        - If source is 'from_external_source' and ocr_status not set, keep as 'pending'

        FIX: Handle race condition - if another transaction creates the organization
        between our search and create, retry the search
        """
        import psycopg2

        for vals in vals_list:
            # Set OCR status based on source
            if vals.get('source') == 'from_user_upload' and 'ocr_status' not in vals:
                vals['ocr_status'] = 'completed'

            if not vals.get('organization_id') and vals.get('business_id'):
                # Search existing partner by business license number
                partner = self.env['res.partner'].search([
                    '|',
                    ('name', 'ilike', vals.get('organization_name')),
                    ('business_id', '=', vals.get('business_id'))
                ], limit=1)

                if partner:
                    # Partner found → use it
                    vals['organization_id'] = partner.id
                else:
                    # Partner not found → create new
                    partner_vals = {
                        'name': vals.get('organization_name') or 'Unknown Organization',
                        'business_id': vals.get('business_id'),
                        'business_license_date': vals.get('business_license_date'),
                        'business_license_place': vals.get('business_license_place'),
                        'legal_representative_name': vals.get('legal_representative_name'),
                        'legal_representative_position': vals.get('legal_representative_position'),
                        'contact_person_name': vals.get('contact_person_name'),
                        'street': vals.get('contact_address'),
                        'state_id': vals.get('contact_state_id'),
                        'country_id': vals.get('contact_country_id'),
                        'phone': vals.get('contact_phone'),
                        'fax': vals.get('contact_fax'),
                        'email': vals.get('contact_email'),
                        'is_company': True,
                        'company_type': 'company',
                        'x_partner_type': 'organization'
                    }

                    try:
                        # Try to create new partner
                        new_partner = self.env['res.partner'].create(partner_vals)
                        vals['organization_id'] = new_partner.id
                    except psycopg2.IntegrityError:
                        # Race condition: Another transaction created it between search and create
                        # Rollback and retry search
                        self.env.cr.rollback()
                        partner = self.env['res.partner'].search([
                            ('business_id', '=', vals.get('business_id'))
                        ], limit=1)
                        if partner:
                            vals['organization_id'] = partner.id
                        else:
                            # Still not found (shouldn't happen), re-raise
                            raise

        # Create records
        records = super(DocumentExtraction, self).create(vals_list)

        # Link extraction logs to created records
        for record in records:
            if record.extraction_log_id and not record.extraction_log_id.extraction_record_id:
                # Update log to link the created record
                # Status remains 'success' (was set by controller)
                record.extraction_log_id.sudo().write({
                    'extraction_record_id': record.id,
                })

        # Link PDF attachments to created records
        for record in records:
            if record.pdf_attachment_id and record.pdf_attachment_id.res_id == 0:
                # Update attachment with actual res_id
                record.pdf_attachment_id.sudo().write({
                    'res_id': record.id,
                    'public': False,  # Make private now that it's linked to a record
                })

        # Auto-update has_table_x flags based on activity_field_ids
        for record in records:
            if record.activity_field_ids:
                codes = record.activity_field_ids.mapped('code')

                update_vals = {}
                if record.document_type == '01':
                    update_vals.update({
                        'has_table_1_1': any(code in codes for code in ['production', 'import', 'export']),
                        'has_table_1_2': any(code in codes for code in ['equipment_production', 'equipment_import']),
                        'has_table_1_3': any(code in codes for code in ['ac_ownership', 'refrigeration_ownership']),
                        'has_table_1_4': 'collection_recycling' in codes,
                    })
                elif record.document_type == '02':
                    update_vals.update({
                        'has_table_2_1': any(code in codes for code in ['production', 'import', 'export']),
                        'has_table_2_2': any(code in codes for code in ['equipment_production', 'equipment_import']),
                        'has_table_2_3': any(code in codes for code in ['ac_ownership', 'refrigeration_ownership']),
                        'has_table_2_4': 'collection_recycling' in codes,
                    })

                if update_vals:
                    # Use super().write() to avoid triggering our custom write() logic
                    super(DocumentExtraction, record).write(update_vals)

        return records

    def write(self, vals):
        """
        Override write to auto-update has_table_x when activity_field_ids changes

        This ensures has_table flags are always in sync when saving
        """
        result = super(DocumentExtraction, self).write(vals)

        # If activity_field_ids changed, update has_table_x
        if 'activity_field_ids' in vals:
            for record in self:
                codes = record.activity_field_ids.mapped('code')

                update_vals = {}
                if record.document_type == '01':
                    update_vals.update({
                        'has_table_1_1': any(code in codes for code in ['production', 'import', 'export']),
                        'has_table_1_2': any(code in codes for code in ['equipment_production', 'equipment_import']),
                        'has_table_1_3': any(code in codes for code in ['ac_ownership', 'refrigeration_ownership']),
                        'has_table_1_4': 'collection_recycling' in codes,
                    })
                elif record.document_type == '02':
                    update_vals.update({
                        'has_table_2_1': any(code in codes for code in ['production', 'import', 'export']),
                        'has_table_2_2': any(code in codes for code in ['equipment_production', 'equipment_import']),
                        'has_table_2_3': any(code in codes for code in ['ac_ownership', 'refrigeration_ownership']),
                        'has_table_2_4': 'collection_recycling' in codes,
                    })

                if update_vals:
                    # Use super().write() to avoid recursion
                    super(DocumentExtraction, record).write(update_vals)

        return result

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

    def action_bulk_set_draft(self):
        """Bulk set selected documents to draft"""
        self.write({'state': 'draft'})

    def action_bulk_set_validated(self):
        """Bulk set selected documents to validated"""
        self.write({'state': 'validated'})

    def action_bulk_set_completed(self):
        """Bulk set selected documents to completed"""
        self.write({'state': 'completed'})

    def action_view_extraction_log(self):
        """Smart button to view extraction log"""
        self.ensure_one()
        if not self.extraction_log_id:
            return

        return {
            'type': 'ir.actions.act_window',
            'name': 'Extraction Log',
            'res_model': 'google.drive.extraction.log',
            'res_id': self.extraction_log_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_reanalyze_with_ai(self):
        """
        Verify current form data against PDF and suggest corrections

        Returns:
            dict: Action to display JSON result
        """
        self.ensure_one()

        # Validate PDF exists
        if not self.pdf_attachment_id:
            raise ValidationError("No PDF file attached to this record")

        # Get current data JSON
        current_data = self._serialize_current_data()

        # Get PDF binary
        pdf_binary = base64.b64decode(self.pdf_attachment_id.datas)

        # Call verification service
        reanalysis_service = self.env['document.reanalysis.service']

        try:
            delta_changes = reanalysis_service.verify_and_suggest_corrections(
                pdf_binary=pdf_binary,
                current_data=current_data,
                document_type=self.document_type,
                filename=self.pdf_filename or 'document.pdf'
            )
        except Exception as e:
            _logger.error(f"Verification failed: {e}", exc_info=True)
            raise ValidationError(f"Verification failed: {str(e)}")

        # Show result in notification (temporary - sẽ improve sau)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'AI Verification Complete',
                'message': f'Delta changes: {json.dumps(delta_changes, ensure_ascii=False, indent=2)}',
                'type': 'success',
                'sticky': True,
            }
        }

    def _serialize_current_data(self):
        """
        Serialize current form state to JSON

        Returns:
            dict: Current form data
        """
        self.ensure_one()

        data = {
            'year': self.year,
            'year_1': self.year_1,
            'year_2': self.year_2,
            'year_3': self.year_3,
            'organization_name': self.organization_name,
            'business_id': self.business_id,
            'business_license_date': str(self.business_license_date) if self.business_license_date else None,
            'business_license_place': self.business_license_place,
            'legal_representative_name': self.legal_representative_name,
            'legal_representative_position': self.legal_representative_position,
            'contact_person_name': self.contact_person_name,
            'contact_address': self.contact_address,
            'contact_phone': self.contact_phone,
            'contact_fax': self.contact_fax,
            'contact_email': self.contact_email,
            'contact_country_code': self.contact_country_id.code if self.contact_country_id else None,
            'contact_state_code': self.contact_state_id.code if self.contact_state_id else None,
            'activity_field_codes': self.activity_field_ids.mapped('code'),
        }

        # Add table data
        if self.document_type == '01':
            data.update({
                'has_table_1_1': self.has_table_1_1,
                'has_table_1_2': self.has_table_1_2,
                'has_table_1_3': self.has_table_1_3,
                'has_table_1_4': self.has_table_1_4,
                'substance_usage': self._serialize_one2many(self.substance_usage_ids),
                'equipment_product': self._serialize_one2many(self.equipment_product_ids),
                'equipment_ownership': self._serialize_one2many(self.equipment_ownership_ids),
                'collection_recycling': self._serialize_one2many(self.collection_recycling_ids),
            })
        else:  # '02'
            data.update({
                'has_table_2_1': self.has_table_2_1,
                'has_table_2_2': self.has_table_2_2,
                'has_table_2_3': self.has_table_2_3,
                'has_table_2_4': self.has_table_2_4,
                'quota_usage': self._serialize_one2many(self.quota_usage_ids),
                'equipment_product_report': self._serialize_one2many(self.equipment_product_report_ids),
                'equipment_ownership_report': self._serialize_one2many(self.equipment_ownership_report_ids),
                'collection_recycling_report': self._serialize_one2many(self.collection_recycling_report_ids),
            })

        return data

    def _serialize_one2many(self, recordset):
        """
        Serialize One2many recordset to list of dicts

        Args:
            recordset: One2many recordset

        Returns:
            list: List of dicts with record data
        """
        result = []
        for record in recordset:
            vals = {'id': record.id, 'sequence': record.sequence if 'sequence' in record._fields else None}

            for field_name, field in record._fields.items():
                # Skip technical fields
                if field_name in ['create_uid', 'create_date', 'write_uid', 'write_date',
                                '__last_update', 'document_id', 'display_name', 'id']:
                    continue

                value = record[field_name]

                # Handle Many2one
                if field.type == 'many2one' and value:
                    vals[field_name] = value.name
                # Handle date/datetime
                elif field.type in ['date', 'datetime'] and value:
                    vals[field_name] = str(value)
                else:
                    vals[field_name] = value

            result.append(vals)

        return result

    def update_all_title_selections(self, exclude_existing=True):
        """
        Cron job: Auto-update selection fields for all title rows across all documents
        
        This method:
        1. Iterates through all document.extraction records
        2. For each document, processes 7 table types (1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3)
        3. Finds title rows (is_title=True) with empty selection values
        4. Matches text against keywords using fuzzy matching
        5. Updates selection field with matched value
        6. Logs all actions (updated, skipped, errors)
        7. Creates detailed CSV log for suspicious records (fuzzy < 90% or default)
        
        Usage:
        - Run manually: document_extraction_obj.update_all_title_selections()
        - Run via cron: Enable scheduled action in Settings > Technical > Scheduled Actions
        
        Returns:
            dict: Notification action with log file path
        """
        import csv
        from datetime import datetime
        import os
        
        _logger.info("=" * 60)
        _logger.info("Starting Title Selection Auto-Update Job")
        _logger.info("=" * 60)
        
        # Create log file with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_filename = f'title_selection_update_{timestamp}.csv'
        log_filepath = os.path.join('/tmp', log_filename)
        
        # Prepare CSV file
        csv_file = open(log_filepath, 'w', newline='', encoding='utf-8')
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow([
            'Document ID',
            'Document Name',
            'Table Name',
            'Record ID',
            'Text Value',
            'Matched Selection',
            'Confidence (%)',
            'Match Type',
            'Notes'
        ])
        
        # Get all documents
        all_documents = self.search([])
        total_docs = len(all_documents)
        _logger.info(f"Found {total_docs} documents to process")
        
        # Statistics
        stats = {
            'total_processed': 0,
            'total_updated': 0,
            'total_skipped': 0,
            'total_errors': 0,
            'by_confidence': {'exact': 0, 'fuzzy': 0, 'default': 0},
            'suspicious_count': 0,  # fuzzy < 85% or default
            'docs_without_titles': 0  # documents with no title rows found
        }

        # Process each document
        for doc_idx, document in enumerate(all_documents, 1):
            _logger.info(f"\n[{doc_idx}/{total_docs}] Processing document: {document.name} (ID: {document.id})")

            doc_has_title_rows = False  # Track if this document has any title rows

            try:
                # Process each table type
                for model_name, config in TITLE_KEYWORD_CONFIG.items():
                    field_name = config['field_name']
                    
                    # Skip if document doesn't have this field
                    if not hasattr(document, field_name):
                        continue
                    
                    records = getattr(document, field_name)

                    # Filter title rows with empty selection
                    title_rows = records.filtered(
                        lambda r: r.is_title and (not r[config['selection_field']] and exclude_existing)
                    )

                    if not title_rows:
                        continue

                    # Mark that this document has title rows
                    doc_has_title_rows = True

                    _logger.info(f"  Table {model_name}: Found {len(title_rows)} title rows to update")
                    
                    # Process each title row
                    for record in title_rows:
                        stats['total_processed'] += 1
                        
                        text_value = record[config['text_field']]

                        # Match selection value (with templates for exact matching)
                        matched_value, confidence, match_type = match_title_selection(
                            text_value,
                            config.get('templates', {}),
                            config['mappings'],
                            config['default']
                        )
                        
                        # Update record
                        try:
                            record.write({config['selection_field']: matched_value})
                            stats['total_updated'] += 1

                            # Track by confidence type
                            if match_type not in stats['by_confidence']:
                                stats['by_confidence'][match_type] = 0
                            stats['by_confidence'][match_type] += 1

                            # Determine if this is suspicious (needs review)
                            is_suspicious = (match_type == 'default') or (
                                match_type in ['fuzzy_prefix', 'fuzzy_full'] and confidence < 85
                            )

                            if is_suspicious:
                                stats['suspicious_count'] += 1
                                notes = ''
                                if match_type == 'default':
                                    notes = 'NO MATCH - Used default value'
                                elif confidence < 85:
                                    notes = f'LOW CONFIDENCE - Match below 85%'

                                # Write to CSV (only suspicious records)
                                csv_writer.writerow([
                                    document.id,
                                    document.name,
                                    model_name,
                                    record.id,
                                    text_value or '',
                                    matched_value,
                                    confidence,
                                    match_type,
                                    notes
                                ])

                            # Log based on match type
                            if match_type == 'template':
                                _logger.info(f"    ✓ Updated {model_name} #{record.id}: '{text_value}' → '{matched_value}' (template exact match)")
                            elif match_type == 'fuzzy_prefix':
                                if confidence < 85:
                                    _logger.warning(f"    ⚠ Updated {model_name} #{record.id}: '{text_value}' → '{matched_value}' (prefix fuzzy: {confidence}%) - LOW CONFIDENCE")
                                else:
                                    _logger.info(f"    ✓ Updated {model_name} #{record.id}: '{text_value}' → '{matched_value}' (prefix fuzzy: {confidence}%)")
                            elif match_type == 'fuzzy_full':
                                if confidence < 85:
                                    _logger.warning(f"    ⚠ Updated {model_name} #{record.id}: '{text_value}' → '{matched_value}' (full fuzzy: {confidence}%) - LOW CONFIDENCE")
                                else:
                                    _logger.info(f"    ✓ Updated {model_name} #{record.id}: '{text_value}' → '{matched_value}' (full fuzzy: {confidence}%)")
                            else:  # default
                                _logger.warning(f"    ⊘ Updated {model_name} #{record.id}: '{text_value}' → '{matched_value}' (default - NO MATCH)")
                        
                        except Exception as e:
                            stats['total_errors'] += 1
                            _logger.error(f"    ✗ Error updating {model_name} #{record.id}: {str(e)}")
                            
                            # Log error to CSV
                            csv_writer.writerow([
                                document.id,
                                document.name,
                                model_name,
                                record.id,
                                text_value or '',
                                '',
                                0,
                                'error',
                                f'ERROR: {str(e)}'
                            ])

                # Check if document has no title rows at all
                if not doc_has_title_rows:
                    stats['docs_without_titles'] += 1
                    _logger.warning(f"  ⚠ Document {document.id} ({document.name}) has NO title rows (is_title=True) to process")

                    # Write to CSV for tracking
                    csv_writer.writerow([
                        document.id,
                        document.name,
                        'N/A',
                        'N/A',
                        'N/A',
                        'N/A',
                        0,
                        'no_titles',
                        'WARNING: Document has no title rows (is_title=True) in any table'
                    ])

                # Commit after each document
                # self.env.cr.commit()

            except Exception as e:
                stats['total_errors'] += 1
                _logger.error(f"  ✗ Error processing document {document.id}: {str(e)}")
                raise e
                # self.env.cr.rollback()
        
        # Close CSV file
        csv_file.close()
        
        # Print summary
        _logger.info("\n" + "=" * 60)
        _logger.info("Title Selection Update - Summary Report")
        _logger.info("=" * 60)
        _logger.info(f"Documents processed: {total_docs}")
        _logger.info(f"Title rows processed: {stats['total_processed']}")
        _logger.info(f"  ✓ Successfully updated: {stats['total_updated']}")
        _logger.info(f"  ⊘ Skipped: {stats['total_skipped']}")
        _logger.info(f"  ✗ Errors: {stats['total_errors']}")
        _logger.info("\nMatch Type Distribution:")
        _logger.info(f"  Template exact matches (100%): {stats['by_confidence'].get('template', 0)}")
        _logger.info(f"  Fuzzy prefix matches (4 words): {stats['by_confidence'].get('fuzzy_prefix', 0)}")
        _logger.info(f"  Fuzzy full text matches: {stats['by_confidence'].get('fuzzy_full', 0)}")
        _logger.info(f"  Default values (no match): {stats['by_confidence'].get('default', 0)}")
        _logger.info(f"\n⚠ Suspicious records (need review): {stats['suspicious_count']}")
        _logger.info(f"⚠ Documents without title rows: {stats['docs_without_titles']}")
        _logger.info(f"📄 Detailed CSV log: {log_filepath}")
        _logger.info("=" * 60)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Title Selection Update Complete',
                'message': f"Updated {stats['total_updated']} title rows across {total_docs} documents.\n"
                          f"⚠ {stats['suspicious_count']} suspicious records need review.\n"
                          f"⚠ {stats['docs_without_titles']} documents have NO title rows.\n"
                          f"📄 Log file: {log_filepath}",
                'type': 'success' if (stats['suspicious_count'] == 0 and stats['docs_without_titles'] == 0) else 'warning',
                'sticky': True,
            }
        }

    def update_equipment_table_titles(self):
        """
        One-time update: Fix production_type for equipment tables (1.2 and 2.2)
        
        This method specifically handles the issue where titles like:
        "Nhập khẩu thiết bị, sản phẩm có chứa hoặc sản xuất từ chất được kiểm soát"
        were incorrectly matched as 'production' instead of 'import' due to 
        the word "sản xuất" appearing at the end.
        
        Solution: Use first 4 words for matching priority
        
        Usage:
        - Run manually: env['document.extraction'].update_equipment_table_titles()
        - Run via cron: Enable scheduled action
        """
        try:
            from rapidfuzz import fuzz
            from unidecode import unidecode
        except ImportError:
            _logger.error("Missing dependencies: rapidfuzz or unidecode")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': 'Missing dependencies: rapidfuzz or unidecode',
                    'type': 'danger',
                }
            }
        
        _logger.info("=" * 60)
        _logger.info("Equipment Tables Title Update (1.2 & 2.2)")
        _logger.info("=" * 60)
        
        # Get all documents
        all_documents = self.search(['|', ('has_table_1_2', '=', True), ('has_table_2_2', '=', True)])
        total_docs = len(all_documents)
        _logger.info(f"Found {total_docs} documents to process")
        
        # Statistics
        stats = {
            'total_processed': 0,
            'total_updated': 0,
            'total_unchanged': 0,
            'total_errors': 0,
            'by_table': {
                'equipment.product': {'updated': 0, 'unchanged': 0},
                'equipment.product.report': {'updated': 0, 'unchanged': 0}
            }
        }
        
        # Configuration for equipment tables only
        EQUIPMENT_CONFIG = {
            'equipment.product': {
                'field_name': 'equipment_product_ids',
                'text_field': 'product_type',
                'selection_field': 'production_type',
                'templates': {
                    'production': 'Sản xuất thiết bị, sản phẩm có chứa hoặc sản xuất từ chất được kiểm soát',
                    'import': 'Nhập khẩu thiết bị, sản phẩm có chứa hoặc sản xuất từ chất được kiểm soát'
                },
                'keywords': {
                    'production': ['sản xuất thiết bị', 'sản xuất sản phẩm', 'san xuat thiet bi', 'production equipment'],
                    'import': ['nhập khẩu thiết bị', 'nhập khẩu sản phẩm', 'nhap khau thiet bi', 'import equipment']
                },
                'default': 'production'
            },
            'equipment.product.report': {
                'field_name': 'equipment_product_report_ids',
                'text_field': 'product_type',
                'selection_field': 'production_type',
                'templates': {
                    'production': 'Sản xuất thiết bị, sản phẩm có chứa hoặc sản xuất từ chất được kiểm soát',
                    'import': 'Nhập khẩu thiết bị, sản phẩm có chứa hoặc sản xuất từ chất được kiểm soát'
                },
                'keywords': {
                    'production': ['sản xuất thiết bị', 'sản xuất sản phẩm', 'san xuat thiet bi', 'production equipment'],
                    'import': ['nhập khẩu thiết bị', 'nhập khẩu sản phẩm', 'nhap khau thiet bi', 'import equipment']
                },
                'default': 'import'
            }
        }
        
        # Process each document
        for doc_idx, document in enumerate(all_documents, 1):
            _logger.info(f"\n[{doc_idx}/{total_docs}] Processing document: {document.name} (ID: {document.id})")
            
            try:
                # Process each table type
                for model_name, config in EQUIPMENT_CONFIG.items():
                    field_name = config['field_name']
                    
                    # Skip if document doesn't have this field
                    if not hasattr(document, field_name):
                        continue
                    
                    records = getattr(document, field_name)
                    
                    # Filter title rows only
                    title_rows = records.filtered(lambda r: r.is_title)
                    
                    if not title_rows:
                        continue
                    
                    _logger.info(f"  Table {model_name}: Found {len(title_rows)} title rows")
                    
                    # Process each title row
                    for record in title_rows:
                        stats['total_processed'] += 1
                        
                        text_value = record[config['text_field']] or ''
                        current_value = record[config['selection_field']]
                        
                        # Normalize text
                        normalized_text = unidecode(text_value.lower().strip())
                        
                        # Extract first 4 words
                        words = normalized_text.split()
                        first_4_words = ' '.join(words[:4]) if len(words) >= 4 else normalized_text
                        
                        matched_value = None
                        match_type = None
                        confidence = 0
                        
                        # Strategy 1: Template exact match
                        for selection_value, template_text in config['templates'].items():
                            normalized_template = unidecode(template_text.lower().strip())
                            if normalized_text == normalized_template:
                                matched_value = selection_value
                                match_type = 'template'
                                confidence = 100
                                break
                        
                        # Strategy 2: Fuzzy prefix match (4 words)
                        if not matched_value:
                            best_score = 0
                            for selection_value, keywords in config['keywords'].items():
                                for keyword in keywords:
                                    normalized_keyword = unidecode(keyword.lower().strip())
                                    score = fuzz.partial_ratio(first_4_words, normalized_keyword)
                                    
                                    if score > best_score:
                                        best_score = score
                                        if score >= 80:
                                            matched_value = selection_value
                                            match_type = 'fuzzy_prefix'
                                            confidence = score
                        
                        # Strategy 3: Fuzzy full text (fallback)
                        if not matched_value:
                            best_score = 0
                            for selection_value, keywords in config['keywords'].items():
                                for keyword in keywords:
                                    normalized_keyword = unidecode(keyword.lower().strip())
                                    score = fuzz.partial_ratio(normalized_text, normalized_keyword)
                                    
                                    if score > best_score:
                                        best_score = score
                                        if score >= 70:
                                            matched_value = selection_value
                                            match_type = 'fuzzy_full'
                                            confidence = score
                        
                        # Use default if no match
                        if not matched_value:
                            matched_value = config['default']
                            match_type = 'default'
                            confidence = 0
                        
                        # Update if different from current value
                        try:
                            if matched_value != current_value:
                                record.write({config['selection_field']: matched_value})
                                stats['total_updated'] += 1
                                stats['by_table'][model_name]['updated'] += 1
                                
                                _logger.info(
                                    f"    ✓ Updated {model_name} #{record.id}: "
                                    f"'{text_value}' → '{current_value}' ➜ '{matched_value}' "
                                    f"({match_type}: {confidence}%)"
                                )
                            else:
                                stats['total_unchanged'] += 1
                                stats['by_table'][model_name]['unchanged'] += 1
                                _logger.debug(
                                    f"    - Unchanged {model_name} #{record.id}: "
                                    f"'{text_value}' = '{matched_value}'"
                                )
                        
                        except Exception as e:
                            stats['total_errors'] += 1
                            _logger.error(f"    ✗ Error updating {model_name} #{record.id}: {str(e)}")
                
            except Exception as e:
                stats['total_errors'] += 1
                _logger.error(f"  ✗ Error processing document {document.id}: {str(e)}")
                self.env.cr.rollback()
        
        # Print summary
        _logger.info("\n" + "=" * 60)
        _logger.info("Equipment Tables Update - Summary Report")
        _logger.info("=" * 60)
        _logger.info(f"Documents processed: {total_docs}")
        _logger.info(f"Title rows processed: {stats['total_processed']}")
        _logger.info(f"  ✓ Updated: {stats['total_updated']}")
        _logger.info(f"  - Unchanged: {stats['total_unchanged']}")
        _logger.info(f"  ✗ Errors: {stats['total_errors']}")
        _logger.info("\nBy Table:")
        _logger.info(f"  equipment.product (1.2):")
        _logger.info(f"    - Updated: {stats['by_table']['equipment.product']['updated']}")
        _logger.info(f"    - Unchanged: {stats['by_table']['equipment.product']['unchanged']}")
        _logger.info(f"  equipment.product.report (2.2):")
        _logger.info(f"    - Updated: {stats['by_table']['equipment.product.report']['updated']}")
        _logger.info(f"    - Unchanged: {stats['by_table']['equipment.product.report']['unchanged']}")
        _logger.info("=" * 60)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Equipment Tables Update Complete',
                'message': f"Updated {stats['total_updated']} title rows in tables 1.2 and 2.2.\n"
                          f"Unchanged: {stats['total_unchanged']}\n"
                          f"Errors: {stats['total_errors']}",
                'type': 'success' if stats['total_errors'] == 0 else 'warning',
                'sticky': True,
            }
        }

    def update_titles_matched_only(self):
        """
        One-time update: Update ONLY title rows that have a good match (>= 70%)
        Do NOT use default values for unmatched titles - leave them as-is
        
        This is useful when you want to:
        - Fix only the obvious matches
        - Leave uncertain cases for manual review
        - Avoid auto-filling defaults on unclear titles
        
        Usage:
        - Run manually: env['document.extraction'].update_titles_matched_only()
        - Run via cron: Create scheduled action
        """
        _logger.info("=" * 60)
        _logger.info("Update Titles - Matched Only (No Defaults)")
        _logger.info("=" * 60)
        
        all_documents = self.search([])
        total_docs = len(all_documents)
        _logger.info(f"Found {total_docs} documents to process")
        
        stats = {
            'total_processed': 0,
            'total_updated': 0,
            'total_skipped': 0,
            'by_match_type': {
                'template': 0,
                'fuzzy_prefix': 0,
                'fuzzy_full': 0,
                'no_match': 0
            }
        }
        
        for doc_idx, document in enumerate(all_documents, 1):
            _logger.info(f"\n[{doc_idx}/{total_docs}] Processing: {document.name} (ID: {document.id})")
            
            try:
                for model_name, config in TITLE_KEYWORD_CONFIG.items():
                    field_name = config['field_name']
                    
                    if not hasattr(document, field_name):
                        continue
                    
                    records = getattr(document, field_name)
                    title_rows = records.filtered(lambda r: r.is_title)
                    
                    if not title_rows:
                        continue
                    
                    for record in title_rows:
                        stats['total_processed'] += 1
                        text_value = record[config['text_field']] or ''
                        current_value = record[config['selection_field']]
                        
                        # Match with use_default=False
                        matched_value, confidence, match_type = match_title_selection(
                            text_value,
                            config.get('templates', {}),
                            config['mappings'],
                            config['default'],
                            use_default=False  # ← DO NOT use default
                        )
                        
                        # Track match type
                        stats['by_match_type'][match_type] = stats['by_match_type'].get(match_type, 0) + 1
                        
                        # Only update if we found a real match
                        if matched_value and matched_value != current_value:
                            record.write({config['selection_field']: matched_value})
                            stats['total_updated'] += 1
                            _logger.info(
                                f"  ✓ Updated {model_name} #{record.id}: "
                                f"'{text_value}' → '{matched_value}' ({match_type}: {confidence}%)"
                            )
                        elif match_type == 'no_match':
                            stats['total_skipped'] += 1
                            _logger.info(
                                f"  ⊘ Skipped {model_name} #{record.id}: "
                                f"'{text_value}' - No match found (current: '{current_value}')"
                            )
                        else:
                            stats['total_skipped'] += 1
                
                # Commit after each document
                self.env.cr.commit()
                
            except Exception as e:
                _logger.error(f"  ✗ Error processing document {document.id}: {str(e)}")
                self.env.cr.rollback()
        
        # Summary
        _logger.info("\n" + "=" * 60)
        _logger.info("Update Summary - Matched Only")
        _logger.info("=" * 60)
        _logger.info(f"Documents processed: {total_docs}")
        _logger.info(f"Title rows processed: {stats['total_processed']}")
        _logger.info(f"  ✓ Updated (matched): {stats['total_updated']}")
        _logger.info(f"  ⊘ Skipped (no match): {stats['total_skipped']}")
        _logger.info("\nMatch Type Distribution:")
        _logger.info(f"  Template exact: {stats['by_match_type'].get('template', 0)}")
        _logger.info(f"  Fuzzy prefix: {stats['by_match_type'].get('fuzzy_prefix', 0)}")
        _logger.info(f"  Fuzzy full: {stats['by_match_type'].get('fuzzy_full', 0)}")
        _logger.info(f"  No match (skipped): {stats['by_match_type'].get('no_match', 0)}")
        _logger.info("=" * 60)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Title Update Complete (Matched Only)',
                'message': f"Updated {stats['total_updated']} matched titles.\n"
                          f"Skipped {stats['total_skipped']} unmatched titles (no defaults used).",
                'type': 'success',
                'sticky': True,
            }
        }
