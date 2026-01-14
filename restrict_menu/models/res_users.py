from odoo import fields, models, api
import logging

logger = logging.getLogger(__name__)

class ResUsers(models.Model):
    _inherit = 'res.users'

    def _get_is_admin(self):
        for rec in self:
            rec.is_admin = rec.has_group('base.group_system')

    show_menu_ids = fields.Many2many(
        'ir.ui.menu', 
        string="Show menus",
        relation="menu_user_rel",
        column1='user_id',
        column2='menu_id', 
        domain=[('parent_id', '=', False)],  # Only root menus
        help='Select root menu items that will be shown to this user. All child menus will be shown automatically.'
    )

    is_admin = fields.Boolean(
        compute=_get_is_admin, 
        string="Is Admin",
        store=True,
        help='Check if the user is an admin.'
    )
    
    @api.model_create_single
    def create(self, vals):
        res = super().create(vals)
        
        try:
            if not res.is_admin:
                dashboard_menu = self.env.ref('dashboard.company_dashboard_menu', raise_if_not_found=False)
                if dashboard_menu:
                    res.show_menu_ids = [(4, dashboard_menu.id)]
                else:
                    logger.warning('Dashboard menu not found. Please install Dashboard module.')
        except Exception as e:
            logger.error(f'Error assigning default menu: {str(e)}')
            
        return res

    def write(self, vals):
        res = super().write(vals)

        if 'show_menu_ids' in vals:
            self.env['ir.ui.menu'].clear_caches()
            
        return res