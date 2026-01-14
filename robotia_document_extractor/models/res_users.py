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
    is_doc_viewer = fields.Boolean(
        string="Document Viewer",
        compute="_compute_doc_roles",
        store=False
    )
    is_system_admin = fields.Boolean(
        string="System Admin",
        compute="_compute_doc_roles",
        store=False
    )

    document_extractor_group = fields.Selection(
        selection=[
            ('none', 'No Role'),
            ('viewer', 'Viewer'),
            ('checker', 'Checker'),
            ('maker', 'Maker'),
            ('admin', 'Admin'),
        ],
        string="Document Extractor Role",
        compute="_compute_document_extractor_group",
        inverse="_inverse_document_extractor_group",
        store=False,
        help="User's role in Document Extractor module"
    )

    @api.depends('groups_id')
    def _compute_doc_roles(self):
        admin_group = self.env.ref('robotia_document_extractor.group_document_extractor_admin', raise_if_not_found=False)
        maker_group = self.env.ref('robotia_document_extractor.group_document_extractor_maker', raise_if_not_found=False)
        checker_group = self.env.ref('robotia_document_extractor.group_document_extractor_checker', raise_if_not_found=False)
        viewer_group = self.env.ref('robotia_document_extractor.group_document_extractor_viewer', raise_if_not_found=False)
        system_group = self.env.ref('base.group_system', raise_if_not_found=False)

        for user in self:
            user.is_doc_admin = admin_group and admin_group in user.groups_id
            user.is_doc_maker = maker_group and maker_group in user.groups_id
            user.is_doc_checker = checker_group and checker_group in user.groups_id
            user.is_doc_viewer = viewer_group and viewer_group in user.groups_id
            user.is_system_admin = system_group and system_group in user.groups_id

    @api.depends('groups_id')
    def _compute_document_extractor_group(self):
        """Determine which Document Extractor group the user belongs to"""
        admin_group = self.env.ref('robotia_document_extractor.group_document_extractor_admin', raise_if_not_found=False)
        maker_group = self.env.ref('robotia_document_extractor.group_document_extractor_maker', raise_if_not_found=False)
        checker_group = self.env.ref('robotia_document_extractor.group_document_extractor_checker', raise_if_not_found=False)
        viewer_group = self.env.ref('robotia_document_extractor.group_document_extractor_viewer', raise_if_not_found=False)

        for user in self:
            if admin_group and admin_group in user.groups_id:
                user.document_extractor_group = 'admin'
            elif maker_group and maker_group in user.groups_id:
                user.document_extractor_group = 'maker'
            elif checker_group and checker_group in user.groups_id:
                user.document_extractor_group = 'checker'
            elif viewer_group and viewer_group in user.groups_id:
                user.document_extractor_group = 'viewer'
            else:
                user.document_extractor_group = 'none'

    def _inverse_document_extractor_group(self):
        """Update user's Document Extractor group membership"""
        admin_group = self.env.ref('robotia_document_extractor.group_document_extractor_admin', raise_if_not_found=False)
        maker_group = self.env.ref('robotia_document_extractor.group_document_extractor_maker', raise_if_not_found=False)
        checker_group = self.env.ref('robotia_document_extractor.group_document_extractor_checker', raise_if_not_found=False)
        viewer_group = self.env.ref('robotia_document_extractor.group_document_extractor_viewer', raise_if_not_found=False)

        all_doc_groups = [admin_group, maker_group, checker_group, viewer_group]
        all_doc_groups = [g for g in all_doc_groups if g]  # Filter out None values

        for user in self:
            # Build list of commands: remove all doc groups, then add selected one
            commands = []

            # Remove all Document Extractor groups
            for group in all_doc_groups:
                if group in user.groups_id:
                    commands.append((3, group.id))

            # Add the selected group
            if user.document_extractor_group == 'admin' and admin_group:
                commands.append((4, admin_group.id))
            elif user.document_extractor_group == 'maker' and maker_group:
                commands.append((4, maker_group.id))
            elif user.document_extractor_group == 'checker' and checker_group:
                commands.append((4, checker_group.id))
            elif user.document_extractor_group == 'viewer' and viewer_group:
                commands.append((4, viewer_group.id))
            # If 'none', only removal commands (no add command)

            # Apply all commands at once
            if commands:
                user.groups_id = commands
