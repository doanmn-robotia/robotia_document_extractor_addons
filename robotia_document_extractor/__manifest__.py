# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'Robotia Document Extractor',
    'version': '18.0.1.0.1',
    'sequence': 10,
    'description': "",
    'depends': ['web', 'queue_job'],
    'category': "Document Extractor",
    'data': [
        'data/security_groups.xml',
        'security/ir.model.access.csv',
        'security/ir_rules.xml',
        'data/hs_code_data.xml',
        'data/master_data.xml',
        'data/substance_groups_data.xml',
        'data/default_prompts.xml',
        'data/google_drive_cron.xml',
        'data/extraction_job_sequence.xml',
        'data/queue_job_channel.xml',
        'wizard/google_drive_config_wizard_views.xml',
        'views/document_extraction_views.xml',
        'views/master_data_views.xml',
        'views/google_drive_extraction_log_views.xml',
        'views/extraction_job_views.xml',
        'views/queue_job_extraction_views.xml',
        'views/res_config_settings_views.xml',
        'views/res_config_settings_document_only.xml',
        'views/menus.xml',
        'views/client_actions.xml',
    ],
    'installable': True,
    'application': True,
    'assets': {
        'web.assets_backend': [
            # Utilities (must load first)
            'robotia_document_extractor/static/src/js/utils/chart_utils.js',

            # Page Selector (Client Action)
            'robotia_document_extractor/static/src/js/extraction_page_selector.js',
            'robotia_document_extractor/static/src/xml/extraction_page_selector.xml',
            'robotia_document_extractor/static/src/scss/extraction_page_selector_stepper.scss',

            # Widgets
            'robotia_document_extractor/static/src/js/validation_stats_widget.js',
            'robotia_document_extractor/static/src/xml/validation_stats_widget.xml',

            # OCR Preview Widget
            'robotia_document_extractor/static/src/js/raw_ocr_viewer/raw_ocr_viewer.js',
            'robotia_document_extractor/static/src/xml/raw_ocr_viewer.xml',
            'robotia_document_extractor/static/src/scss/raw_ocr_viewer.scss',

            # Dashboards (JS)
            'robotia_document_extractor/static/src/js/dashboard/substance_dashboard.js',
            'robotia_document_extractor/static/src/js/dashboard/company_dashboard.js',
            'robotia_document_extractor/static/src/js/dashboard/equipment_dashboard.js',
            'robotia_document_extractor/static/src/js/dashboard/recovery_dashboard.js',
            'robotia_document_extractor/static/src/js/dashboard/hfc_dashboard.js',
            'robotia_document_extractor/static/src/js/dashboard/overview_dashboard.js',

            # ChatBot
            'robotia_document_extractor/static/src/js/chatbot/chatbot.js',
            'robotia_document_extractor/static/src/xml/chatbot.xml',
            'robotia_document_extractor/static/src/scss/chatbot.scss',

            # ChatBot Systray
            'robotia_document_extractor/static/src/js/systray/chatbot_systray.js',
            'robotia_document_extractor/static/src/xml/chatbot_systray.xml',
            'robotia_document_extractor/static/src/scss/chatbot_systray.scss',

            # Templates (XML)
            'robotia_document_extractor/static/src/xml/substance_dashboard.xml',
            'robotia_document_extractor/static/src/xml/company_dashboard.xml',
            'robotia_document_extractor/static/src/xml/equipment_dashboard.xml',
            'robotia_document_extractor/static/src/xml/recovery_dashboard.xml',
            'robotia_document_extractor/static/src/xml/hfc_dashboard.xml',
            'robotia_document_extractor/static/src/xml/overview_dashboard.xml',

            # Styles (SCSS)
            'robotia_document_extractor/static/src/scss/substance_dashboard.scss',
            'robotia_document_extractor/static/src/scss/company_dashboard.scss',
            'robotia_document_extractor/static/src/scss/equipment_dashboard.scss',
            'robotia_document_extractor/static/src/scss/recovery_dashboard.scss',
            'robotia_document_extractor/static/src/scss/hfc_dashboard.scss',
            'robotia_document_extractor/static/src/scss/overview_dashboard.scss',

            # Field Replacement for X2ManyField (Global Patch - must load before other X2Many widgets)
            'robotia_document_extractor/static/src/js/field_replacement/field_replacement_list_renderer.js',
            'robotia_document_extractor/static/src/js/field_replacement/field_replacement_x2many.js',

            # X2Many Numbered Widget (with row numbers)
            'robotia_document_extractor/static/src/js/x2many_numbered/x2many_numbered_list_renderer.js',
            'robotia_document_extractor/static/src/js/x2many_numbered/x2many_numbered_field.js',
            'robotia_document_extractor/static/src/js/x2many_numbered/x2many_numbered_list_renderer.xml',
            'robotia_document_extractor/static/src/js/x2many_numbered/x2many_numbered.scss',

            # Grouped One2many Widget (section + row numbering + grouped columns)
            'robotia_document_extractor/static/src/js/grouped_one2many/extraction_grouped_list_renderer.js',
            'robotia_document_extractor/static/src/js/grouped_one2many/extraction_grouped_list_renderer.xml',
            'robotia_document_extractor/static/src/js/grouped_one2many/extraction_grouped_one2many_field.js',

            # Ace Copy Field Widget (ace editor with copy/download buttons)
            'robotia_document_extractor/static/src/js/fields/ace_copy_field.js',
            'robotia_document_extractor/static/src/xml/ace_copy_field.xml',
            'robotia_document_extractor/static/src/scss/ace_copy_field.scss',

            # Settings Dashboard (Main Component)
            'robotia_document_extractor/static/src/js/dashboard/settings_dashboard.js',

            # Settings Dashboard Tab Components (OCR and Permissions removed)
            'robotia_document_extractor/static/src/js/dashboard/settings/users_tab.js',
            'robotia_document_extractor/static/src/js/dashboard/settings/ai_tab.js',
            'robotia_document_extractor/static/src/js/dashboard/settings/backup_tab.js',
            'robotia_document_extractor/static/src/js/dashboard/settings/logs_tab.js',

            # Settings Dashboard Templates (OCR and Permissions removed)
            'robotia_document_extractor/static/src/xml/settings_dashboard.xml',
            'robotia_document_extractor/static/src/xml/settings/users_tab.xml',
            'robotia_document_extractor/static/src/xml/settings/ai_tab.xml',
            'robotia_document_extractor/static/src/xml/settings/backup_tab.xml',
            'robotia_document_extractor/static/src/xml/settings/logs_tab.xml',

            # Settings Dashboard Styles (OCR and Permissions removed)
            'robotia_document_extractor/static/src/scss/settings_dashboard.scss',
            'robotia_document_extractor/static/src/scss/settings/users_tab.scss',
            'robotia_document_extractor/static/src/scss/settings/ai_tab.scss',
            'robotia_document_extractor/static/src/scss/settings/backup_tab.scss',
            'robotia_document_extractor/static/src/scss/settings/logs_tab.scss',

            # Other existing files
            'robotia_document_extractor/static/src/**/*'
        ],
    },
    'external_dependencies': {
        'python': [
            'google-genai',
            'google-api-python-client',
            'PyMuPDF',
            'Pillow',
            'llama-cloud-services',
        ]
    },
    'license': 'LGPL-3',
}
