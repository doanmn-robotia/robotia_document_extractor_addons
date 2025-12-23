# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class ThemeController(http.Controller):
    """
    Controller for theme configuration endpoints
    """

    @http.route('/backend_theme/get_colors', type='json', auth='user', methods=['POST'])
    def get_theme_colors(self):
        """
        Get theme color configuration for primary and secondary colors.

        This endpoint uses sudo() to allow all authenticated users to retrieve
        theme colors regardless of their access rights to ir.config_parameter.

        Returns:
            dict: Dictionary containing primary_color and secondary_color values
                Example: {
                    'primary_color': '#6366f1',
                    'secondary_color': '#f8fafc'
                }
        """
        try:
            # Use sudo() to allow all users to read theme configuration
            config_param = request.env['ir.config_parameter'].sudo()

            # Fetch both color configurations
            primary_color = config_param.get_param(
                'backend_theme.primary_color',
                default='#6366f1'  # Default: Indigo-500
            )
            secondary_color = config_param.get_param(
                'backend_theme.secondary_color',
                default='#f8fafc'  # Default: Slate-50
            )

            return {
                'primary_color': primary_color,
                'secondary_color': secondary_color
            }

        except Exception as e:
            # Return default colors if any error occurs
            return {
                'primary_color': '#6366f1',
                'secondary_color': '#f8fafc',
                'error': str(e)
            }
