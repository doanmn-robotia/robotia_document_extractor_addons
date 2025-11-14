# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    """
    Backend Theme Settings

    Extends Odoo's configuration settings to allow customization of
    the backend theme colors including primary and secondary colors.
    """
    _inherit = 'res.config.settings'

    theme_primary_color = fields.Char(
        string='Primary Color',
        help='Main color used throughout the backend theme (buttons, headers, etc.)',
        config_parameter='backend_theme.primary_color',
        default='#6366f1'  # Indigo-500 (modern theme default)
    )

    theme_secondary_color = fields.Char(
        string='Secondary Color',
        help='Secondary color used for accents and highlights',
        config_parameter='backend_theme.secondary_color',
        default='#f8fafc'  # Slate-50 (modern theme default)
    )

    @api.model
    def get_values(self):
        """
        Retrieve current theme color values from system parameters.

        Returns:
            dict: Dictionary containing theme color settings
        """
        res = super(ResConfigSettings, self).get_values()
        params = self.env['ir.config_parameter'].sudo()

        res.update(
            theme_primary_color=params.get_param('backend_theme.primary_color', '#6366f1'),
            theme_secondary_color=params.get_param('backend_theme.secondary_color', '#f8fafc'),
        )
        return res

    def set_values(self):
        """
        Save theme color values to system parameters.

        This method persists the color settings so they are available
        across sessions and for all users.
        """
        super(ResConfigSettings, self).set_values()
        params = self.env['ir.config_parameter'].sudo()

        params.set_param('backend_theme.primary_color', self.theme_primary_color or '#6366f1')
        params.set_param('backend_theme.secondary_color', self.theme_secondary_color or '#f8fafc')

    def action_reset_theme_colors(self):
        """
        Reset theme colors to default values.

        This action restores the modern theme default colors:
        - Primary Color: #6366f1 (indigo)
        - Secondary Color: #f8fafc (slate)

        Returns:
            dict: Action to reload the settings form
        """
        params = self.env['ir.config_parameter'].sudo()

        # Reset to modern theme default colors
        params.set_param('backend_theme.primary_color', '#6366f1')
        params.set_param('backend_theme.secondary_color', '#f8fafc')

        # Update current form values
        self.theme_primary_color = '#6366f1'
        self.theme_secondary_color = '#f8fafc'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Theme Colors Reset',
                'message': 'Theme colors have been reset to default values. Please refresh your browser to see the changes.',
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_url', 'target': 'self', 'url': '/odoo/settings'},
            }
        }
