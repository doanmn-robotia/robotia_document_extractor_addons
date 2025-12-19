# -*- coding: utf-8 -*-

from odoo import models, fields


class ResPartner(models.Model):
    """Extend res.partner to add organization-specific fields"""
    _inherit = 'res.partner'

    # Business License Info
    business_id = fields.Char(
        string='Business License Number',
        help='Mã số doanh nghiệp',
        index=True
    )
    business_license_date = fields.Date(
        string='Business License Date',
        help='Ngày cấp giấy phép đăng ký kinh doanh'
    )
    business_license_place = fields.Char(
        string='Business License Place',
        help='Nơi cấp giấy phép'
    )

    # Legal Representative
    legal_representative_name = fields.Char(
        string='Legal Representative',
        help='Tên người đại diện theo pháp luật'
    )
    legal_representative_position = fields.Char(
        string='Legal Representative Position',
        help='Chức vụ người đại diện'
    )

    # Contact Person (different from legal representative)
    contact_person_name = fields.Char(
        string='Contact Person',
        help='Tên người đại diện liên lạc'
    )

    # Additional fields (fax may not exist in base)
    fax = fields.Char(
        string='Fax'
    )

    # Partner type for filtering
    x_partner_type = fields.Selection(
        selection=[
            ('standard', 'Standard Contact'),
            ('organization', 'Controlled Substance Organization'),
        ],
        string='Partner Type',
        default='standard',
        help='Type of partner for filtering in document extractor module'
    )

    _sql_constraints = [
        ('business_id_unique',
         'UNIQUE(business_id)',
         'The business license number must be unique!')
    ]

    def action_view_dashboard(self):
        """Open company dashboard with analytics"""
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'document_extractor.company_dashboard',
            'context': {
                'default_organization_id': self.id,
                'default_organization_name': self.name,
            },
            'name': f'Dashboard - {self.name}'
        }
