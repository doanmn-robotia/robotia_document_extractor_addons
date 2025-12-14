# -*- coding: utf-8 -*-

from odoo import models, api
import logging
import json

_logger = logging.getLogger(__name__)


class LlamaOCRService(models.AbstractModel):
    """
    LlamaIndex OCR Service for extracting structured data with bounding boxes
    
    Uses LlamaParse (LlamaCloud API) to extract text from PDFs with layout information
    and bounding box coordinates.
    """
    _name = 'document.llama.ocr.service'
    _description = 'LlamaIndex OCR Service'

    @api.model
    def extract_with_bbox(self, pdf_binary, document_type, filename):
        """
        Extract structured data from PDF using LlamaParse with bounding boxes
        
        Args:
            pdf_binary (bytes): PDF file content
            document_type (str): '01' for Registration, '02' for Report
            filename (str): Original filename for logging
            
        Returns:
            dict: Structured OCR data with format:
                {
                    "pages": [
                        {
                            "page_num": 0,
                            "page_width": 595.0,
                            "page_height": 842.0,
                            "text_regions": [
                                {
                                    "text": "extracted text",
                                    "bbox": {
                                        "x0": 100.0,
                                        "y0": 200.0,
                                        "x1": 300.0,
                                        "y1": 220.0
                                    },
                                    "confidence": 1.0
                                }
                            ]
                        }
                    ],
                    "extracted_fields": {
                        "field_name": {
                            "value": "field value",
                            "bbox": {...}
                        }
                    }
                }
                
        Raises:
            ValueError: If API key not configured or extraction fails
        """
        _logger.info(f"Starting LlamaIndex OCR extraction for {filename} (Type: {document_type})")
        
        # Get configuration
        ICP = self.env['ir.config_parameter'].sudo()
        api_key = ICP.get_param('robotia_document_extractor.llama_cloud_api_key')
        premium_mode_param = ICP.get_param('robotia_document_extractor.llama_premium_mode', 'False')
        # Ensure premium_mode_param is a string before calling .lower()
        premium_mode = str(premium_mode_param).lower() == 'true' if premium_mode_param else False
        
        if not api_key:
            raise ValueError(
                "LlamaCloud API key not configured. "
                "Please configure it in Settings > Document Extractor > Configuration"
            )
        
        _logger.info(f"LlamaIndex OCR Config - Premium Mode: {premium_mode}")
        
        try:
            # Import LlamaParse
            from llama_cloud_services import LlamaParse
            from llama_cloud_services.parse.utils import ResultType
            import tempfile
            import os
            
            # Get page dimensions first using PyMuPDF
            import fitz  # PyMuPDF
            doc_dimensions = []
            doc = fitz.open(stream=pdf_binary, filetype="pdf")
            for page in doc:
                rect = page.rect
                doc_dimensions.append((rect.width, rect.height))
            doc.close()
            
            _logger.info(f"PDF has {len(doc_dimensions)} pages")
            
            # Create temporary file for LlamaParse
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tf:
                tf.write(pdf_binary)
                temp_path = tf.name
            
            try:
                # Build parsing instruction based on document type
                parsing_instruction = self._build_parsing_instruction(document_type)
                # Build JSON schema for structured output
                json_schema_obj = self._build_json_schema(document_type)
                # Convert to JSON string (LlamaParse expects string, not dict)
                json_schema = json.dumps(json_schema_obj)
                
                # Initialize LlamaParse
                parser = LlamaParse(
                    api_key=api_key,
                    result_type=ResultType.STRUCTURED,  # Critical for getting layout/bbox data
                    language="vi",  # Vietnamese
                    system_prompt=parsing_instruction,
                    premium_mode=premium_mode,
                    verbose=True,
                    structured_output=True,
                    structured_output_json_schema=json_schema
                )
                
                _logger.info("Calling LlamaParse API...")
                
                # Execute parsing
                json_result = parser.get_json_result(temp_path)
                
                _logger.info(f"LlamaParse API call completed")
                
                # Step 1: Parse LlamaParse response structure
                pages = self._parse_llamaparse_response(json_result)
                
                # Step 2: Extract structured JSON data from items
                extracted_data = self._extract_structured_json_from_items(pages)
                
                # Step 3: Map raw OCR data for bbox information
                ocr_data = self._map_llama_to_internal_format(json_result, doc_dimensions)
                
                # Combine structured data with OCR bbox data
                result = {
                    'extracted_data': extracted_data,
                    'pages': ocr_data.get('pages', []),
                    'raw_response': json_result
                }
                
                _logger.info(f"OCR extraction completed - {len(extracted_data)} top-level fields")
                
                return result
                
            finally:
                # Cleanup temp file
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                    _logger.debug(f"Cleaned up temp file: {temp_path}")
                    
        except ImportError:
            raise ValueError(
                "llama-cloud-services not installed. "
                "Please install it: pip install llama-cloud-services"
            )
        except Exception as e:
            _logger.error(f"LlamaIndex OCR extraction failed: {str(e)}", exc_info=True)
            raise ValueError(f"OCR extraction failed: {str(e)}")

    def _build_parsing_instruction(self, document_type):
        """
        Build parsing instruction for LlamaParse based on document type
        
        This instruction guides LlamaParse on how to extract and structure the data.
        
        Args:
            document_type (str): '01' or '02'
            
        Returns:
            str: Parsing instruction prompt
        """
        # Import schema prompts for instructions
        from odoo.addons.robotia_document_extractor.prompts import schema_prompts
        
        if document_type == '01':
            return schema_prompts.get_form_01_schema()
        else:  # document_type == '02'
            return schema_prompts.get_form_02_schema()

    def _build_json_schema(self, document_type):
        """
        Build JSON Schema for LlamaParse structured output
        
        Converts the document type to proper JSON Schema format that LlamaParse
        can use for structured data extraction.
        
        Args:
            document_type (str): '01' or '02'
            
        Returns:
            dict: JSON Schema object
        """
        if document_type == '01':
            return self._get_form_01_json_schema()
        else:  # document_type == '02'
            return self._get_form_02_json_schema()

    def _get_form_01_json_schema(self):
        """
        Get JSON Schema for Form 01 (Registration)
        
        Returns:
            dict: JSON Schema for Form 01
        """
        return {
            "type": "object",
            "properties": {
                # Metadata Fields
                "year": {"type": "integer"},
                "year_1": {"type": "integer"},
                "year_2": {"type": "integer"},
                "year_3": {"type": "integer"},
                "organization_name": {"type": "string"},
                "business_license_number": {"type": "string"},
                "business_license_date": {"type": ["string", "null"]},
                "business_license_place": {"type": "string"},
                "legal_representative_name": {"type": "string"},
                "legal_representative_position": {"type": "string"},
                "contact_person_name": {"type": "string"},
                "contact_address": {"type": "string"},
                "contact_phone": {"type": "string"},
                "contact_fax": {"type": "string"},
                "contact_email": {"type": "string"},
                "contact_country_code": {"type": "string"},
                "contact_state_code": {"type": ["string", "null"]},
                "activity_field_codes": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                
                # Table Presence Flags
                "has_table_1_1": {"type": "boolean"},
                "has_table_1_2": {"type": "boolean"},
                "has_table_1_3": {"type": "boolean"},
                "has_table_1_4": {"type": "boolean"},
                "is_capacity_merged_table_1_2": {"type": "boolean"},
                "is_capacity_merged_table_1_3": {"type": "boolean"},
                
                # Table 1.1: substance_usage
                "substance_usage": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "is_title": {"type": "boolean"},
                            "sequence": {"type": "integer"},
                            "usage_type": {"type": "string"},
                            "substance_name": {"type": "string"},
                            "year_1_quantity_kg": {"type": ["number", "null"]},
                            "year_1_quantity_co2": {"type": ["number", "null"]},
                            "year_2_quantity_kg": {"type": ["number", "null"]},
                            "year_2_quantity_co2": {"type": ["number", "null"]},
                            "year_3_quantity_kg": {"type": ["number", "null"]},
                            "year_3_quantity_co2": {"type": ["number", "null"]},
                            "avg_quantity_kg": {"type": ["number", "null"]},
                            "avg_quantity_co2": {"type": ["number", "null"]}
                        }
                    }
                },
                
                # Table 1.2: equipment_product
                "equipment_product": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "is_title": {"type": "boolean"},
                            "sequence": {"type": "integer"},
                            "product_type": {"type": "string"},
                            "hs_code": {"type": "string"},
                            "capacity": {"type": ["string", "null"]},
                            "cooling_capacity": {"type": ["string", "null"]},
                            "power_capacity": {"type": ["string", "null"]},
                            "quantity": {"type": ["number", "null"]},
                            "substance_name": {"type": "string"},
                            "substance_quantity_per_unit": {"type": ["number", "null"]},
                            "notes": {"type": ["string", "null"]}
                        }
                    }
                },
                
                # Table 1.3: equipment_ownership
                "equipment_ownership": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "is_title": {"type": "boolean"},
                            "sequence": {"type": "integer"},
                            "equipment_type": {"type": "string"},
                            "start_year": {"type": ["integer", "null"]},
                            "capacity": {"type": ["string", "null"]},
                            "cooling_capacity": {"type": ["string", "null"]},
                            "power_capacity": {"type": ["string", "null"]},
                            "equipment_quantity": {"type": ["integer", "null"]},
                            "substance_name": {"type": "string"},
                            "refill_frequency": {"type": ["string", "null"]},
                            "substance_quantity_per_refill": {"type": ["string", "null"]}
                        }
                    }
                },
                
                # Table 1.4: collection_recycling
                "collection_recycling": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "is_title": {"type": "boolean"},
                            "sequence": {"type": "integer"},
                            "activity_type": {"type": "string"},
                            "substance_name": {"type": "string"},
                            "quantity_kg": {"type": ["number", "null"]},
                            "quantity_co2": {"type": ["number", "null"]}
                        }
                    }
                }
            },
            "required": ["year", "organization_name"]
        }

    def _get_form_02_json_schema(self):
        """
        Get JSON Schema for Form 02 (Report)
        
        Returns:
            dict: JSON Schema for Form 02
        """
        return {
            "type": "object",
            "properties": {
                # Metadata Fields
                "year": {"type": "integer"},
                "year_1": {"type": "integer"},
                "year_2": {"type": "integer"},
                "year_3": {"type": "integer"},
                "organization_name": {"type": "string"},
                "business_license_number": {"type": "string"},
                "business_license_date": {"type": ["string", "null"]},
                "business_license_place": {"type": "string"},
                "legal_representative_name": {"type": "string"},
                "legal_representative_position": {"type": "string"},
                "contact_person_name": {"type": "string"},
                "contact_address": {"type": "string"},
                "contact_phone": {"type": "string"},
                "contact_fax": {"type": "string"},
                "contact_email": {"type": "string"},
                "contact_country_code": {"type": "string"},
                "contact_state_code": {"type": ["string", "null"]},
                "activity_field_codes": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                
                # Table Presence Flags
                "has_table_2_1": {"type": "boolean"},
                "has_table_2_2": {"type": "boolean"},
                "has_table_2_3": {"type": "boolean"},
                "has_table_2_4": {"type": "boolean"},
                "is_capacity_merged_table_2_2": {"type": "boolean"},
                "is_capacity_merged_table_2_3": {"type": "boolean"},
                
                # Table 2.1: quota_usage
                "quota_usage": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "is_title": {"type": "boolean"},
                            "sequence": {"type": "integer"},
                            "usage_type": {"type": "string"},
                            "substance_name": {"type": "string"},
                            "hs_code": {"type": "string"},
                            "allocated_quota_kg": {"type": ["number", "null"]},
                            "allocated_quota_co2": {"type": ["number", "null"]},
                            "adjusted_quota_kg": {"type": ["number", "null"]},
                            "adjusted_quota_co2": {"type": ["number", "null"]},
                            "total_quota_kg": {"type": ["number", "null"]},
                            "total_quota_co2": {"type": ["number", "null"]},
                            "average_price": {"type": ["number", "null"]},
                            "country_text": {"type": "string"},
                            "customs_declaration_number": {"type": ["string", "null"]},
                            "next_year_quota_kg": {"type": ["number", "null"]},
                            "next_year_quota_co2": {"type": ["number", "null"]}
                        }
                    }
                },
                
                # Table 2.2: equipment_product_report
                "equipment_product_report": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "is_title": {"type": "boolean"},
                            "sequence": {"type": "integer"},
                            "production_type": {"type": "string"},
                            "product_type": {"type": "string"},
                            "hs_code": {"type": "string"},
                            "capacity": {"type": ["string", "null"]},
                            "cooling_capacity": {"type": ["string", "null"]},
                            "power_capacity": {"type": ["string", "null"]},
                            "quantity": {"type": ["number", "null"]},
                            "substance_name": {"type": "string"},
                            "substance_quantity_per_unit": {"type": ["number", "null"]},
                            "notes": {"type": ["string", "null"]}
                        }
                    }
                },
                
                # Table 2.3: equipment_ownership_report
                "equipment_ownership_report": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "is_title": {"type": "boolean"},
                            "sequence": {"type": "integer"},
                            "ownership_type": {"type": "string"},
                            "equipment_type": {"type": "string"},
                            "equipment_quantity": {"type": ["integer", "null"]},
                            "substance_name": {"type": "string"},
                            "capacity": {"type": ["string", "null"]},
                            "cooling_capacity": {"type": ["string", "null"]},
                            "power_capacity": {"type": ["string", "null"]},
                            "start_year": {"type": ["integer", "null"]},
                            "refill_frequency": {"type": ["string", "null"]},
                            "substance_quantity_per_refill": {"type": ["string", "null"]},
                            "notes": {"type": ["string", "null"]}
                        }
                    }
                },
                
                # Table 2.4: collection_recycling_report
                "collection_recycling_report": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "substance_name": {"type": "string"},
                            "collection_quantity_kg": {"type": ["number", "null"]},
                            "collection_location": {"type": ["string", "null"]},
                            "storage_location": {"type": ["string", "null"]},
                            "reuse_quantity_kg": {"type": ["number", "null"]},
                            "reuse_technology": {"type": ["string", "null"]},
                            "recycle_quantity_kg": {"type": ["number", "null"]},
                            "recycle_technology": {"type": ["string", "null"]},
                            "recycle_usage_location": {"type": ["string", "null"]},
                            "disposal_quantity_kg": {"type": ["number", "null"]},
                            "disposal_technology": {"type": ["string", "null"]},
                            "disposal_facility": {"type": ["string", "null"]}
                        }
                    }
                }
            },
            "required": ["year", "organization_name"]
        }

    def _parse_llamaparse_response(self, json_result):
        """
        Parse LlamaParse response structure to extract pages array
        
        LlamaParse response structure can vary:
        - Case 1: json_result[0][0]['pages']
        - Case 2: json_result[0]['pages']
        
        Args:
            json_result: Raw response from parser.get_json_result()
            
        Returns:
            list: Pages array containing items with md, text, and bbox
            
        Raises:
            ValueError: If response structure is invalid
        """
        try:
            if not isinstance(json_result, list) or len(json_result) == 0:
                raise ValueError("LlamaParse returned empty or invalid response")
            
            result_data = json_result[0]
            
            # Case 1: Nested structure - json_result[0][0]['pages']
            if isinstance(result_data, dict) and 0 in result_data:
                inner_data = result_data[0]
                if isinstance(inner_data, dict) and 'pages' in inner_data:
                    pages = inner_data['pages']
                    _logger.info(f"Successfully parsed {len(pages)} page(s) from nested structure")
                    return pages
            
            # Case 2: Direct structure - json_result[0]['pages']
            if isinstance(result_data, dict) and 'pages' in result_data:
                pages = result_data['pages']
                _logger.info(f"Successfully parsed {len(pages)} page(s) from direct structure")
                return pages
            
            # Neither structure worked - log details for debugging
            _logger.error(f"Unexpected response structure. Type: {type(result_data)}, Keys: {result_data.keys() if isinstance(result_data, dict) else 'N/A'}")
            raise ValueError(f"Missing 'pages' key in response. Available keys: {list(result_data.keys()) if isinstance(result_data, dict) else 'N/A'}")
            
        except Exception as e:
            _logger.error(f"Failed to parse LlamaParse response structure: {e}", exc_info=True)
            raise ValueError(f"Invalid LlamaParse response structure: {e}")

    def _extract_structured_json_from_items(self, pages):
        """
        Extract and merge structured JSON data from all pages
        
        Iterates through pages and items to extract structured JSON output,
        then merges data from all pages:
        - Scalar fields: Use first non-null value
        - Array fields: Append all rows from all pages
        
        Args:
            pages (list): Pages array from _parse_llamaparse_response()
            
        Returns:
            dict: Merged structured data from all pages
        """
        all_page_data = []
        
        for page_idx, page in enumerate(pages):
            items = page.get('items', [])
            
            for item_idx, item in enumerate(items):
                # Try to get structured JSON from 'md' or 'value' field
                md_content = item.get('md') or item.get('value')
                
                if not md_content:
                    continue
                
                # Try to parse as JSON
                try:
                    page_data = json.loads(md_content)
                    _logger.info(
                        f"Extracted structured JSON from page {page_idx}, "
                        f"item {item_idx} (type: {item.get('type', 'unknown')})"
                    )
                    all_page_data.append(page_data)
                    break  # Only take first valid JSON per page
                    
                except json.JSONDecodeError as e:
                    # Not a JSON string, skip this item
                    _logger.debug(f"Item md field is not JSON: {e}")
                    continue
        
        if not all_page_data:
            _logger.warning("No structured JSON found in any page items - returning empty dict")
            return {}
        
        # Merge all page data
        merged_data = self._merge_page_data(all_page_data)
        _logger.info(f"Merged data from {len(all_page_data)} page(s)")
        
        return merged_data

    def _merge_page_data(self, all_page_data):
        """
        Merge structured data from multiple pages
        
        Rules:
        - Scalar fields (str, int, float, bool): Use first non-null value
        - Array fields: Concatenate all arrays
        - Nested dicts: Recursively merge
        
        Args:
            all_page_data (list): List of dicts, one per page
            
        Returns:
            dict: Merged data
        """
        if not all_page_data:
            return {}
        
        # Start with first page as base
        merged = {}
        
        for page_data in all_page_data:
            if not isinstance(page_data, dict):
                continue
            
            for key, value in page_data.items():
                # If key doesn't exist in merged, add it
                if key not in merged:
                    merged[key] = value
                    continue
                
                # Key exists - need to merge intelligently
                existing = merged[key]
                
                # Case 1: Arrays - concatenate
                if isinstance(existing, list) and isinstance(value, list):
                    merged[key] = existing + value
                
                # Case 2: Scalars - use first non-null
                elif not isinstance(existing, (list, dict)):
                    # If existing is null/None, use new value
                    if existing is None and value is not None:
                        merged[key] = value
                    # Otherwise keep existing (first non-null wins)
                
                # Case 3: Dicts - recursively merge (rare case)
                elif isinstance(existing, dict) and isinstance(value, dict):
                    merged[key] = self._merge_page_data([existing, value])
        
        return merged

    def _map_llama_to_internal_format(self, llama_pages, doc_dimensions):
        """
        Map LlamaParse JSON output to internal OCR data format
        
        Args:
            llama_pages (list): Result from parser.get_json_result()
            doc_dimensions (list): List of (width, height) tuples for each page
            
        Returns:
            dict: Formatted OCR data with normalized coordinates converted to PDF points
        """
        processed_pages = []
        
        for i, page_data in enumerate(llama_pages):
            # Safety check for page count mismatch
            if i >= len(doc_dimensions):
                _logger.warning(f"Page {i} missing dimensions, skipping")
                break
            
            page_w, page_h = doc_dimensions[i]
            
            # Extract layout items from page data
            # LlamaParse structure can vary, check both possible locations
            layout_items = []
            
            if isinstance(page_data, dict):
                layout_items = page_data.get('layout', []) or page_data.get('items', [])
                # Also check for 'pages' nested structure
                if 'pages' in page_data and isinstance(page_data['pages'], list):
                    if len(page_data['pages']) > 0:
                        layout_items = page_data['pages'][0].get('layout', [])
            
            text_regions = []
            
            for item in layout_items:
                # Extract bbox information
                bbox = item.get('bbox', {})
                if not bbox or 'x' not in bbox:
                    continue
                
                # Map normalized coordinates to PDF points
                x0 = bbox['x'] * page_w
                y0 = bbox['y'] * page_h
                x1 = (bbox['x'] + bbox.get('w', 0)) * page_w
                y1 = (bbox['y'] + bbox.get('h', 0)) * page_h
                
                # Extract text content (can be in 'md', 'content', or 'text' field)
                text = item.get('md', '') or item.get('content', '') or item.get('text', '')
                
                text_regions.append({
                    'text': text,
                    'bbox': {
                        'x0': round(x0, 2),
                        'y0': round(y0, 2),
                        'x1': round(x1, 2),
                        'y1': round(y1, 2)
                    },
                    'confidence': 1.0,  # LlamaParse doesn't provide granular confidence
                    'type': item.get('type', 'text')  # text, table, heading, etc.
                })
            
            processed_pages.append({
                'page_num': i,
                'page_width': page_w,
                'page_height': page_h,
                'text_regions': text_regions
            })
            
            _logger.info(f"Page {i}: Mapped {len(text_regions)} text regions")
        
        return {'pages': processed_pages}

    def _extract_structured_fields(self, ocr_data, document_type):
        """
        Extract structured fields from OCR data
        
        Uses AI to parse the OCR text and extract specific fields with their bounding boxes.
        
        Args:
            ocr_data (dict): Raw OCR data with text regions and bboxes
            document_type (str): '01' or '02'
            
        Returns:
            dict: Extracted fields in format:
                {
                    "field_name": {
                        "value": "extracted value",
                        "bbox": {"x0": ..., "y0": ..., "x1": ..., "y1": ...},
                        "page": 0
                    }
                }
        """
        # Combine all text with their bounding boxes
        all_text_with_bbox = []
        for page in ocr_data.get('pages', []):
            page_num = page['page_num']
            for region in page.get('text_regions', []):
                all_text_with_bbox.append({
                    'text': region['text'],
                    'bbox': region['bbox'],
                    'page': page_num
                })
        
        # Use AI to extract structured fields
        # This could use Gemini API to map text regions to specific fields
        # For now, return basic structure - can be enhanced later
        
        _logger.info(f"Extracted {len(all_text_with_bbox)} text regions with bounding boxes")
        
        # Return raw text regions for now
        # TODO: Implement AI-based field extraction with specific field mapping
        return {
            'raw_text_regions': all_text_with_bbox
        }

    @api.model
    def transform_ocr_to_extracted_data(self, ocr_data, document_type):
        """
        Transform OCR data to extracted_data format for compatibility

        This method returns the structured data extracted by LlamaParse.

        Args:
            ocr_data (dict): OCR data from extract_with_bbox()
                            Contains: 'extracted_data', 'pages', 'raw_response'
            document_type (str): '01' or '02'

        Returns:
            dict: Structured data in extracted_data format
        """
        # Return the extracted_data directly - it's already in the correct format
        # from LlamaParse structured output
        return ocr_data.get('extracted_data', {})

    # ===================================================================
    # LlamaSplit API - Document Category Splitting
    # ===================================================================

    @api.model
    def split_document_by_categories(self, pdf_binary, document_type, filename):
        """
        Split document into sections using LlamaSplit API

        Uses LlamaCloud Split API to automatically detect document sections
        (metadata, tables, etc.) and returns both section PDFs and page mappings.

        Args:
            pdf_binary (bytes): PDF file content
            document_type (str): '01' or '02'
            filename (str): Original filename for logging

        Returns:
            dict: {
                'section_pdfs': {
                    'metadata': b'PDF bytes...',
                    'substance_production': b'PDF bytes...',
                    ...
                },
                'page_mapping': {
                    'metadata': [1, 2, 3],
                    'substance_production': [4, 5, 6],
                    ...
                }
            }

        Raises:
            ValueError: If API key not configured or split fails
        """
        _logger.info(f"Starting LlamaSplit for {filename} (Type: {document_type})")

        try:
            import requests
            import tempfile
            import os
            import time

            # Get API key
            api_key = self._get_llama_api_key()

            # Step 1: Upload PDF to LlamaCloud
            file_id = self._upload_file_to_llama(pdf_binary, filename, api_key)
            _logger.info(f"Uploaded PDF to LlamaCloud: {file_id}")

            # Step 2: Build categories based on document type
            categories = self._build_split_categories(document_type)
            _logger.info(f"Defined {len(categories)} categories for splitting")

            # Step 3: Create split job
            job_id = self._create_split_job(file_id, categories, api_key)
            _logger.info(f"Created split job: {job_id}")

            # Step 4: Poll for completion
            split_result = self._poll_split_job(job_id, api_key, timeout=120)
            _logger.info(f"Split job completed successfully")

            # Step 5: Parse segments and validate coverage
            page_mapping = self._parse_split_segments(split_result, document_type)
            _logger.info(f"Detected sections: {list(page_mapping.keys())}")

            # Step 6: Split PDF into section PDFs
            section_pdfs = self._split_pdf_by_pages(pdf_binary, page_mapping)
            _logger.info(f"Created {len(section_pdfs)} section PDFs")

            return {
                'section_pdfs': section_pdfs,
                'page_mapping': page_mapping
            }

        except Exception as e:
            _logger.error(f"LlamaSplit failed: {str(e)}", exc_info=True)
            raise ValueError(f"Document splitting failed: {str(e)}")

    def _get_llama_api_key(self):
        """Get LlamaCloud API key from config"""
        ICP = self.env['ir.config_parameter'].sudo()
        api_key = ICP.get_param('robotia_document_extractor.llama_cloud_api_key')

        if not api_key:
            raise ValueError(
                "LlamaCloud API key not configured. "
                "Please configure it in Settings > Document Extractor"
            )

        return api_key

    def _upload_file_to_llama(self, pdf_binary, filename, api_key):
        """
        Upload PDF file to LlamaCloud

        Args:
            pdf_binary (bytes): PDF content
            filename (str): Original filename
            api_key (str): LlamaCloud API key

        Returns:
            str: file_id
        """
        import requests
        import tempfile
        import os

        # Create temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tf:
            tf.write(pdf_binary)
            temp_path = tf.name

        try:
            # Upload to LlamaCloud
            url = "https://api.cloud.llamaindex.ai/api/v1/files"
            headers = {
                "accept": "application/json",
                "Authorization": f"Bearer {api_key}"
            }

            with open(temp_path, 'rb') as f:
                files = {'upload_file': (filename, f, 'application/pdf')}
                response = requests.post(url, headers=headers, files=files, timeout=60)

            if response.status_code not in [200, 201]:
                raise ValueError(f"Upload failed: {response.status_code} - {response.text}")

            result = response.json()
            file_id = result.get('id')

            if not file_id:
                raise ValueError(f"No file_id in response: {result}")

            return file_id

        finally:
            # Cleanup temp file
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def _build_split_categories(self, document_type):
        """
        Build category definitions for LlamaSplit

        Categories describe the document sections to detect.

        Args:
            document_type (str): '01' or '02'

        Returns:
            list: Category definitions with names and descriptions
        """
        if document_type == '01':
            return [
                {
                    "name": "metadata",
                    "description": "Header section containing organization information, business license, contact details, year, legal representative, and activity fields. Usually first 2-3 pages."
                },
                {
                    "name": "substance_production",
                    "description": "Table 1.1a - Substance usage for production activities. Contains columns: substance name, quantities in kg and CO2e for 3 years (year-2, year-1, current year), average values."
                },
                {
                    "name": "substance_import",
                    "description": "Table 1.1b - Substance usage for import activities. Contains columns: substance name, quantities in kg and CO2e for 3 years, average values."
                },
                {
                    "name": "substance_export",
                    "description": "Table 1.1c - Substance usage for export activities. Contains columns: substance name, quantities in kg and CO2e for 3 years, average values."
                },
                {
                    "name": "equipment_product",
                    "description": "Table 1.2 - Equipment/Product manufacturing plans. Contains columns: product type, HS code, capacity (cooling/power), quantity, substance name, substance quantity per unit."
                },
                {
                    "name": "equipment_ownership",
                    "description": "Table 1.3 - Equipment ownership/usage plans. Contains columns: equipment type, start year, capacity, quantity, substance name, refill frequency, substance quantity per refill."
                },
                {
                    "name": "collection_recycling",
                    "description": "Table 1.4 - Collection, recycling, and recovery activities. Contains 6 sub-sections: collection, reuse, recycling, conversion, disposal, destruction. Columns: activity type, substance name, quantity in kg and CO2e."
                }
            ]
        else:  # document_type == '02'
            return [
                {
                    "name": "metadata",
                    "description": "Header section containing organization information, business license, contact details, year, legal representative, and activity fields. Usually first 2-3 pages."
                },
                {
                    "name": "quota_usage",
                    "description": "Table 2.1 - Quota usage report. Contains columns: usage type (production/import/export), substance name, HS code, allocated quota, adjusted quota, total quota (both kg and CO2e), average price, country, customs declaration, next year quota."
                },
                {
                    "name": "equipment_product_report",
                    "description": "Table 2.2 - Equipment/Product production report. Contains columns: production type (manufactured/assembled), product type, HS code, capacity (cooling/power), quantity, substance name, substance quantity per unit."
                },
                {
                    "name": "equipment_ownership_report",
                    "description": "Table 2.3 - Equipment ownership/usage report. Contains columns: ownership type, equipment type, quantity, substance name, capacity, start year, refill frequency, substance quantity per refill."
                },
                {
                    "name": "collection_recycling_report",
                    "description": "Table 2.4 - Collection and recycling report. Contains columns: substance name, collection quantity/location, storage location, reuse quantity/technology, recycle quantity/technology/usage location, disposal quantity/technology/facility."
                }
            ]

    def _create_split_job(self, file_id, categories, api_key):
        """
        Create document split job via API

        Args:
            file_id (str): File ID from upload
            categories (list): Category definitions
            api_key (str): API key

        Returns:
            str: job_id
        """
        import requests

        url = "https://api.cloud.llamaindex.ai/api/v1/document-split/create-job"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "file_id": file_id,
            "split_categories": categories
        }

        response = requests.post(url, headers=headers, json=payload, timeout=30)

        if response.status_code != 200:
            raise ValueError(f"Create split job failed: {response.status_code} - {response.text}")

        result = response.json()
        job_id = result.get('id')

        if not job_id:
            raise ValueError(f"No job_id in response: {result}")

        return job_id

    def _poll_split_job(self, job_id, api_key, timeout=120):
        """
        Poll split job until completion

        Args:
            job_id (str): Job ID to poll
            api_key (str): API key
            timeout (int): Max seconds to wait

        Returns:
            dict: Split result with segments
        """
        import requests
        import time

        url = f"https://api.cloud.llamaindex.ai/api/v1/document-split/job/{job_id}"
        headers = {
            "Authorization": f"Bearer {api_key}"
        }

        start_time = time.time()
        poll_interval = 2  # seconds

        while True:
            # Check timeout
            if time.time() - start_time > timeout:
                raise ValueError(f"Split job timed out after {timeout}s")

            # Poll status
            response = requests.get(url, headers=headers, timeout=30)

            if response.status_code != 200:
                raise ValueError(f"Poll job failed: {response.status_code} - {response.text}")

            result = response.json()
            status = result.get('status')

            _logger.info(f"Split job status: {status}")

            if status == 'completed':
                return result
            elif status == 'failed':
                error_msg = result.get('error', 'Unknown error')
                raise ValueError(f"Split job failed: {error_msg}")
            elif status in ['pending', 'processing']:
                # Continue polling
                time.sleep(poll_interval)
            else:
                raise ValueError(f"Unknown job status: {status}")

    def _parse_split_segments(self, split_result, document_type):
        """
        Parse split segments into page mapping

        Args:
            split_result (dict): Result from poll_split_job
            document_type (str): '01' or '02'

        Returns:
            dict: Page mapping {category: [page_numbers]}
        """
        segments = split_result.get('segments', [])

        if not segments:
            raise ValueError("No segments found in split result")

        page_mapping = {}

        for segment in segments:
            category = segment.get('category')
            page_start = segment.get('page_start')  # 1-indexed
            page_end = segment.get('page_end')      # 1-indexed inclusive
            confidence = segment.get('confidence', 0)

            if not category or page_start is None or page_end is None:
                _logger.warning(f"Invalid segment: {segment}")
                continue

            # Skip low-confidence segments
            if confidence < 0.5:
                _logger.warning(f"Skipping low-confidence segment: {category} (conf={confidence})")
                continue

            # Convert to list of page numbers (1-indexed)
            page_numbers = list(range(page_start, page_end + 1))

            page_mapping[category] = page_numbers
            _logger.info(f"Section '{category}': pages {page_start}-{page_end} (confidence: {confidence:.2f})")

        # Validate coverage
        self._validate_split_coverage(page_mapping, document_type)

        return page_mapping

    def _validate_split_coverage(self, page_mapping, document_type):
        """
        Validate that all critical sections are detected

        Args:
            page_mapping (dict): Detected page mapping
            document_type (str): '01' or '02'

        Raises:
            ValueError: If critical sections are missing
        """
        # Define required sections
        if document_type == '01':
            required = ['metadata']  # Only metadata is critical
            recommended = ['substance_production', 'substance_import', 'substance_export']
        else:
            required = ['metadata']
            recommended = ['quota_usage']

        # Check required sections
        missing_required = [sec for sec in required if sec not in page_mapping]
        if missing_required:
            raise ValueError(f"Missing required sections: {missing_required}")

        # Warn about missing recommended sections
        missing_recommended = [sec for sec in recommended if sec not in page_mapping]
        if missing_recommended:
            _logger.warning(f"Missing recommended sections: {missing_recommended}")

    def _split_pdf_by_pages(self, pdf_binary, page_mapping):
        """
        Split PDF into section PDFs using PyMuPDF

        Args:
            pdf_binary (bytes): Original PDF
            page_mapping (dict): {category: [page_numbers]} (1-indexed)

        Returns:
            dict: {category: section_pdf_bytes}
        """
        import fitz  # PyMuPDF
        import io

        # Open source PDF
        source_doc = fitz.open(stream=pdf_binary, filetype="pdf")

        section_pdfs = {}

        for category, page_numbers in page_mapping.items():
            # Create new PDF for this section
            section_doc = fitz.open()  # Empty PDF

            # Insert pages (convert 1-indexed to 0-indexed)
            for page_num in page_numbers:
                page_idx = page_num - 1  # Convert to 0-indexed

                if page_idx < 0 or page_idx >= source_doc.page_count:
                    _logger.warning(f"Page {page_num} out of range, skipping")
                    continue

                # Insert page into section PDF
                section_doc.insert_pdf(source_doc, from_page=page_idx, to_page=page_idx)

            # Save section PDF to bytes
            section_bytes = section_doc.tobytes()
            section_pdfs[category] = section_bytes

            section_doc.close()

            _logger.info(f"Created section PDF '{category}': {len(section_bytes)} bytes, {len(page_numbers)} pages")

        source_doc.close()

        return section_pdfs
