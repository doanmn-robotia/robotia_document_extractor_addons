# -*- coding: utf-8 -*-
{
    'name': "Restrict Menu",

    'summary': "Restrict created user to see only specific menu",

    'author': "Robotia",
    
    'category': 'Uncategorized',
    'version': '0.1',

    'depends': ['base'],
    'post_init_hook': 'installed_hook',
    'uninstall_hook': 'uninstall_hook',
    # always loaded
    'data': [
        'security/security.xml',
        'views/res_users_views.xml'
    ]
}

