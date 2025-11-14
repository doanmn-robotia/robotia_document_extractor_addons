# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'Robotia Document Extractor',
    'version': '1.3',
    'sequence': 10,
    'description': "",
    'depends': ['web'],
    'data': [
        'security/ir.model.access.csv',
        'data/master_data.xml',
        'data/default_prompts.xml',
        'views/document_extraction_views.xml',
        'views/res_config_settings_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': True,
    'assets': {
        'web.assets_backend': [
            # Form view customization
            'robotia_document_extractor/static/src/**/*'
        ],
    },
    'external_dependencies': {
        'python': ['google-genai']
    },
    'license': 'LGPL-3',
}
