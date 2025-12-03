# -*- coding: utf-8 -*-

from odoo import models, api
import logging
import json

_logger = logging.getLogger(__name__)


class OCRRawService(models.AbstractModel):
    """
    OCR Service with Bounding Box Extraction using Gemini Vision API

    Uses Google Gemini Vision for Vietnamese text recognition with coordinate information.
    Returns structured JSON with text regions and bounding boxes for PDF highlighting.
    
    Advantages of Gemini Vision OCR:
    - Excellent Vietnamese text recognition accuracy
    - No additional dependencies (uses existing Gemini API)
    - No GPU/CUDA requirements
    - Structured JSON output with bounding boxes
    - Server-side processing (no local compute)
    """
    _name = 'document.ocr.raw.service'
    _description = 'OCR Service with Bounding Boxes (Gemini Vision)'

    @api.model
    def extract_ocr_with_bbox(self, pdf_binary, filename):
        """
        Extract text with bounding boxes using Gemini Vision API + PyMuPDF

        This method:
        1. Opens PDF with PyMuPDF
        2. Converts each page to high-res image (300 DPI)
        3. Uploads image to Gemini Vision
        4. Requests structured OCR output with bounding boxes
        5. Maps image coordinates back to PDF coordinate system
        6. Returns structured data with confidence scores

        Args:
            pdf_binary (bytes): Binary PDF data
            filename (str): Original filename (for logging)

        Returns:
            dict or None: {
                "pages": [
                    {
                        "page_num": 0,
                        "page_width": 595.276,
                        "page_height": 841.890,
                        "text_regions": [
                            {
                                "text": "R-410A",
                                "bbox": {"x0": 100, "y0": 200, "x1": 150, "y1": 220},
                                "confidence": 0.95
                            }
                        ]
                    }
                ]
            }
            Returns None if OCR fails (graceful degradation)
        """
        try:
            # Import dependencies
            from google import genai
            from google.genai import types
            import fitz  # PyMuPDF
            import tempfile
            import os
            import time

            _logger.info(f"Starting Gemini Vision OCR extraction for {filename}")

            # Get Gemini API key from config
            ICP = self.env['ir.config_parameter'].sudo()
            api_key = ICP.get_param('robotia_document_extractor.gemini_api_key')
            
            if not api_key:
                _logger.error("Gemini API key not configured")
                return None

            # Initialize Gemini client
            client = genai.Client(api_key=api_key)
            
            # Get Gemini model from config (default: gemini-2.0-flash-exp for fast OCR)
            GEMINI_MODEL = ICP.get_param(
                'robotia_document_extractor.gemini_model',
                default='gemini-2.0-flash-exp'
            )

            # Open PDF
            doc = fitz.open(stream=pdf_binary, filetype="pdf")
            total_pages = len(doc)
            _logger.info(f"OCR: Processing {total_pages} pages with Gemini Vision")

            result = {"pages": []}

            for page_num in range(total_pages):
                page = doc[page_num]

                # Get page dimensions (in points, 72 DPI)
                page_rect = page.rect
                page_width = page_rect.width
                page_height = page_rect.height

                _logger.debug(f"Page {page_num + 1}: {page_width} x {page_height} points")

                # Convert page to image (300 DPI for good OCR quality)
                zoom_factor = 300 / 72
                matrix = fitz.Matrix(zoom_factor, zoom_factor)
                pix = page.get_pixmap(matrix=matrix)

                # Get image dimensions
                img_width = pix.width
                img_height = pix.height

                _logger.debug(f"Page {page_num + 1}: Converted to {img_width} x {img_height} image")

                # Save image to temporary file for Gemini upload
                tmp_image_path = None
                uploaded_file = None
                
                try:
                    # Create temporary PNG file
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
                        tmp_image_path = tmp_file.name
                        pix.save(tmp_image_path)

                    _logger.debug(f"Page {page_num + 1}: Saved temp image: {tmp_image_path}")

                    # Upload image to Gemini
                    uploaded_file = client.files.upload(file=tmp_image_path)
                    _logger.debug(f"Page {page_num + 1}: Uploaded to Gemini: {uploaded_file.name}")

                    # Wait for file processing
                    poll_count = 0
                    max_polls = 30
                    while uploaded_file.state.name == "PROCESSING":
                        if poll_count >= max_polls:
                            raise TimeoutError("Gemini file processing timeout")
                        time.sleep(1)
                        uploaded_file = client.files.get(name=uploaded_file.name)
                        poll_count += 1

                    if uploaded_file.state.name == "FAILED":
                        raise ValueError("Gemini file processing failed")

                    # Build OCR prompt requesting structured output
                    ocr_prompt = """
You are an OCR system. Extract ALL text from this image with bounding box coordinates.

CRITICAL: Return ONLY valid JSON. No markdown, no explanations, no code blocks.

Output format (STRICT JSON):
{
  "text_regions": [
    {
      "text": "extracted text here",
      "bbox": {"x0": 100, "y0": 50, "x1": 200, "y1": 80},
      "confidence": 0.95
    }
  ]
}

Requirements:
1. Extract EVERY piece of text visible
2. Preserve Vietnamese diacritics exactly
3. Bounding box coordinates in pixels (x0,y0 = top-left, x1,y1 = bottom-right)
4. Confidence: 0.0 to 1.0 (estimate based on text clarity)
5. If no text found, return: {"text_regions": []}

Return the JSON now.
"""

                    # Run Gemini Vision OCR
                    _logger.info(f"Page {page_num + 1}: Running Gemini Vision OCR...")
                    
                    response = client.models.generate_content(
                        model=GEMINI_MODEL,
                        contents=[uploaded_file, ocr_prompt],
                        config=types.GenerateContentConfig(
                            temperature=0.1,
                            response_mime_type='application/json',
                        )
                    )

                    # Get response text
                    response_text = response.text
                    _logger.debug(f"Page {page_num + 1}: Gemini response length: {len(response_text)} chars")

                    # Parse JSON response with error handling
                    try:
                        ocr_data = json.loads(response_text)
                    except json.JSONDecodeError as e:
                        _logger.error(f"Page {page_num + 1}: JSON parse error: {e}")
                        _logger.error(f"Response preview: {response_text[:500]}")
                        
                        # Try to extract JSON from markdown code block if present
                        if "```json" in response_text or "```" in response_text:
                            _logger.info("Attempting to extract JSON from markdown code block...")
                            import re
                            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
                            if json_match:
                                try:
                                    ocr_data = json.loads(json_match.group(1))
                                    _logger.info("Successfully extracted JSON from markdown")
                                except json.JSONDecodeError:
                                    _logger.error("Failed to parse extracted JSON")
                                    ocr_data = {"text_regions": []}
                            else:
                                _logger.error("Could not find JSON in markdown")
                                ocr_data = {"text_regions": []}
                        else:
                            # Return empty result for this page
                            _logger.warning(f"Page {page_num + 1}: Returning empty OCR result due to parse error")
                            ocr_data = {"text_regions": []}
                    
                    # Calculate scale to map image coords back to PDF coords
                    scale_x = page_width / img_width
                    scale_y = page_height / img_height

                    _logger.debug(f"Page {page_num + 1}: Scale factors: X={scale_x:.4f}, Y={scale_y:.4f}")

                    # Process OCR results
                    text_regions = []
                    
                    for region in ocr_data.get('text_regions', []):
                        text = region.get('text', '')
                        bbox = region.get('bbox', {})
                        confidence = region.get('confidence', 0.0)

                        # Validate bbox has required fields
                        if not all(k in bbox for k in ['x0', 'y0', 'x1', 'y1']):
                            _logger.warning(f"Skipping region with invalid bbox: {region}")
                            continue

                        # Scale coordinates from image to PDF space
                        x0 = bbox.get('x0', 0) * scale_x
                        y0 = bbox.get('y0', 0) * scale_y
                        x1 = bbox.get('x1', 0) * scale_x
                        y1 = bbox.get('y1', 0) * scale_y

                        text_regions.append({
                            "text": text,
                            "bbox": {
                                "x0": round(x0, 2),
                                "y0": round(y0, 2),
                                "x1": round(x1, 2),
                                "y1": round(y1, 2)
                            },
                            "confidence": round(confidence, 3)
                        })

                    result["pages"].append({
                        "page_num": page_num,
                        "page_width": round(page_width, 2),
                        "page_height": round(page_height, 2),
                        "text_regions": text_regions
                    })

                    _logger.info(f"OCR page {page_num + 1}: Found {len(text_regions)} text regions")

                finally:
                    # Cleanup temporary file
                    if tmp_image_path and os.path.exists(tmp_image_path):
                        try:
                            os.unlink(tmp_image_path)
                            _logger.debug(f"Cleaned up temp image: {tmp_image_path}")
                        except Exception as e:
                            _logger.warning(f"Failed to cleanup temp image: {e}")

                    # Cleanup Gemini uploaded file
                    if uploaded_file:
                        try:
                            client.files.delete(name=uploaded_file.name)
                            _logger.debug(f"Deleted Gemini file: {uploaded_file.name}")
                        except Exception as e:
                            _logger.warning(f"Failed to delete Gemini file: {e}")

            doc.close()

            # Log summary
            total_regions = sum(len(p["text_regions"]) for p in result["pages"])
            _logger.info(f"Gemini Vision OCR completed: {total_pages} pages, {total_regions} total regions")

            return result

        except ImportError as e:
            _logger.error(f"Required library not installed: {e}")
            _logger.error("Please ensure google-genai and PyMuPDF are installed")
            return None

        except Exception as e:
            _logger.error(f"Gemini Vision OCR extraction failed: {str(e)}", exc_info=True)
            return None

