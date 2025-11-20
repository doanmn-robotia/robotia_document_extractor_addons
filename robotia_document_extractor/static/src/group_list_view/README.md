# Grouped List View - Auto-Applied Patches

## Overview

This module **automatically patches Odoo's default list view and X2Many fields** to support grouped column headers with colspan. No need to specify custom widgets - the functionality is applied globally to all list views and One2many/Many2many fields.

## What Changed

### Before (v1.0 - Custom Widget Approach)
```xml
<!-- Had to explicitly use custom widget -->
<field name="revenue_ids" widget="grouped_one2many">
  <list>
    <field name="q1" context="{'group_start': True, 'group_header': 'Q1'}"/>
    <field name="q2"/>
    <field name="q3" context="{'group_end': True}"/>
  </list>
</field>
```

### After (v2.0 - Auto-Applied Patches)
```xml
<!-- No widget needed! Works automatically -->
<field name="revenue_ids">
  <list>
    <field name="q1" context="{'group_start': True, 'group_header': 'Q1'}"/>
    <field name="q2"/>
    <field name="q3" context="{'group_end': True}"/>
  </list>
</field>
```

## How It Works

The module patches three core Odoo components:

1. **ListArchParser** → `GroupedListArchParser`
   - Parses `context` attributes to detect grouping configuration
   - Extracts `group_start`, `group_end`, `group_header`, `group_label_field`, `group_class`

2. **ListRenderer** → `GroupedListRenderer`
   - Detects if any columns have grouping info
   - Renders two-level headers when groups are present
   - Falls back to standard single-level headers when no groups detected

3. **X2ManyField** → `PatchedX2ManyField`
   - All One2many and Many2many fields use `GroupedListRenderer`
   - Automatically supports grouped headers without widget specification

## Files Modified

```
group_list_view/
├── group_list_arch_parser.js     # Parse group context attributes
├── group_list_renderer.js        # Render two-level headers
├── group_list_renderer.xml       # OWL templates for grouped headers
├── group_list_controller.js      # PATCH default "list" view
├── grouped_x2many_field.js       # PATCH "one2many" & "many2many" fields
└── README.md                     # This file
```

## Patching Strategy

Uses `registry.category().add()` with `{ force: true }` to override defaults:

```javascript
// Patch list view
registry.category("views").add("list", patchedListView, { force: true });

// Patch X2Many fields
registry.category("fields").add("one2many", patchedX2ManyField, { force: true });
registry.category("fields").add("many2many", patchedX2ManyField, { force: true });
```

## Usage Examples

### Example 1: Static Group Labels

```xml
<field name="measurements">
  <list editable="bottom">
    <field name="product"/>
    <field name="q1_value" context="{'group_start': True, 'group_header': 'Q1 2024'}"/>
    <field name="q1_target" context="{'group_end': True}"/>
    <field name="q2_value" context="{'group_start': True, 'group_header': 'Q2 2024'}"/>
    <field name="q2_target" context="{'group_end': True}"/>
  </list>
</field>
```

**Renders:**
```
┌──────────┬─────────────────┬─────────────────┐
│ Product  │    Q1 2024      │    Q2 2024      │
├──────────┼────────┬────────┼────────┬────────┤
│          │ Value  │ Target │ Value  │ Target │
├──────────┼────────┼────────┼────────┼────────┤
│ Widget A │ 100    │ 120    │ 150    │ 140    │
└──────────┴────────┴────────┴────────┴────────┘
```

### Example 2: Dynamic Group Labels (from field definitions)

```xml
<field name="category" invisible="1"/>  <!-- Hidden field for label -->
<field name="value_1" context="{'group_start': True,
                                 'group_label_field': 'category'}"/>
<field name="value_2" context="{'group_end': True}"/>
```

The group header will display the `string` attribute from the `category` field definition.

### Example 3: Custom CSS Classes

```xml
<field name="planned" context="{'group_start': True,
                                 'group_header': 'Planned',
                                 'group_class': 'bg-info-subtle'}"/>
<field name="planned_q2" context="{'group_end': True}"/>
<field name="actual" context="{'group_start': True,
                                'group_header': 'Actual',
                                'group_class': 'bg-success-subtle'}"/>
<field name="actual_q2" context="{'group_end': True}"/>
```

### Example 4: Mixed Grouped and Ungrouped Columns

```xml
<list>
  <field name="name"/>  <!-- Ungrouped, rowspan=2 -->
  <field name="status"/>  <!-- Ungrouped, rowspan=2 -->
  <field name="jan" context="{'group_start': True, 'group_header': '2024'}"/>
  <field name="feb"/>
  <field name="mar" context="{'group_end': True}"/>
</list>
```

**Renders:**
```
┌──────────┬────────┬────────────────────┐
│   Name   │ Status │       2024         │
│          │        ├──────┬──────┬──────┤
│          │        │ Jan  │ Feb  │ Mar  │
├──────────┼────────┼──────┼──────┼──────┤
│ Product  │ Active │ 100  │ 150  │ 200  │
└──────────┴────────┴──────┴──────┴──────┘
```

## Context Attributes Reference

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `group_start` | Boolean | Yes | Marks first column in group |
| `group_end` | Boolean | Yes | Marks last column in group |
| `group_header` | String | No* | Static label for group header |
| `group_label_field` | String | No* | Field name to get label from (dynamic) |
| `group_class` | String | No | CSS class(es) to apply to group |

\* **Note**: Either `group_header` OR `group_label_field` must be provided for the first column in a group.

## Technical Details

### Header Rendering Logic

1. **Detection**: `hasGroupedHeaders` checks if any column has `groupStart = true`
2. **Row 1** (`headerColumns1`):
   - Ungrouped columns: single cell with `rowspan=2`
   - Grouped columns: single cell with `colspan=N` (calculated from `group_start` to `group_end`)
3. **Row 2** (`headerColumns2`):
   - Only grouped columns appear here
   - Individual field labels for each column

### Colspan Calculation

```javascript
let colspan = 2;  // Start with group_start column
for (let j = index + 1; j < columns.length; j++) {
    if (columns[j].groupEnd) {
        break;  // Found end of group
    }
    colspan += 1;
}
```

### CSS Class Propagation

When `group_class` is set on the `group_start` column:
- Applied to all columns in the group (`groupClass` property)
- Added to header cells (row 1 & row 2)
- Added to all data cells in those columns

### Template Inheritance

Uses **extension mode** to inherit from `web.ListRenderer`:
```xml
<t t-name="company_management.GroupedListRenderer"
   t-inherit="web.ListRenderer"
   t-inherit-mode="extension">
```

This extends the base template without replacing it entirely, allowing better compatibility with Odoo core updates.

### useMagicColumnWidths

Set to `false` in `GroupedListRenderer`:
```javascript
static useMagicColumnWidths = false
```

This prevents Odoo from auto-adjusting column widths, which would interfere with colspan calculations.

## Asset Loading Order

**CRITICAL**: The patches must load early in the asset pipeline:

```python
'web.assets_backend': [
    # Load patches FIRST (before other widgets that depend on list view)
    'robotia_document_extractor/static/src/group_list_view/group_list_arch_parser.js',
    'robotia_document_extractor/static/src/group_list_view/group_list_renderer.js',
    'robotia_document_extractor/static/src/group_list_view/group_list_renderer.xml',
    'robotia_document_extractor/static/src/group_list_view/group_list_controller.js',
    'robotia_document_extractor/static/src/group_list_view/grouped_x2many_field.js',

    # Other widgets can safely inherit the patched behavior
    'robotia_document_extractor/static/src/**/*'
]
```

## Backward Compatibility

### Old Widget Names (REMOVED)

The following custom widget registrations have been **removed**:
- ❌ `widget="grouped_list"` (view type)
- ❌ `widget="grouped_x2many"`
- ❌ `widget="grouped_one2many"`
- ❌ `widget="grouped_many2many"`

### Migration Path

**Before:**
```xml
<field name="my_field" widget="grouped_one2many">
```

**After:**
```xml
<field name="my_field">
```

Simply **remove the widget attribute** - the functionality is now automatic!

## Interaction with Other Widgets

### Compatible Widgets

These widgets work seamlessly with grouped headers:

- ✅ `x2many_numbered` - Row numbers + grouped headers
- ✅ `extraction_section_one2many` - Section rows + grouped headers
- ✅ Custom widgets that extend `X2ManyField`

### Example: Combining with x2many_numbered

```xml
<field name="revenue_ids" widget="x2many_numbered">
  <list editable="bottom">
    <field name="product"/>
    <field name="q1" context="{'group_start': True, 'group_header': 'Q1'}"/>
    <field name="q2" context="{'group_end': True}"/>
  </list>
</field>
```

This renders a table with:
- Automatic row numbers (#)
- Grouped headers (Q1 colspan)

## Debugging

### Check if Patches Applied

Open browser console:
```javascript
// Check if list view uses GroupedListRenderer
odoo.__DEBUG__.services.registry.category('views').get('list').Renderer.name
// Expected: "GroupedListRenderer"

// Check if one2many uses patched field
odoo.__DEBUG__.services.registry.category('fields').get('one2many').component.name
// Expected: "PatchedX2ManyField"
```

### Common Issues

**Issue**: Grouped headers not appearing
- **Check**: Verify `group_start` AND `group_end` are both present
- **Check**: Ensure at least one group has a label (`group_header` or `group_label_field`)

**Issue**: Columns not aligned correctly
- **Cause**: `useMagicColumnWidths` conflicts with colspan
- **Solution**: Already disabled in `GroupedListRenderer`

**Issue**: Patches not loading
- **Check**: Asset loading order in `__manifest__.py`
- **Fix**: Ensure group_list_view files load before other widgets

## Future Enhancements

Possible improvements:
- [ ] Support for 3+ level headers (nested groups)
- [ ] Visual group separators (vertical borders)
- [ ] Group-level totals/aggregations
- [ ] Collapsible column groups
- [ ] Auto-detect consecutive columns without explicit `group_end`

## Version History

- **v2.0** (Current): Auto-applied patches to default list view and X2Many
- **v1.0**: Custom widget approach (`widget="grouped_one2many"`)

## License

LGPL-3 (same as parent module)
