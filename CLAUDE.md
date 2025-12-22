# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an Odoo 18 custom addons directory for extracting structured data from Vietnamese regulatory forms using Google Gemini AI. The main module is **robotia_document_extractor**, which processes Form 01 (Registration) and Form 02 (Report) related to controlled substances.

### Business Domain Context

This system supports Vietnamese regulatory compliance for controlled substances (HFCs, refrigerants, ozone-depleting substances). The extracted forms are official government documents mandated by Vietnamese law and international treaties (Montreal Protocol):

- **Form 01 (Đăng ký)**: Annual registration of substance usage, equipment inventory, and recycling activities
- **Form 02 (Báo cáo)**: Quarterly reports on actual usage, quota consumption, and equipment status updates

**Key Business Concepts**:
- **Controlled Substances**: Regulated chemicals tracked by government agencies
- **GWP (Global Warming Potential)**: Multiplier for converting substance weight (kg) to CO2 equivalent impact
- **Activity Fields**: Business activity categories (production, import, export, distribution, service, etc.)
- **Quotas**: Government-allocated annual limits on substance import/production
- **Equipment Registration**: Tracking devices/systems containing controlled substances (capacity, location, ownership)

## Development Commands

### Start Odoo Server
```bash
# From project root directory (parent of custom_addons)
./odoo-bin -c odoo.conf

# With development mode (auto-reload on changes)
./odoo-bin -c odoo.conf --dev=all
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
- `google-genai` - Gemini API integration
- `google-api-python-client` - Google Drive API
- `PyMuPDF` - PDF processing
- `Pillow` - Image processing
- `llama-cloud-services` - LlamaParse OCR service

## Architecture & Business Logic

### End-to-End Extraction Workflow

1. **Upload** → User uploads PDF via dashboard (OWL component)
2. **Job Creation** → System creates `extraction.job` record and queues async processing
3. **OCR Processing** → LlamaParse service performs OCR, converts pages to images + structured markdown
4. **Category Mapping** → Identifies which tables correspond to which activity fields using keyword matching
5. **AI Extraction** → `extraction_service.py` builds mega-prompt with master data context and sends to Gemini
6. **Data Validation** → System validates metadata flags (merged columns/years) and infers activity codes
7. **Response** → Returns `ir.actions.act_window` with `default_*` context (NOT creating record yet)
8. **User Validation** → Opens split-view form with PDF preview on left, editable fields on right
9. **Save** → User reviews, edits, and saves to create `document.extraction` record

**Critical Pattern: Deferred Record Creation**

The extraction controller (`extraction_controller.py`) does NOT create database records immediately. This design allows user validation before committing data:

1. Controller extracts data via AI service
2. Creates **public** `ir.attachment` with `res_id=0` (enables preview without saved record)
3. Returns `ir.actions.act_window` with context containing `default_*` prefixed values
4. Form opens in CREATE mode - user validates/edits
5. On save, record is created and attachment is linked via `res_id` update

### Asynchronous Processing Architecture

#### Queue Job Integration
The system uses the `queue_job` module (Odoo Connector) for asynchronous PDF extraction:

**Configuration** (`odoo.conf`):
```ini
[queue_job]
channels = root:4,root.extraction:1

server_wide_modules = web,queue_job
```

**Queue Channels**:
- `root` (4 workers): General background jobs
- `root.extraction` (1 worker): Dedicated extraction processing to prevent resource contention

**Extraction Flow**:
1. User uploads PDF → Frontend creates `extraction.job` record
2. Job enqueued to `root.extraction` channel via `run_extraction_async()` method
3. Worker processes stages: OCR → Category Mapping → AI Extraction → Data Validation
4. Progress updates tracked in real-time (percentage-based via `_update_progress()`)
5. On completion: Returns form action for user validation
6. On failure: Job marked as failed with error details

**Retry Mechanism**:
Jobs can be retried from different stages (useful for transient failures):
- `action_retry_from_llama_ocr`: Restart from OCR step
- `action_retry_from_category_mapping`: Restart from table mapping step
- `action_retry_from_ai_processing`: Restart from AI extraction step

**Monitoring**: Settings > Technical > Queue Jobs

### Multi-Stage AI Extraction Pipeline

#### Stage 1: OCR Processing (`llama.ocr.service`)
- Uses LlamaParse Cloud Services for high-quality OCR
- Extracts structured markdown with table preservation
- Handles multi-page PDFs
- Converts pages to PNG images for preview

#### Stage 2: Category Mapping
- Identifies which extracted tables correspond to which activity fields
- Uses keyword matching against constants:
  - `SUBSTANCE_KEYWORDS` - Matches substance usage tables
  - `EQUIPMENT_KEYWORDS` - Matches equipment product tables
  - `OWNERSHIP_KEYWORDS` - Matches equipment ownership tables
  - `COLLECTION_KEYWORDS` - Matches collection/recycling tables
- Maps tables to correct One2many relationships via `TABLE_ACTIVITY_MAPPINGS`

#### Stage 3: AI Extraction (`extraction_service.py`)
Builds comprehensive prompt ("mega-prompt") containing:
- **Master data context**: Controlled substances list, equipment types, Vietnamese provinces, activity fields
- **OCR markdown**: Structured text from LlamaParse
- **Expected JSON schema**: Detailed structure for Gemini to follow
- **Instructions**: Vietnamese text preservation, number format handling, null value rules

Sends to **Google Gemini 2.0 Flash Exp** API and parses JSON response (handles markdown-wrapped JSON: ` ```json...``` `)

#### Stage 4: Data Cleaning & Validation
- Validates metadata flags (is_capacity_merged, is_years_merged) against actual table structure
- Infers activity field codes from table content using `_infer_activity_field_codes()`
- Cleans Vietnamese number formats (handles both comma and dot as decimal separator)
- Extracts year information from table headers via `_extract_years_from_tables()`
- Validates data row presence using `_has_valid_data_rows()`

### Configurable Prompts
Prompts are stored as `ir.config_parameter` values (editable in Settings):
- `robotia_document_extractor.extraction_prompt_form_01`
- `robotia_document_extractor.extraction_prompt_form_02`
- Default prompts defined in `data/default_prompts.xml`

## Data Models & Relationships

### Form 01 (Registration) Structure
Main model: `document.extraction`

**Substance Usage** (3 separate One2many fields):
- `substance_usage_production_ids` → `substance.usage` (production/formulation activity)
- `substance_usage_import_ids` → `substance.usage` (import activity)
- `substance_usage_export_ids` → `substance.usage` (export activity)

**Equipment**:
- `equipment_product_ids` → `equipment.product` (products/systems using substances)
- `equipment_ownership_ids` → `equipment.ownership` (owned equipment inventory)

**Collection/Recycling** (6 categories):
- `collection_recycling_collection_ids` → `collection.recycling`
- `collection_recycling_reuse_ids` → `collection.recycling`
- `collection_recycling_processing_ids` → `collection.recycling`
- `collection_recycling_destruction_ids` → `collection.recycling`
- `collection_recycling_storage_ids` → `collection.recycling`
- `collection_recycling_export_ids` → `collection.recycling`

### Form 02 (Report) Structure
Main model: `document.extraction` (same model, different fields)

**Quota Usage**:
- `quota_usage_ids` → `quota.usage` (tracks against allocated quotas)

**Equipment Reports**:
- `equipment_product_report_ids` → `equipment.product.report`
- `equipment_ownership_report_ids` → `equipment.ownership.report`

**Collection Reports**:
- `collection_recycling_report_ids` → `collection.recycling.report`

### Master Data Models
- `controlled.substance` - Substances with GWP values, substance groups, chemical formulas
- `equipment.type` - Equipment categories (air conditioner, refrigerator, fire suppression, etc.)
- `recycling.facility` - Registered recycling facilities
- `activity.field` - Activity categories for business operations
- `res.partner` - Organizations (extended with regulatory fields)
- `hs.code` - Harmonized System codes for customs
- `recycling.technology` - Methods of recycling/recovery

### Population Pattern for One2many Fields
Use One2many commands `[(0, 0, values)]` in `default_*` context:

```python
context = {
    'default_document_type': '01',
    'default_year': 2024,
    'default_substance_usage_production_ids': [
        (0, 0, {'substance_id': 1, 'quantity_kg': 100.5, 'activity_field_id': 2}),
        (0, 0, {'substance_id': 3, 'quantity_kg': 200.0, 'activity_field_id': 2}),
    ]
}
```

## Google Drive Auto-Extraction

### Automated Batch Processing
The system can automatically scan Google Drive folders and extract PDFs without manual upload:

**Components**:
- **Service**: `google.drive.service` - Handles Drive API authentication, file listing, downloads
- **Auto-Extractor**: `google.drive.auto.extractor` - Cron-based folder scanning
- **Logging**: `google.drive.extraction.log` - Tracks processed files, success/failure status

**Configuration**:
1. Navigate to: Settings > Document Extractor > Google Drive Configuration
2. Upload OAuth credentials JSON (from Google Cloud Console)
3. Authenticate and grant access
4. Configure folder mappings (which folders to scan, which document type)
5. Set cron schedule in `data/google_drive_cron.xml`

**Workflow**:
- Cron job runs periodically (`process_drive_files()`)
- Scans configured folders for new PDFs
- Downloads files and creates `extraction.job` records automatically
- Logs results in `google.drive.extraction.log`
- Marks/moves processed files to avoid re-processing

## AI Chatbot Assistant

### Conversational Interface
The system includes an AI-powered chatbot accessible via systray icon for answering questions about extraction data:

**Components**:
- **Service**: `chatbot.service` - Handles Gemini API conversation logic
- **Models**: `chatbot.conversation` (sessions), `chatbot.message` (individual messages)
- **Frontend**: Systray widget (`chatbot_systray.js`) + full-screen modal (`chatbot.js`)

**Features**:
- Answer questions about extraction data and regulatory requirements
- Provide guidance on form completion
- Query substance information, GWP values, equipment types
- Search across document records
- Access via systray icon (top-right corner of Odoo UI)

## Odoo 18 Specific Conventions

### RPC Calls in JavaScript
**IMPORTANT**: Odoo 18 uses direct RPC imports:
```javascript
import { rpc } from "@web/core/network/rpc";

// Correct usage:
await rpc("/document_extractor/extract", {
    pdf_data: base64Data,
    filename: file.name,
    document_type: docType
});
```
**Do NOT use** `userService("rpc")` - this is outdated pre-Odoo 18 syntax.

### OWL Components (Odoo 18)
All frontend components use OWL (Odoo Web Library) framework:
```javascript
import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
```

## Custom Views & Components

### Custom View Types
Registered in `registry.category('views')`:

1. **`document_extraction_form`** (`extraction_form_view.js`):
   - Split-panel form view with PDF preview on left, editable fields on right
   - Custom Compiler extracts PDF container and moves it outside `o_form_sheet_bg`
   - Custom Controller initializes Split.js for resizable panels
   - **Responsive**: Only enables split on desktop (>=992px), stacks vertically on mobile
   - **Split.js Config**: 55/45 split ratio, 300/250px minimums, 10px gutter
   - Usage in XML: `<field name="arch" js_class="document_extraction_form"/>`

2. **`grouped_list`** (`group_list_view/`):
   - List view with custom grouping behavior
   - Custom ArchParser and Renderer for grouped data display

### Custom Field Widgets
Registered in `registry.category('fields')`:

**Widget Selection Guide**:

1. **`extraction_section_one2many`**:
   - **Use for**: Tables with section headers/title rows
   - **Example**: Substance usage tables grouped by activity field
   - **Requirement**: Model must have `is_title` boolean field
   - **Features**: Non-editable title rows styled differently
   - **Variant**: `extraction_section_one2many_equipment_type` for equipment tables

2. **`extraction_grouped_one2many`**:
   - **Use for**: Tables with column grouping (merged headers) and row numbers
   - **Example**: Equipment tables with capacity columns (Design/Actual/Unit)
   - **Features**: Automatic row numbering, column spanning support, section headers

3. **`x2many_numbered`**:
   - **Use for**: Simple tables that just need row numbers
   - **Example**: Any One2many list where users need to reference specific rows
   - **Features**: Simplest option for numbered lists, no special configuration

4. **`pdf_url_viewer`**:
   - **Use for**: Displaying PDF attachments in forms
   - **Features**: Handles both saved records and public attachments (res_id=0)
   - **Usage**: `<field name="pdf_url" widget="pdf_url_viewer"/>`

5. **`ace_copy_field`**:
   - **Use for**: Displaying code/JSON/text with syntax highlighting
   - **Features**: Copy to clipboard button, download as file
   - **Example**: Raw OCR output, JSON responses, logs

6. **`raw_ocr_viewer`**:
   - **Use for**: Displaying OCR markdown with formatting
   - **Features**: Collapsible sections, syntax highlighting
   - **Example**: LlamaParse OCR output preview

### OWL Client Actions (Dashboards)
Registered in `registry.category('actions')`:

- **Main Dashboard**: `robotia_document_extractor.dashboard_action` (upload, statistics, recent extractions)
- **Analytics Dashboards**:
  - `substance_dashboard_action` - Substance usage analytics
  - `company_dashboard_action` - Organization-level analytics
  - `equipment_dashboard_action` - Equipment inventory analytics
  - `recovery_dashboard_action` - Collection/recycling analytics
  - `hfc_dashboard_action` - HFC-specific analytics
  - `overview_dashboard_action` - System-wide overview

**Usage in XML**:
```xml
<record id="action_substance_analytics" model="ir.actions.client">
    <field name="name">Substance Analytics</field>
    <field name="tag">substance_dashboard_action</field>
    <field name="params" eval="{}"/>
</record>
```

## Important Architectural Patterns

### PDF Attachment Workflow
**Problem**: Need to preview PDF before saving record (record doesn't exist yet, no `res_id`).

**Solution**:
1. Create `ir.attachment` with `res_id=0` and `public=True`
2. This generates a public URL accessible without authentication
3. Pass attachment ID via `default_pdf_attachment_id` in context
4. On record save, `document_extraction.py` model updates attachment's `res_id`

### Dynamic Form Context Population
**Pattern**: Use `default_*` prefixed context keys to populate form fields in CREATE mode.

**For Many2one fields**: Use ID directly
```python
'default_organization_id': partner_id
```

### Custom View Component Architecture
**Pattern**: Extend standard Odoo views by creating custom Compiler/Renderer/Controller classes.

**Registration**:
```javascript
registry.category('views').add('custom_view_name', {
    ...formView,  // Extend base view
    Controller: CustomController,
    Compiler: CustomCompiler,
    Renderer: CustomRenderer
});
```

### Master Data with Analytics
**Pattern**: Master data records have action buttons to open analytics dashboards with context.

**Implementation**:
```python
def action_view_dashboard(self):
    return {
        'type': 'ir.actions.client',
        'tag': 'substance_dashboard_action',
        'params': {'substance_id': self.id, 'substance_name': self.name}
    }
```
Dashboard reads `substance_id` from `props.action.params`

### Chart.js Integration Pattern
**Pattern**: Centralize chart configuration and utilities for consistency.

**Implementation**:
1. Define reusable utilities in `utils/chart_utils.js`:
   - Color schemes (`CHART_COLORS`, `CHART_COLOR_ARRAY`)
   - Default options (`LINE_CHART_OPTIONS`, `BAR_CHART_OPTIONS`, `PIE_CHART_OPTIONS`)
   - Formatters (`formatNumber`, `formatWeight`, `formatCO2e`)
2. Load Chart.js bundle: `await loadBundle("web.chartjs_lib")`
3. Import utilities: `import { CHART_COLORS, formatNumber } from "../utils/chart_utils"`
4. Store chart instances for cleanup: `this.lineChart = new Chart(...)`
5. **Critical**: Clean up on destroy: `willUnmount() { if (this.lineChart) this.lineChart.destroy(); }`

### Responsive Split View Pattern
**Problem**: Split.js doesn't handle responsive layouts automatically.

**Solution** (`extraction_form_view.js`):
1. Use `window.matchMedia('(min-width: 992px)')` to detect screen size
2. Initialize Split.js only on desktop
3. Destroy on mobile (resets inline styles, allows CSS stacking)
4. Listen to window resize events
5. Clean up listeners in useEffect cleanup function

## Code Conventions

### Python (Backend)
- **Style Guide**: PEP 8
- **Logging**: Use `_logger = logging.getLogger(__name__)` at module level
- **Model Naming**: Dot-separated (e.g., `document.extraction`, `controlled.substance`)
- **Docstrings**: Required for all public methods
- **Service Models**: Use `models.AbstractModel` for services/mixins (no database table)

### JavaScript (Frontend)
- **Syntax**: ES6+ (import/export, arrow functions, async/await, destructuring)
- **Framework**: OWL (Odoo Web Library) for all components
- **Component Naming**: PascalCase classes (e.g., `UploadArea`, `SubstanceDashboard`)
- **File Naming**: snake_case (e.g., `upload_area.js`, `substance_dashboard.js`)
- **Template Naming**: `modulename.ComponentName` (e.g., `robotia_document_extractor.Dashboard`)

### XML (Views)
- **ID Attributes**: Descriptive with prefix (e.g., `view_document_extraction_form`, `menu_document_extraction`)
- **Field Grouping**: Use `<group>` tags for related fields
- **Tabbed Interfaces**: Use `<notebook>` and `<page>` elements

## Assets Management

Assets are registered in `__manifest__.py` under `assets` key:
```python
'assets': {
    'web.assets_backend': [
        # Utilities (must load first)
        'robotia_document_extractor/static/src/js/utils/chart_utils.js',

        # Specific components with load order dependencies
        'robotia_document_extractor/static/src/js/dashboard/substance_dashboard.js',

        # Wildcard for remaining files
        'robotia_document_extractor/static/src/**/*'
    ],
}
```

**Order matters**:
- Utility files must load before components that depend on them
- Use explicit paths for files with dependencies
- Use wildcard `**/*` for remaining files
- Templates (XML) should be available when JS components reference them

## Translation Files

For translation work in `.po` files, always use the **@agent-odoo-po-translator** skill. This agent is specifically designed for Odoo multilanguage support and handling untranslated strings.

## Common Pitfalls

1. **RPC Syntax**: Don't use old `userService("rpc")` - use `import { rpc } from "@web/core/network/rpc"`
2. **One2many Commands**: Use `[(0, 0, values)]` for create, not direct list assignment
3. **Context Defaults**: Must prefix with `default_` (e.g., `default_year`, not `year`)
4. **File Upload**: Gemini requires file upload for PDFs - use temporary file approach in extraction service
5. **JSON Parsing**: Gemini may wrap JSON in markdown code blocks (` ```json...``` `) - extraction service handles both
6. **Vietnamese Numbers**: Handle both comma and dot as decimal separators in extraction
7. **PDF Attachment**: When creating attachment for preview, use `res_id=0` and `public=True`
8. **Custom View Registration**: Register custom views in `registry.category('views')` with unique names
9. **Widget Registration**: Register field widgets in `registry.category('fields')` with kebab-case names
10. **Chart.js Bundle**: Load Chart.js via `loadBundle("web.chartjs_lib")`, not direct script import
11. **Split.js Responsive**: Always check screen size and destroy/recreate Split.js on resize events
12. **Title Rows in One2many**: Use `is_title` boolean field to identify non-editable section headers

## Performance & Scaling

### Extraction Performance
- **Average extraction time**: 30-60 seconds per PDF (varies by page count and complexity)
- **Bottlenecks**: Gemini API response time, LlamaParse OCR processing
- **Optimization**: Queue jobs prevent UI blocking, dedicated extraction channel prevents resource contention

### Database Performance
- **Indexed fields**: `year`, `document_type`, `organization_id`, `status` fields have database indexes
- **Computed fields**: Many use `store=True` for performance (pre-computed and stored in DB)
- **Query optimization**: Use specific field lists in `read()` calls instead of reading full records

### Frontend Performance
- **Chart.js**: Always destroy instances in `willUnmount()` to prevent memory leaks
- **Asset loading**: Utilities load first via explicit paths, then other components via wildcard
- **Lazy loading**: Large libraries loaded via `loadBundle()` and `loadJS()` only when needed

## Debugging & Troubleshooting

### Backend Debugging
- **View Logs**: `tail -f /var/log/odoo/odoo-server.log`
- **Python Debugger**: Use `import pdb; pdb.set_trace()` in Python code
- **Logging**: Use `_logger.info()`, `_logger.error()` for debug output
- **SQL Queries**: Enable SQL logging in `odoo.conf`: `log_level = debug_sql`

### Frontend Debugging
- **Browser Console**: All console.log/error output visible in browser DevTools
- **OWL DevTools**: Install OWL DevTools Chrome extension for component inspection
- **Network Tab**: Monitor RPC calls to controllers
- **Asset Reloading**: After JS/XML/SCSS changes, hard refresh (Ctrl+Shift+R) or clear browser cache
- **Registry Inspection**: In console: `odoo.__DEBUG__.services`, `odoo.registry`

### Queue Job Debugging
- **View job details**: Settings > Technical > Queue Jobs
- **Check job state**: pending, started, done, failed
- **Retry failed jobs**: Use retry buttons on job form (can choose retry stage)
- **Job logs**: Check `queue_job` table for exception details and stack traces
- **Channel status**: Monitor worker allocation and queue depth
- **Manual enqueue**: Can manually enqueue jobs for testing

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

**Issue**: Queue job stuck in pending state
- **Solution**: Check queue_job workers are running, verify channel configuration in `odoo.conf`

**Issue**: Google Drive auto-extraction not working
- **Solution**: Check OAuth credentials, verify folder permissions, check cron job is active

## Security & Access Control

Access rights are defined in `security/ir.model.access.csv`:
- Format: `id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink`
- Each model needs explicit access rules for user groups
- Security groups defined in `data/security_groups.xml`
- Record rules defined in `security/ir_rules.xml` (row-level security)

## Configuration

### Gemini API Key Configuration
Users must configure API key in: Settings > Document Extractor > Configuration
- Stored in: `ir.config_parameter` with key `robotia_document_extractor.gemini_api_key`
- Retrieved in code: `self.env['ir.config_parameter'].sudo().get_param('robotia_document_extractor.gemini_api_key')`

### LlamaParse API Key Configuration
For OCR processing: Settings > Document Extractor > Configuration
- Stored in: `ir.config_parameter` with key `robotia_document_extractor.llama_api_key`

### Theme Configuration
Backend theme colors configurable in: Settings > Backend Theme
- Dynamic CSS variables injected via JavaScript (`theme_colors.js`)

## Git Integration

This is a git submodule in the parent Odoo repository. The custom_addons directory has its own `.git` folder and `.gitignore`.

Current branch: 18.0
