# Title Selection Auto-Detection Guide

This guide explains how the title row selection auto-detection works and how to control default value behavior.

## Overview

The system automatically detects and assigns selection field values for title rows (records with `is_title=True`) based on text content matching.

## Matching Strategy

The matching happens in priority order:

1. **Template Exact Match** (100% confidence)
   - Case-insensitive exact match with predefined templates from view XML
   - Example: "Nhập khẩu thiết bị, sản phẩm có chứa hoặc sản xuất từ chất được kiểm soát" → `import`

2. **Fuzzy Prefix Match** (80-99% confidence)
   - Matches **first 4 words only** to avoid false positives
   - Example: "Nhập khẩu thiết bị, sản phẩm có chứa hoặc **sản xuất**..."
     - Matches "Nhập khẩu thiết bị sản" (4 words) → `import` ✅
     - Ignores "sản xuất" at end of sentence

3. **Fuzzy Full Text Match** (70-89% confidence)
   - Fallback: matches entire text if prefix match fails

4. **Default Value** (0% confidence) - *Optional*
   - Uses configured default value when no match found
   - Can be disabled with `use_default=False`

---

## Using Default Values

### Option 1: Always Use Defaults (Default Behavior)

**When to use:** Creating new records from AI extraction, bulk import

```python
# All auto_detect calls use defaults by default
detected_value = auto_detect_title_selection(
    'equipment.product',
    'Unknown text that doesnt match anything',
    current_value=None
    # use_default=True (implicit)
)
# Returns: 'production' (default value from config)
```

**Result:** Unmatched titles get default values automatically

---

### Option 2: No Defaults (Only Matched Values)

**When to use:** Fixing existing data without guessing, manual review required

```python
# Explicitly disable defaults
detected_value = auto_detect_title_selection(
    'equipment.product',
    'Unknown text that doesnt match anything',
    current_value='import',
    use_default=False  # ← Disable defaults
)
# Returns: 'import' (keeps current_value)
```

**Result:** Unmatched titles keep existing values (or None if empty)

---

## Practical Examples

### Example 1: Create with Auto-Defaults (UI Creation)

When user creates a title row in the UI:

```python
# In model create()
vals = {
    'is_title': True,
    'product_type': 'Sản xuất máy móc'  # Unclear text
}

detected = auto_detect_title_selection(
    'equipment.product',
    'Sản xuất máy móc',
    None,
    use_default=True  # Use default if no match
)
# Returns: 'production' (default)

vals['production_type'] = detected
# Record created with production_type = 'production'
```

---

### Example 2: Update Only Matched (Cron Job)

Batch update existing records without guessing:

```python
def update_titles_matched_only(self):
    for record in title_rows:
        text = record.product_type
        current = record.production_type

        matched, confidence, match_type = match_title_selection(
            text,
            templates,
            mappings,
            default_value='production',
            use_default=False  # ← Don't use defaults
        )

        if matched:  # Only update if we found a match
            record.production_type = matched
        else:
            # Skip - leave as-is for manual review
            pass
```

**Log Output:**
```
✓ Updated equipment.product #123: 'Nhập khẩu thiết bị...' → 'import' (fuzzy_prefix: 95%)
⊘ Skipped equipment.product #456: 'Unclear text' - No match found (current: 'production')
```

---

## Available Methods

### 1. `update_all_title_selections()` - Use Defaults

Updates all title rows, using defaults for unmatched titles.

```python
env['document.extraction'].update_all_title_selections()
```

**Behavior:**
- Matched titles: Update with detected value
- Unmatched titles: Update with default value
- Empty titles: Update with default value

---

### 2. `update_titles_matched_only()` - No Defaults

Updates only title rows with good matches (>= 70% confidence).

```python
env['document.extraction'].update_titles_matched_only()
```

**Behavior:**
- Matched titles: Update with detected value
- Unmatched titles: **Skip** (leave as-is)
- Empty titles: **Skip** (leave empty)

**Use case:** Fix obvious mistakes without guessing unclear cases

---

### 3. `update_equipment_table_titles()` - Table-Specific

Updates equipment tables (1.2 & 2.2) with full logic.

```python
env['document.extraction'].update_equipment_table_titles()
```

**Behavior:** Same as `update_all_title_selections()` but only for equipment tables

---

## Configuration

Templates and keywords are defined in `TITLE_KEYWORD_CONFIG`:

```python
TITLE_KEYWORD_CONFIG = {
    'equipment.product': {
        'templates': {
            'production': 'Sản xuất thiết bị, sản phẩm có chứa hoặc sản xuất từ chất được kiểm soát',
            'import': 'Nhập khẩu thiết bị, sản phẩm có chứa hoặc sản xuất từ chất được kiểm soát'
        },
        'mappings': {
            'production': ['sản xuất thiết bị', 'sản xuất sản phẩm', 'production equipment'],
            'import': ['nhập khẩu thiết bị', 'nhập khẩu sản phẩm', 'import equipment']
        },
        'default': 'production'  # ← Used when use_default=True
    }
}
```

---

## Troubleshooting

### Issue: Title gets wrong selection

**Cause:** Text matches keyword at end of sentence

**Solution:** System now uses **first 4 words** for matching to avoid this

**Example:**
```
Text: "Nhập khẩu thiết bị, sản phẩm có chứa hoặc sản xuất từ chất..."
OLD: Matches "sản xuất" → 'production' ❌
NEW: Matches "Nhập khẩu thiết bị sản" → 'import' ✅
```

---

### Issue: Don't want defaults for unclear titles

**Solution:** Use `use_default=False` or call `update_titles_matched_only()`

```python
# Option 1: In code
auto_detect_title_selection(model, text, current, use_default=False)

# Option 2: Use dedicated method
env['document.extraction'].update_titles_matched_only()
```

---

## Summary Table

| Method | Use Defaults | Update Empty | Update Matched | Update Unmatched |
|--------|--------------|--------------|----------------|------------------|
| `update_all_title_selections()` | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes (with default) |
| `update_titles_matched_only()` | ❌ No | ❌ Skip | ✅ Yes | ❌ Skip |
| `update_equipment_table_titles()` | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes (with default) |

---

## Best Practices

1. **For AI Extraction:** Use defaults (`use_default=True`) to ensure all titles have values
2. **For Data Cleanup:** Use matched-only (`use_default=False`) to avoid guessing
3. **For Manual Review:** Check CSV logs for low confidence matches (< 85%)
4. **For Testing:** Start with `update_titles_matched_only()` to see match quality

---

## See Also

- `CLAUDE.md` - Full project documentation
- `models/document_extraction.py` - Implementation details
- `data/cron_update_title_selections.xml` - Scheduled job configuration
