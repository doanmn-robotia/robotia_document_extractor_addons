# -*- coding: utf-8 -*-
{
    "name": "Backend theme",
    "summary": "Customizable backend theme with dynamic color configuration",
    "author": "Robotia",
    "category": "Management",
    "version": "0.1",
    "depends": ['web'],
    "data": [
        'security/ir.model.access.csv',
        'views/res_config_settings_views.xml',
    ],
    "demo": [
    ],
    "assets": {
        "web.assets_backend": [
            "backend_theme/static/src/backend/**/*",
            "backend_theme/static/src/js/theme_colors.js",
        ],
        'web.assets_frontend': [
        ],
    },
    'external_dependencies': {
        'python': [],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}