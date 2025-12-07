# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ResUsers(models.Model):
    _inherit = 'res.users'

    is_doc_admin = fields.Boolean(
        string="Document Admin",
        compute="_compute_doc_roles",
        store=False
    )
    is_doc_maker = fields.Boolean(
        string="Document Maker",
        compute="_compute_doc_roles",
        store=False
    )
    is_doc_checker = fields.Boolean(
        string="Document Checker",
        compute="_compute_doc_roles",
        store=False
    )
    is_system_admin = fields.Boolean(
        string="System Admin",
        compute="_compute_doc_roles",
        store=False
    )

    @api.depends('groups_id')
    def _compute_doc_roles(self):
        admin_group = self.env.ref('robotia_document_extractor.group_document_extractor_admin', raise_if_not_found=False)
        maker_group = self.env.ref('robotia_document_extractor.group_document_extractor_maker', raise_if_not_found=False)
        checker_group = self.env.ref('robotia_document_extractor.group_document_extractor_checker', raise_if_not_found=False)
        system_group = self.env.ref('base.group_system', raise_if_not_found=False)

        for user in self:
            user.is_doc_admin = admin_group and admin_group in user.groups_id
            user.is_doc_maker = maker_group and maker_group in user.groups_id
            user.is_doc_checker = checker_group and checker_group in user.groups_id
            user.is_system_admin = system_group and system_group in user.groups_id
