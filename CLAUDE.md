# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an Odoo 18 custom addons directory containing modules for document extraction and backend theming. The main module is **robotia_document_extractor**, which uses Google Gemini AI to extract structured data from Vietnamese regulatory forms (Form 01 Registration and Form 02 Report) related to controlled substances.

## Repository Structure

```
custom_addons/
├── robotia_document_extractor/     # Main document extraction module
│   ├── models/                     # Backend models
│   │   ├── document_extraction.py  # Main extraction model (Form 01 & 02)
│   │   ├── extraction_service.py   # AI extraction service (Gemini integration)
│   │   ├── substance_*.py          # Substance-related models (usage, aggregate)
│   │   ├── equipment_*.py          # Equipment models (product, ownership, type)
│   │   ├── collection_*.py         # Collection/recycling models
│   │   ├── quota_usage.py          # Quota usage tracking
│   │   └── res_*.py                # Extended res.partner, res.config.settings
│   ├── controllers/
│   │   └── extraction_controller.py # JSON-RPC endpoint for AI extraction
│   ├── views/                      # Backend XML views
│   │   ├── document_extraction_views.xml
│   │   ├── master_data_views.xml
│   │   └── menus.xml
│   ├── static/src/
│   │   ├── js/
│   │   │   ├── dashboard/          # Main & analytics dashboards
│   │   │   │   ├── dashboard.js    # Main upload & statistics dashboard
│   │   │   │   ├── substance_dashboard.js  # Substance analytics
│   │   │   │   ├── company_dashboard.js    # Company analytics
│   │   │   │   ├── equipment_dashboard.js  # Equipment analytics
│   │   │   │   └── recovery_dashboard.js   # Recovery analytics
│   │   │   ├── form_view/          # Custom split-view form with PDF preview
│   │   │   ├── section_one2many/   # Custom One2many widget with title rows
│   │   │   ├── fields/             # Custom field widgets (pdf_url_viewer)
│   │   │   └── utils/              # Chart utilities (Chart.js helpers)
│   │   ├── xml/                    # OWL templates for components
│   │   ├── scss/                   # Component styles
│   │   └── group_list_view/        # Custom grouped list view
│   ├── security/                   # Access control (ir.model.access.csv)
│   ├── data/                       # Master data & default prompts
│   └── i18n/                       # Vietnamese translations (vi_VN.po)
└── backend_theme/                  # Backend UI theme module
    ├── models/                     # Theme settings
    ├── static/src/
    │   ├── backend/                # Custom app menu/sidebar
    │   └── js/                     # Dynamic theme color injection
    └── i18n/                       # Translations
```

## Development Commands

### Start Odoo Server
```bash
# From project root directory
./odoo-bin -c odoo.conf
```

### Install/Update Custom Modules
```bash
# Install module
./odoo-bin -c odoo.conf -d <database_name> -i robotia_document_extractor

# Update module after changes
./odoo-bin -c odoo.conf -d <database_name> -u robotia_document_extractor

# Update all modules
./odoo-bin -c odoo.conf -d <database_name> -u all
```

### Run Tests
```bash
# Run tests for specific module
./odoo-bin -c odoo.conf -d <test_database> -i robotia_document_extractor --test-enable --stop-after-init

# Run tests for specific file/class
./odoo-bin -c odoo.conf -d <test_database> --test-tags /robotia_document_extractor
```

### Python Dependencies
The project uses a virtual environment at `env/` in the project root. Activate it before development:
```bash
source ../env/bin/activate
```

### Required Python Packages
- `google-genai` - Required for Gemini API integration (robotia_document_extractor)

## Architecture & Key Patterns

### Odoo 18 Specific Conventions

#### RPC Calls in JavaScript
**IMPORTANT**: Odoo 18 uses direct RPC imports:
```javascript
import { rpc } from "@web/core/network/rpc";

// Use like this:
await rpc("/document_extractor/extract", {
    pdf_data: base64Data,
    filename: file.name,
    document_type: docType
});
```
Do NOT use `userService("rpc")` - this is outdated pre-Odoo 18 syntax.

#### OWL Components (Odoo 18)
All frontend components use OWL (Odoo Web Library) framework:
```javascript
import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
```

### Document Extraction Workflow

1. **Upload** → User uploads PDF via dashboard (`dashboard.js` → `upload_area.js`)
2. **Extract** → Frontend calls `/document_extractor/extract` via RPC
3. **AI Processing** → `extraction_service.py` calls Gemini API with configurable prompts
4. **Attachment** → Controller creates public `ir.attachment` for PDF preview (res_id=0)
5. **Response** → Returns `ir.actions.act_window` with `default_*` context (NOT creating record)
6. **Form Preview** → Opens custom split-view form with PDF on left, editable fields on right
7. **Validation** → User reviews/edits extracted data in CREATE mode
8. **Save** → On save, record created with One2many commands, attachment linked to res_id

**Key Point**: The controller does NOT create records. It only extracts data and returns a form action with context. This allows user validation before committing to database.

### Key Technical Details

#### Extraction Service Architecture
- **Service Model**: `document.extraction.service` (AbstractModel in `extraction_service.py:21`)
- **Method**: `extract_pdf(pdf_binary, document_type, filename)` at `extraction_service.py:53`
- **API**: Google Gemini 2.0 Flash Exp with temporary file upload
- **Prompts**: Configurable via `ir.config_parameter` (stored in `data/default_prompts.xml`)
  - `robotia_document_extractor.extraction_prompt_form_01`
  - `robotia_document_extractor.extraction_prompt_form_02`
- **Output**: Structured JSON with Vietnamese text preservation
- **Error Handling**: Parses both raw JSON and markdown-wrapped JSON from Gemini

#### Custom Form View Implementation (`extraction_form_view.js`)
- **View Type**: Custom form view registered as `document_extraction_form`
- **Split View**: PDF iframe on left, editable form on right (resizable)
- **Custom Compiler**: `DocumentExtractionFormCompiler` extracts PDF container and moves it outside `o_form_sheet_bg`
- **Custom Controller**: `DocumentExtractionFormController` initializes Split.js for resizable panels
  - **Responsive**: Only enables split on desktop (>=992px), stacks vertically on mobile
  - **Split.js Config**: 55/45 split, 300/250px minimums, 10px gutter
- **Split.js**: Third-party library loaded via `loadJS()` from `/static/lib/split.js`

#### Custom Widget: Section One2many (`section_one2many/`)
- **Purpose**: Display One2many tables with title/section rows (non-editable header rows)
- **Widget Name**: `extraction_section_one2many` and `extraction_section_one2many_equipment_type`
- **Components**:
  - `ExtractionSectionOneToManyField`: Custom field widget
  - `ExtractionSectionListRenderer`: Custom renderer that styles title rows differently
  - `ExtractionTitleField`: Custom field for title row display
- **Usage**: One2many fields with mixed data and title rows (identified by `is_title` field)
- **Variants**: Different renderers for standard vs equipment type tables

#### Analytics Dashboard System
- **Main Dashboard**: Entry point with upload area, statistics cards, recent extractions
- **Specialized Dashboards**: Substance, Company, Equipment, Recovery analytics
- **Chart Integration**: Uses Chart.js via `loadBundle("web.chartjs_lib")`
- **Chart Utilities**: Centralized in `utils/chart_utils.js`
  - Standard color schemes, formatters (weight, CO2e, numbers)
  - Reusable chart options (line, bar, pie configurations)
- **Data Flow**: Backend models compute aggregates → RPC calls → Chart.js rendering
- **Navigation**: Action buttons on master data records trigger dashboard with context

#### Controller Pattern
**CRITICAL**: The extraction controller (`extraction_controller.py:11`) does NOT create records immediately. It:
1. Calls extraction service to get data
2. Creates **public** `ir.attachment` with `res_id=0` (allows preview before save)
3. Returns `ir.actions.act_window` with `context` containing `default_*` prefixed values
4. Opens form in CREATE mode - user validates before saving
5. On save, `document_extraction.py` model hooks attach the PDF to the actual record

#### One2many Relationships & Data Models
**Form 01 (Registration)** uses these One2many fields on `document.extraction`:
- **Substance Usage**: `substance_usage_production_ids`, `substance_usage_import_ids`, `substance_usage_export_ids` → `substance.usage` model
- **Equipment**: `equipment_product_ids` → `equipment.product`, `equipment_ownership_ids` → `equipment.ownership`
- **Collection/Recycling**: 6 fields for different categories → `collection.recycling` model
  - `collection_recycling_collection_ids`, `collection_recycling_reuse_ids`, etc.

**Form 02 (Report)** uses:
- **Quota Usage**: `quota_usage_ids` → `quota.usage` model
- **Equipment Reports**: `equipment_product_report_ids` → `equipment.product.report`, `equipment_ownership_report_ids` → `equipment.ownership.report`
- **Collection Reports**: `collection_recycling_report_ids` → `collection.recycling.report`

**Master Data Models** (referenced via Many2one):
- `controlled.substance` - Controlled substances with GWP values
- `equipment.type` - Equipment types
- `recycling.facility` - Recycling facilities
- `activity.field`, `collection.location`, `recycling.technology`, `hs.code`

**Population Pattern**: Use One2many commands `[(0, 0, values)]` in `default_*` context to populate tables during extraction.

## Custom Views & Components

### Custom View Types
The module implements several custom view types registered in `registry.category('views')`:

1. **`document_extraction_form`** (`extraction_form_view.js`):
   - Split-panel form view with PDF preview
   - Custom Compiler, Renderer, and Controller
   - Used in `document_extraction_views.xml` via `js_class="document_extraction_form"`

2. **`grouped_list`** (`group_list_view/`):
   - List view with custom grouping behavior
   - Custom ArchParser and Renderer
   - Used for displaying grouped data with special rendering

### Custom Field Widgets
Registered in `registry.category('fields')`:

1. **`extraction_section_one2many`** (`section_one2many/extraction_section_one2many_field.js`):
   - One2many widget with title row support
   - Uses custom list renderer for styling title rows
   - Variant: `extraction_section_one2many_equipment_type` for equipment tables

2. **`pdf_url_viewer`** (`fields/pdf_url_viewer.js`):
   - Displays PDF from URL in iframe
   - Handles both saved records and unsaved (public attachment)
   - Usage: `<field name="pdf_url" widget="pdf_url_viewer"/>`

### OWL Client Actions
Dashboard components registered in `registry.category('actions')`:

- **Main Dashboard**: `robotia_document_extractor.dashboard_action`
- **Analytics Dashboards**: `substance_dashboard_action`, `company_dashboard_action`, `equipment_dashboard_action`, `recovery_dashboard_action`

**Usage in XML**: Define actions with `tag="robotia_document_extractor.dashboard_action"` and pass context for filtering.

## Translation Files

For translation work in `.po` files, always use the **@agent-odoo-po-translator** skill. This agent is specifically designed for Odoo multilanguage support and handling untranslated strings.

## Important Architectural Patterns

### PDF Attachment Workflow
**Problem**: Need to preview PDF before saving record (record doesn't exist yet, no `res_id`).

**Solution** (`extraction_controller.py:71-80`):
1. Create `ir.attachment` with `res_id=0` and `public=True`
2. This generates a public URL accessible without authentication
3. Pass attachment ID via `default_pdf_attachment_id` in context
4. On record save, `document_extraction.py` model updates attachment's `res_id`

### Dynamic Form Context Population
**Pattern**: Use `default_*` prefixed context keys to populate form fields in CREATE mode.

**For One2many fields**:
```python
context = {
    'default_document_type': '01',
    'default_year': 2024,
    'default_substance_usage_production_ids': [
        (0, 0, {'substance_id': 1, 'quantity': 100.5}),
        (0, 0, {'substance_id': 2, 'quantity': 200.0}),
    ]
}
```

**For Many2one fields**: Use ID directly
```python
'default_organization_id': partner_id
```

### Custom View Component Architecture
**Pattern**: Extend standard Odoo views by creating custom Compiler/Renderer/Controller classes.

**Example**: `DocumentExtractionFormView`
1. **Compiler**: Modifies XML structure before rendering (moves PDF container)
2. **Renderer**: Renders the modified structure
3. **Controller**: Adds behavior (Split.js initialization, event handlers)

**Registration**:
```javascript
registry.category('views').add('custom_view_name', {
    ...formView,  // Extend base view
    Controller: CustomController,
    Compiler: CustomCompiler,
    Renderer: CustomRenderer
});
```

**Usage in XML**:
```xml
<field name="name" js_class="custom_view_name"/>
```

### Master Data with Analytics
**Pattern**: Master data records (like `controlled.substance`) have action buttons to open analytics dashboards.

**Implementation**:
1. Add button to form/list view: `<button name="action_view_dashboard" type="object"/>`
2. Define Python method in model:
```python
def action_view_dashboard(self):
    return {
        'type': 'ir.actions.client',
        'tag': 'substance_dashboard_action',
        'params': {'substance_id': self.id, 'substance_name': self.name}
    }
```
3. Dashboard reads `substance_id` from `props.action.params`

### Chart.js Integration Pattern
**Pattern**: Centralize chart configuration and utilities for consistency.

**Implementation**:
1. Define reusable utilities in `utils/chart_utils.js`:
   - Color schemes (`CHART_COLORS`, `CHART_COLOR_ARRAY`)
   - Default options (`LINE_CHART_OPTIONS`, `BAR_CHART_OPTIONS`)
   - Formatters (`formatNumber`, `formatWeight`, `formatCO2e`)
2. Load Chart.js bundle: `await loadBundle("web.chartjs_lib")`
3. Import utilities: `import { CHART_COLORS, formatNumber } from "../utils/chart_utils"`
4. Store chart instances for cleanup: `this.lineChart = new Chart(...)`
5. Clean up on destroy: `willUnmount() { if (this.lineChart) this.lineChart.destroy(); }`

### Responsive Split View Pattern
**Problem**: Split.js doesn't handle responsive layouts automatically.

**Solution** (`extraction_form_view.js:83-120`):
1. Use `window.matchMedia('(min-width: 992px)')` to detect screen size
2. Initialize Split.js only on desktop
3. Destroy on mobile (resets inline styles, allows CSS stacking)
4. Listen to window resize events
5. Clean up listeners in useEffect cleanup function

## Code Conventions

### Python (Backend)
- Follow PEP 8 style guide
- Use `_logger = logging.getLogger(__name__)` for logging
- Model naming: Use dots (e.g., `document.extraction`, `document.extraction.service`)
- Always include docstrings for public methods

### JavaScript (Frontend)
- Use ES6+ syntax (import/export, arrow functions, async/await)
- Component naming: PascalCase for classes (e.g., `UploadArea`, `Dashboard`)
- File naming: snake_case for files (e.g., `upload_area.js`, `dashboard.js`)
- Template naming: `modulename.ComponentName` (e.g., `robotia_document_extractor.Dashboard`)

### XML (Views)
- Use meaningful `id` attributes: `view_document_extraction_form`, `menu_document_extraction`
- Group related fields in `<group>` tags
- Use `<notebook>` and `<page>` for tabbed interfaces

## Security & Access Control

Access rights are defined in `security/ir.model.access.csv`:
- Format: `id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink`
- Each model needs explicit access rules for user groups

## Configuration

### Gemini API Key Configuration
Users must configure API key in: Settings > Document Extractor > Configuration
- Stored in: `ir.config_parameter` with key `robotia_document_extractor.gemini_api_key`
- Retrieved in code: `self.env['ir.config_parameter'].sudo().get_param('robotia_document_extractor.gemini_api_key')`

### Theme Configuration
Backend theme colors configurable in: Settings > Backend Theme
- Dynamic CSS variables injected via JavaScript (`theme_colors.js`)

## Assets Management

Assets are registered in `__manifest__.py` under `assets` key:
```python
'assets': {
    'web.assets_backend': [
        # Utilities (must load first)
        'robotia_document_extractor/static/src/js/utils/chart_utils.js',

        # Individual dashboard components
        'robotia_document_extractor/static/src/js/dashboard/substance_dashboard.js',
        # ... other dashboards ...

        # Wildcard for all other files (loads remaining components)
        'robotia_document_extractor/static/src/**/*'
    ],
}
```

**Order matters**:
- Utility files must load before components that depend on them
- Use explicit paths for files with dependencies
- Use wildcard `**/*` for remaining files
- Templates (XML) should be available when JS components reference them

## Common Pitfalls

1. **RPC Syntax**: Don't use old `userService("rpc")` - use `import { rpc } from "@web/core/network/rpc"`
2. **One2many Commands**: Use `[(0, 0, values)]` for create, not direct list assignment
3. **Context Defaults**: Must prefix with `default_` (e.g., `default_year`, not `year`)
4. **File Upload**: Gemini requires file upload for PDFs - use temporary file approach in extraction service
5. **JSON Parsing**: Gemini may wrap JSON in markdown code blocks (```json...```) - extraction service handles both
6. **Vietnamese Numbers**: Handle both comma and dot as decimal separators in extraction
7. **PDF Attachment**: When creating attachment for preview, use `res_id=0` and `public=True` - this allows viewing before record save
8. **Custom View Registration**: Register custom views in `registry.category('views')` with unique names
9. **Widget Registration**: Register field widgets in `registry.category('fields')` with kebab-case names
10. **Chart.js Bundle**: Load Chart.js via `loadBundle("web.chartjs_lib")`, not direct script import
11. **Split.js Responsive**: Always check screen size and destroy/recreate Split.js on resize events
12. **Title Rows in One2many**: Use `is_title` boolean field to identify non-editable section headers

## Debugging & Troubleshooting

### Backend Debugging
- **View Logs**: Watch Odoo logs during development
  ```bash
  tail -f /var/log/odoo/odoo-server.log
  ```
- **Python Debugger**: Use `import pdb; pdb.set_trace()` in Python code
- **Logging**: Use `_logger.info()`, `_logger.error()` for debug output
- **SQL Queries**: Enable SQL logging in `odoo.conf`: `log_level = debug_sql`

### Frontend Debugging
- **Browser Console**: All console.log/error output visible in browser DevTools
- **OWL DevTools**: Install OWL DevTools Chrome extension for component inspection
- **Network Tab**: Monitor RPC calls to controllers
- **Asset Reloading**: After JS/XML/SCSS changes, hard refresh (Ctrl+Shift+R) or clear browser cache
- **Registry Inspection**: In console: `odoo.__DEBUG__.services`, `odoo.registry`

### Common Issues

**Issue**: Changes not reflected after module update
- **Solution**: Hard refresh browser, clear Odoo assets cache, or restart server with `--dev=all`

**Issue**: "Model not found" or "Field does not exist"
- **Solution**: Check `ir.model.access.csv` for access rights, verify field definition in model

**Issue**: Custom widget not appearing
- **Solution**: Check widget registered in `registry.category('fields')`, verify asset loaded in manifest

**Issue**: RPC call failing with 404
- **Solution**: Verify route in controller, check authentication (`auth='user'` vs `auth='public'`)

**Issue**: One2many data not saving
- **Solution**: Verify using `[(0, 0, values)]` command format, check inverse field in related model

**Issue**: PDF not displaying in preview
- **Solution**: Check attachment created with `public=True`, verify `pdf_url` computed field returns valid URL

**Issue**: Chart not rendering
- **Solution**: Ensure `loadBundle("web.chartjs_lib")` called before chart creation, check canvas element exists

**Issue**: Split.js not working
- **Solution**: Verify `loadJS('/robotia_document_extractor/static/lib/split.js')` completes, check elements exist in DOM

### Performance Optimization
- **Lazy Loading**: Use `loadBundle()` and `loadJS()` for large libraries
- **Computed Fields**: Add `store=True` for frequently accessed computed fields
- **Indexes**: Add `index=True` to fields used in searches/filters
- **SQL Optimization**: Use `read()` with specific field lists instead of full record
- **Chart Cleanup**: Always destroy Chart.js instances in `willUnmount()` to prevent memory leaks

## Git Integration

This is a git submodule in the parent Odoo repository. The custom_addons directory has its own `.git` folder and `.gitignore`.

Current branch: 18.0
