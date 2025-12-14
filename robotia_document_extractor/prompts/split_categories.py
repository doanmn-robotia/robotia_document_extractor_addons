# -*- coding: utf-8 -*-

def get_categories(document_type):
    """Category definitions for LlamaCloud Split API"""

    if document_type == '01':
        return [
            {
                "name": "metadata",
                "description": "Organization info, license, contact, activity fields"
            },
            {
                "name": "table_1_1",
                "description": "Table 1.1: Substance production/import/export"
            },
            {
                "name": "table_1_2",
                "description": "Table 1.2: Equipment products"
            },
            {
                "name": "table_1_3",
                "description": "Table 1.3: Equipment ownership"
            },
            {
                "name": "table_1_4",
                "description": "Table 1.4: Collection and recycling"
            }
        ]

    else:  # '02'
        return [
            {
                "name": "metadata",
                "description": "Organization info, license, contact, activity fields"
            },
            {
                "name": "table_2_1",
                "description": "Table 2.1: Quota usage"
            },
            {
                "name": "table_2_2",
                "description": "Table 2.2: Equipment manufacturing report"
            },
            {
                "name": "table_2_3",
                "description": "Table 2.3: Equipment ownership report"
            },
            {
                "name": "table_2_4",
                "description": "Table 2.4: Collection/recycling report"
            }
        ]
