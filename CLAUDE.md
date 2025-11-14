# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an Odoo 18 custom addons directory containing modules for document extraction and backend theming. The main module is **robotia_document_extractor**, which uses Google Gemini AI to extract structured data from Vietnamese regulatory forms (Form 01 Registration and Form 02 Report) related to controlled substances.

## Repository Structure

```
custom_addons/
├── robotia_document_extractor/     # Main document extraction module
│   ├── models/                     # Backend models (document_extraction.py, extraction_service.py, etc.)
│   ├── controllers/                # JSON-RPC controllers (extraction_controller.py)
│   ├── views/                      # XML views and menus
│   ├── static/src/
│   │   ├── js/
│   │   │   ├── dashboard/          # Dashboard OWL components
│   │   │   └── form_view/          # Custom form view with PDF preview
│   │   ├── xml/                    # OWL templates
│   │   └── scss/                   # Styles
│   ├── security/                   # Access rights (ir.model.access.csv)
│   ├── data/                       # Master data (controlled substances)
│   └── i18n/                       # Translations (vi_VN.po)
└── backend_theme/                  # Theme customization module
    ├── models/                     # Settings models
    ├── static/src/
    │   ├── backend/                # App menu customization
    │   └── js/                     # Theme color configuration
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

1. **Upload** → User uploads PDF via dashboard (`upload_area.js`)
2. **Extract** → Frontend calls `/document_extractor/extract` controller endpoint
3. **AI Processing** → `extraction_service.py` calls Gemini API with structured prompts
4. **Response** → Controller returns action to open form with extracted data in context
5. **Validation** → User reviews and edits data in custom form view with PDF preview
6. **Save** → Record created with all related tables (One2many relationships)

### Key Technical Details

#### Extraction Service Architecture
- **Service Model**: `document.extraction.service` (AbstractModel)
- **Method**: `extract_pdf(pdf_binary, document_type, filename)`
- **API**: Google Gemini 2.0 Flash Exp with file upload
- **Output**: Structured JSON with Vietnamese text preserved
- **Prompt Engineering**: Highly specific prompts for Form 01 and Form 02 extraction

#### Custom Form View Implementation
- **Split View**: PDF preview on left, editable form on right
- **Custom Compiler**: `DocumentExtractionFormCompiler` moves PDF container outside sheet
- **Custom Renderer**: `DocumentExtractionFormRenderer` initializes split.js for resizable panels
- **Split.js**: Third-party library for panel resizing (loaded dynamically)

#### Controller Pattern
**CRITICAL**: The extraction controller does NOT create records immediately. It returns an `ir.actions.act_window` action with `context` containing `default_*` values to populate the form in CREATE mode. This allows user validation before saving.

#### One2many Relationships
Form 01 has multiple related tables:
- `substance_usage_production_ids`, `substance_usage_import_ids`, `substance_usage_export_ids`
- `equipment_product_ids`, `equipment_ownership_ids`
- `collection_recycling_collection_ids`, `collection_recycling_reuse_ids`, etc.

Form 02 has:
- `quota_usage_ids`, `equipment_product_report_ids`
- `equipment_ownership_report_ids`, `collection_recycling_report_ids`

These are populated via One2many commands: `[(0, 0, values)]` in context.

## Translation Files

For translation work in `.po` files, always use the **@agent-odoo-po-translator** skill:
```
@agent-odoo-po-translator
```

This agent is specifically designed for Odoo multilanguage support and handling untranslated strings.

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
        'robotia_document_extractor/static/src/js/dashboard/dashboard.js',
        'robotia_document_extractor/static/src/xml/dashboard.xml',
        'robotia_document_extractor/static/src/scss/dashboard.scss',
    ],
}
```

Order matters: JS dependencies must be loaded before dependent files.

## Common Pitfalls

1. **RPC Syntax**: Don't use old `userService("rpc")` - use `import { rpc } from "@web/core/network/rpc"`
2. **One2many Commands**: Use `[(0, 0, values)]` for create, not direct list assignment
3. **Context Defaults**: Must prefix with `default_` (e.g., `default_year`, not `year`)
4. **File Upload**: Gemini requires file upload for PDFs - use temporary file approach
5. **JSON Parsing**: Gemini may wrap JSON in markdown code blocks - handle both formats
6. **Vietnamese Numbers**: Handle both comma and dot as decimal separators in extraction

## Git Integration

This is a git submodule in the parent Odoo repository. The custom_addons directory has its own `.git` folder and `.gitignore`.

Current branch: 18.0
