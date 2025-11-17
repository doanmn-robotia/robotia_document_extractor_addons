# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'Robotia Document Extractor',
    'version': '1.4.0',
    'sequence': 10,
    'description': "",
    'depends': ['web'],
    'data': [
        'security/ir.model.access.csv',
        'data/master_data.xml',
        'data/substance_groups_data.xml',
        'data/default_prompts.xml',
        'views/document_extraction_views.xml',
        'views/master_data_views.xml',
        'views/res_config_settings_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': True,
    'assets': {
        'web.assets_backend': [
            # Utilities (must load first)
            'robotia_document_extractor/static/src/js/utils/chart_utils.js',

            # Dashboards (JS)
            'robotia_document_extractor/static/src/js/dashboard/substance_dashboard.js',
            'robotia_document_extractor/static/src/js/dashboard/company_dashboard.js',
            'robotia_document_extractor/static/src/js/dashboard/equipment_dashboard.js',
            'robotia_document_extractor/static/src/js/dashboard/recovery_dashboard.js',
            'robotia_document_extractor/static/src/js/dashboard/hfc_dashboard.js',

            # ChatBot
            'robotia_document_extractor/static/src/js/chatbot/chatbot.js',
            'robotia_document_extractor/static/src/xml/chatbot.xml',
            'robotia_document_extractor/static/src/scss/chatbot.scss',

            # Templates (XML)
            'robotia_document_extractor/static/src/xml/substance_dashboard.xml',
            'robotia_document_extractor/static/src/xml/company_dashboard.xml',
            'robotia_document_extractor/static/src/xml/equipment_dashboard.xml',
            'robotia_document_extractor/static/src/xml/recovery_dashboard.xml',
            'robotia_document_extractor/static/src/xml/hfc_dashboard.xml',

            # Styles (SCSS)
            'robotia_document_extractor/static/src/scss/substance_dashboard.scss',
            'robotia_document_extractor/static/src/scss/company_dashboard.scss',
            'robotia_document_extractor/static/src/scss/equipment_dashboard.scss',
            'robotia_document_extractor/static/src/scss/recovery_dashboard.scss',
            'robotia_document_extractor/static/src/scss/hfc_dashboard.scss',

            # Other existing files
            'robotia_document_extractor/static/src/**/*'
        ],
    },
    'external_dependencies': {
        'python': ['google-genai']
    },
    'license': 'LGPL-3',
}
