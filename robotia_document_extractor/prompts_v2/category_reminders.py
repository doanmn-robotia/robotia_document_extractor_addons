# -*- coding: utf-8 -*-

"""
Short reminders for each batch extraction.
References system context instead of repeating full rules.
"""


def get_category_reminder(category, form_type):
    """
    Get short reminder for category extraction.

    This references the system context (mega-context) instead of
    repeating all extraction rules.

    Args:
        category: Category name
        form_type: '01' or '02'

    Returns:
        str: Short reminder prompt
    """
    category_names = {
        'metadata': 'organization metadata and document information',
        'substance_usage': 'substance usage data (Table 1.1)',
        'equipment_product': 'equipment/product manufacturing data (Table 1.2)',
        'equipment_ownership': 'owned equipment inventory (Table 1.3)',
        'collection_recycling': 'collection/recycling data (Table 1.4)',
        'quota_usage': 'quota usage and customs data (Table 2.1)',
        'equipment_product_report': 'equipment/product report (Table 2.2)',
        'equipment_ownership_report': 'equipment ownership report (Table 2.3)',
        'collection_recycling_report': 'collection/recycling report (Table 2.4)',
    }

    friendly_name = category_names.get(category, category)

    return f"""# EXTRACT CATEGORY: {category.upper()}

Extract {friendly_name} from the provided OCR markdown.

**CRITICAL REMINDERS (from system context):**

✓ Apply ALL extraction rules from system context
✓ Use substance database for mapping (exact/fuzzy/HS code matching)
✓ Follow activity field detection priority (checkboxes > table data)
✓ Preserve Vietnamese text exactly
✓ Use null for unclear/missing values (NEVER guess)
✓ Skip summary rows ("Tổng cộng", "Tổng", "Cộng")
✓ Handle line wrap in table cells (concatenate before parsing)
✓ Return ONLY valid JSON (no markdown, no explanations)

**TASK:**
Extract data following the schema below.
"""
