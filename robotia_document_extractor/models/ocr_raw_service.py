# -*- coding: utf-8 -*-

from odoo import models, api
import logging
import json

_logger = logging.getLogger(__name__)


class OCRRawService(models.AbstractModel):
    """
    OCR Service with Bounding Box Extraction

    Uses EasyOCR for Vietnamese text recognition with coordinate information.
    Returns structured JSON with text regions and bounding boxes for PDF highlighting.
    """
    _name = 'document.ocr.raw.service'
    _description = 'OCR Service with Bounding Boxes'

    @api.model
    def extract_ocr_with_bbox(self, pdf_binary, filename):
        """
        Extract text with bounding boxes using EasyOCR + PyMuPDF

        This method:
        1. Opens PDF with PyMuPDF
        2. Converts each page to high-res image (300 DPI)
        3. Runs EasyOCR to detect text with bounding boxes
        4. Maps image coordinates back to PDF coordinate system
        5. Returns structured data with confidence scores

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
            import easyocr
            import fitz  # PyMuPDF
            from PIL import Image
            import io

            _logger.info(f"Starting OCR extraction for {filename}")

            # Initialize EasyOCR reader (Vietnamese + English)
            # gpu=False to avoid GPU dependency issues in production
            _logger.info("Initializing EasyOCR reader (Vietnamese + English)")
            reader = easyocr.Reader(['vi', 'en'], gpu=False)

            # Open PDF
            doc = fitz.open(stream=pdf_binary, filetype="pdf")
            total_pages = len(doc)
            _logger.info(f"OCR: Processing {total_pages} pages")

            result = {"pages": []}

            for page_num in range(total_pages):
                page = doc[page_num]

                # Get page dimensions (in points, 72 DPI)
                page_rect = page.rect
                page_width = page_rect.width
                page_height = page_rect.height

                _logger.debug(f"Page {page_num + 1}: {page_width} x {page_height} points")

                # Convert page to image (300 DPI for good OCR quality)
                # Matrix(2, 2) doubles the resolution from 72 to 144 DPI
                # Matrix(300/72, 300/72) = Matrix(4.167, 4.167) for 300 DPI
                zoom_factor = 300 / 72
                matrix = fitz.Matrix(zoom_factor, zoom_factor)
                pix = page.get_pixmap(matrix=matrix)

                # Convert pixmap to PIL Image
                img_data = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_data))

                _logger.debug(f"Page {page_num + 1}: Converted to {img.width} x {img.height} image")

                # Run EasyOCR
                _logger.info(f"Page {page_num + 1}: Running OCR...")
                ocr_results = reader.readtext(img)

                # Calculate scale to map image coords back to PDF coords
                scale_x = page_width / img.width
                scale_y = page_height / img.height

                _logger.debug(f"Page {page_num + 1}: Scale factors: X={scale_x:.4f}, Y={scale_y:.4f}")

                # Process OCR results
                text_regions = []
                for (bbox_coords, text, confidence) in ocr_results:
                    # bbox_coords is [[x0,y0], [x1,y0], [x1,y1], [x0,y1]]
                    # We need top-left (x0, y0) and bottom-right (x1, y1)
                    x0 = bbox_coords[0][0] * scale_x
                    y0 = bbox_coords[0][1] * scale_y
                    x1 = bbox_coords[2][0] * scale_x
                    y1 = bbox_coords[2][1] * scale_y

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

            doc.close()

            # Log summary
            total_regions = sum(len(p["text_regions"]) for p in result["pages"])
            _logger.info(f"OCR completed: {total_pages} pages, {total_regions} total regions")

            return result

        except ImportError as e:
            _logger.error(f"OCR library not installed: {e}")
            _logger.error("Please install: pip install easyocr Pillow")
            return None

        except Exception as e:
            _logger.error(f"OCR extraction failed: {str(e)}", exc_info=True)
            return None
