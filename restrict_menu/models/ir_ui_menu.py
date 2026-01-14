from odoo import models, fields, api

class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'
    
    shown_for_user_ids = fields.Many2many('res.users',
        relation="menu_user_rel",
        column1='menu_id',
        column2='user_id',
        string="Shown For Users")

    @api.model
    def _visible_menu_ids(self, debug=False):
        visible_menus = super()._visible_menu_ids(debug=debug)
        
        if self.env.user.is_admin:
            return visible_menus
            
        allowed_menu_ids = set()
        
        root_menus = self.env.user.show_menu_ids
        
        for menu in root_menus:
            allowed_menu_ids.add(menu.id)
            child_menus = self.with_context({'ir.ui.menu.full_list': True}).search([('parent_path', 'like', f'{menu.parent_path}%')])
            allowed_menu_ids.update(child_menus.ids)
        
        return visible_menus & set(allowed_menu_ids)