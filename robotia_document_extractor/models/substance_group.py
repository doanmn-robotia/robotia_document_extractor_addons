# -*- coding: utf-8 -*-

from odoo import models, fields, api


class SubstanceGroup(models.Model):
    """
    Master data for substance grouping (HFC, HCFC, CFC, PFC, HFO, etc.)
    Used to categorize controlled substances for reporting and filtering
    """
    _name = 'substance.group'
    _description = 'Substance Group'
    _order = 'sequence, name'

    # ===== Core Fields =====
    name = fields.Char(
        string='Group Name',
        required=True,
        translate=True,
        index=True,
        help='Name of substance group (e.g., HFC, HCFC, CFC)'
    )
    code = fields.Char(
        string='Code',
        required=True,
        index=True,
        help='Short code for group (uppercase, no spaces)'
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help='Display order in lists and dropdowns'
    )
    description = fields.Text(
        string='Description',
        translate=True,
        help='Detailed description of this substance group'
    )

    # ===== Relational Fields =====
    substance_ids = fields.One2many(
        comodel_name='controlled.substance',
        inverse_name='substance_group_id',
        string='Substances in Group',
        help='All substances belonging to this group'
    )
    substance_count = fields.Integer(
        string='Substance Count',
        compute='_compute_substance_count',
        store=True,
        help='Number of substances in this group'
    )

    # ===== Metadata Fields =====
    active = fields.Boolean(
        string='Active',
        default=True,
        help='Uncheck to hide this group from filters'
    )
    color = fields.Integer(
        string='Color Index',
        default=0,
        help='Color for UI display (0-11 Odoo color palette)'
    )
    needs_review = fields.Boolean(
        string='Needs Review',
        default=False,
        help='Flag for auto-created records that need admin review'
    )
    created_from_extraction = fields.Boolean(
        string='Created from Extraction',
        default=False,
        help='Created automatically during document extraction'
    )

    # ===== SQL Constraints =====
    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'The substance group code must be unique!'),
        ('name_unique', 'UNIQUE(name)', 'The substance group name must be unique!')
    ]

    # ===== Compute Methods =====
    @api.depends('substance_ids')
    def _compute_substance_count(self):
        """Compute number of substances in this group"""
        for record in self:
            record.substance_count = len(record.substance_ids)

    # ===== Override Methods =====
    @api.model
    def name_create(self, name):
        """
        Override to support quick create from Many2one fields
        Auto-generate code from name and mark for review
        """
        # Generate code from name (uppercase, replace spaces with underscores)
        code = name.upper().replace(' ', '_').replace('-', '_')

        # Check if code already exists
        existing = self.search([('code', '=', code)], limit=1)
        if existing:
            return existing.id, existing.display_name

        # Create new record
        record = self.create({
            'name': name,
            'code': code,
            'needs_review': True,
            'created_from_extraction': True
        })
        return record.id, record.display_name

    def name_get(self):
        """
        Override to display code with name for better readability
        """
        result = []
        for record in self:
            name = f"[{record.code}] {record.name}"
            result.append((record.id, name))
        return result

    # ===== Action Methods =====
    def action_view_substances(self):
        """
        Action to view all substances in this group
        """
        self.ensure_one()
        return {
            'name': f'Substances in {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'controlled.substance',
            'view_mode': 'list,form',
            'domain': [('substance_group_id', '=', self.id)],
            'context': {
                'default_substance_group_id': self.id,
            }
        }
