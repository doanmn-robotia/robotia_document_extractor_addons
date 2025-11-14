# -*- coding: utf-8 -*-

from odoo import models, fields


class ActivityField(models.Model):
    """Master data for activity fields (Production, Import, Export, etc.)"""
    _name = 'activity.field'
    _description = 'Activity Field'
    _order = 'sequence, name'

    name = fields.Char(
        string='Activity Field',
        required=True,
        translate=True
    )
    code = fields.Char(
        string='Code',
        required=True,
        index=True
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10
    )
    description = fields.Text(
        string='Description',
        translate=True
    )
    active = fields.Boolean(
        string='Active',
        default=True
    )

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'The activity field code must be unique!')
    ]
