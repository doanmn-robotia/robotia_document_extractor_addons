# -*- coding: utf-8 -*-

"""
Optimized prompts v2 for token-efficient extraction.

Architecture:
- mega_context: Cached system instruction (sent once, reused)
- category_schemas: Minimal per-category JSON schemas
- category_reminders: Short prompts referencing system context
- llama_prompts: LlamaParse category-specific OCR prompts
- additional_prompts: Critical reminders for batch processing (year extraction, column accuracy)
"""

from . import mega_context
from . import category_schemas
from . import category_reminders
from . import llama_prompts
from . import additional_prompts

__all__ = [
    'mega_context',
    'category_schemas',
    'category_reminders',
    'llama_prompts',
    'additional_prompts',
]
