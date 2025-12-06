# -*- coding: utf-8 -*-

"""
Strategy prompts - Assemble prompts for different extraction strategies
"""

from . import meta_prompts, schema_prompts


def get_ai_native_prompt(form_type):
    """Full prompt for AI native strategy (PDF → JSON direct)
    
    Args:
        form_type (str): '01' or '02'
        
    Returns:
        str: Complete extraction prompt for AI native strategy
    """
    form_name = "Form 01 (Registration)" if form_type == '01' else "Form 02 (Report)"
    
    schema = (schema_prompts.get_form_01_schema() if form_type == '01' 
              else schema_prompts.get_form_02_schema())
    
    return f"""
# VIETNAMESE {form_name.upper()} EXTRACTION

You are a professional document auditor. Extract REAL DATA from {form_name}.

{meta_prompts.get_extraction_rules()}

{meta_prompts.get_data_validation()}

{meta_prompts.get_quality_handling()}

{schema}

BEGIN EXTRACTION NOW.
"""


def get_text_extract_prompt(form_type):
    """Prompt for text extraction strategy (PDF → Text)
    
    Args:
        form_type (str): '01' or '02'
        
    Returns:
        str: Text extraction prompt
    """
    form_name = "Form 01 (Registration)" if form_type == '01' else "Form 02 (Report)"
    
    return f"""
Read this Vietnamese {form_name} PDF and extract ALL text content.

INSTRUCTIONS:
1. Extract ALL text, preserving structure
2. Include section headers, table headers, all data rows
3. Preserve Vietnamese text exactly
4. For tables, use "Row N:" prefix
5. For sections, use "=== Section Name ==="
6. Extract ALL numbers (preserve commas, dots)
7. DO NOT summarize - extract EVERYTHING verbatim

OUTPUT FORMAT:
- Plain text
- Preserve document structure
- One line per table row
- Clear section separators

Example:
=== Organization Information ===
Name: [organization name]
License: [number]
...

=== Table 1.1: Substance Usage ===
HEADER: Substance | Year 1 (kg) | Year 2 (kg) | Year 3 (kg) | Avg (kg)
Row 1: R-22 | 100.5 | 120.0 | 110.5 | 110.33
Row 2: R-410A | 200.0 | 210.0 | 205.0 | 205.00
...

Extract ALL content from this document now.
"""


def get_text_to_json_prompt(form_type, extracted_text):
    """Prompt for text-to-JSON conversion (Text → JSON)
    
    Args:
        form_type (str): '01' or '02'
        extracted_text (str): Text extracted from PDF
        
    Returns:
        str: Text-to-JSON conversion prompt
    """
    schema = (schema_prompts.get_form_01_schema() if form_type == '01' 
              else schema_prompts.get_form_02_schema())
    
    return f"""
Convert extracted text to structured JSON.

EXTRACTED TEXT:
{extracted_text}

---

Now convert the above text into JSON following these specifications:

{meta_prompts.get_extraction_rules()}

{meta_prompts.get_data_validation()}

{schema}

IMPORTANT:
- Use the text provided above, NOT a PDF
- Follow JSON structure EXACTLY as specified
- Preserve all Vietnamese text from the extracted text
- Convert all numeric values correctly

Return ONLY valid JSON. No markdown, no explanations.
"""


def get_batch_extract_prompt(form_type, start, end, total, count):
    """Prompt for batch extraction strategy (Images → JSON array)
    
    Args:
        form_type (str): '01' or '02'
        start (int): Start page number
        end (int): End page number
        total (int): Total pages in document
        count (int): Number of pages in this batch
        
    Returns:
        str: Batch extraction prompt
    """
    schema = (schema_prompts.get_form_01_schema() if form_type == '01' 
              else schema_prompts.get_form_02_schema())
    
    return f"""
## BATCH EXTRACTION

Extract from PAGES {start}-{end} (of {total} total).
Return JSON ARRAY with {count} objects (one per page).

### Per-Page Rules
- Extract ONLY visible content on each page
- Not visible → null or []
- Preserve sequence numbers EXACTLY (critical for deduplication)

### Table Continuation Detection

Tables may span pages (no header on page 2+).

Continuation signals:
✓ Same column structure as previous page
✓ Sequence numbers incrementing (18, 19, 20...)
✓ No section title row at top
✓ Same field types (substance names, numbers)

New table signals:
✗ Different column count
✗ New table header visible
✗ Sequence resets to 1
✗ New section title

Action:
- IF continuation → Use SAME table array name
- IF continuation → Continue sequence numbers
- IF new table → Start fresh with sequence=1

### Row Continuation Across Pages (CRITICAL!)

Rows may be SPLIT across page breaks:

Detection:
✓ Last row on page is incomplete (missing fields)
✓ First row on next page has no substance name (empty first column)
✓ Continuation row has only partial data

How to handle:
1. Identify incomplete row at end of page
2. Identify continuation at start of next page
3. Merge into ONE row in the FIRST page's data
4. Do NOT create separate row for continuation part

Example:
Page 1 last row: HFC-134a | 2903.4 | 52000 | ... | Trung Quốc | 106263, 923811 | (incomplete)
Page 2 first row: (empty) | (empty) | (empty) | ... | (empty) | 979010, 106348, ... | (continuation)

Merge result in Page 1 data:
HFC-134a | 2903.4 | 52000 | ... | Trung Quốc | 106263, 923811, 979010, 106348, ... | (complete)

### Summary Rows - SKIP (CRITICAL!)

DO NOT extract rows with these markers:
✗ "Tổng cộng" (Total)
✗ "Tổng" (Sum)
✗ "Cộng" (Total)

These are aggregated summary rows, NOT data rows.
Skip them entirely.

### Context Memory

You are processing batches from same document.
- Remember table structure from previous batches
- If you saw Table 1.1 header in previous batch, continue extracting rows
- Maintain consistency across batches

### Output Format

[
  {{
    "page": 1,
    "year": 2024,
    "organization_name": "...",
    "substance_usage": [
      {{"sequence": 1, "is_title": true, ...}},
      {{"sequence": 2, "is_title": false, ...}}
    ],
    ...
  }},
  {{"page": 2, "substance_usage": [...], ...}},
  ...
]

{meta_prompts.get_extraction_rules()}

{meta_prompts.get_data_validation()}

{meta_prompts.get_quality_handling()}

{schema}

CRITICAL: Return array with EXACTLY {count} page objects!
Return ONLY valid JSON array. No markdown, no explanations.
"""


def get_batch_system_prompt(form_type):
    """System prompt for batch extraction chat session
    
    Args:
        form_type (str): '01' or '02'
        
    Returns:
        str: System prompt for chat initialization
    """
    form_name = "Form 01 (Registration)" if form_type == '01' else "Form 02 (Report)"
    
    return f"""
You are a STRUCTURED DATA EXTRACTOR for Vietnamese {form_name}.

YOUR JOB:
- Extract from multiple page images sent together
- Return array of page objects (one per page)
- Maintain context across batches (chat memory)

CRITICAL RULES:
1. I send N pages → Return N page objects: [page1_json, page2_json, ...]
2. Each page object follows the schema I provide
3. Not visible on page → null or []
4. Tables may span batches - remember context from previous batches!

SEQUENCE NUMBERS ARE CRITICAL:
- Preserve sequence numbers EXACTLY as shown in tables
- Used for deduplication when merging batches
- Never skip or renumber sequences

Remember context from previous batches!
"""
