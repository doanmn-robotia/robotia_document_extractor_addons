# -*- coding: utf-8 -*-
from . import models
from . import controllers
from odoo import fields


def installed_hook(env):
    # my_group = env.ref('restrict_menu.groups_internal_common')
    # menus = env['ir.ui.menu'].search([])

    # for menu in menus:
    #     menu.groups_id = [fields.Command.link(my_group.id)]
    pass

def uninstall_hook(env):
    # default_user = env.ref('base.default_user')
    # group_internal = env.ref('base.group_user')

    # default_user.groups_id = fields.Command.link(group_internal.id)

    print("Uninstall Restrict Menu Successfully!")