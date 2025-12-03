/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

/**
 * Raw OCR Viewer Widget
 *
 * Displays OCR data with bounding boxes in an expandable tree structure.
 * Clicking a text region highlights it on the PDF and scrolls to it.
 *
 * Pattern: Follows validation_stats_widget.js
 */
export class RawOCRViewer extends Component {
    static template = "robotia_document_extractor.RawOCRViewer";
    static props = {
        ...standardWidgetProps
    };

    setup() {
        this.state = useState({
            expandedPages: {},
            selectedRegion: null
        });
    }

    /**
     * Parse OCR data from record
     * Returns null if no data or parse error
     */
    get ocrData() {
        const rawData = this.props.record.data.raw_ocr_data;
        if (!rawData) return null;

        try {
            return JSON.parse(rawData);
        } catch (e) {
            console.error("Failed to parse OCR data:", e);
            return null;
        }
    }

    /**
     * Toggle page accordion expand/collapse
     */
    togglePage(pageNum) {
        this.state.expandedPages[pageNum] = !this.state.expandedPages[pageNum];
    }

    /**
     * Handle region click - highlight PDF and scroll
     */
    onRegionClick(pageNum, region) {
        this.state.selectedRegion = { pageNum, region };
        this.highlightPDFRegion(pageNum, region.bbox);
    }

    /**
     * Highlight region on PDF and scroll to it
     *
     * Strategy:
     * 1. Find PDF iframe
     * 2. Access iframe's document
     * 3. Find the correct page
     * 4. Calculate coordinate scaling (PDF points → canvas pixels)
     * 5. Create highlight overlay
     * 6. Scroll to highlighted region
     */
    highlightPDFRegion(pageNum, bbox) {
        // Find PDF iframe
        const pdfIframe = document.querySelector('.o_pdf_preview iframe');
        if (!pdfIframe) {
            console.warn("PDF iframe not found");
            return;
        }

        // Get iframe content window and document
        const iframeDoc = pdfIframe.contentDocument || pdfIframe.contentWindow.document;

        // Remove existing highlights
        const existingHighlights = iframeDoc.querySelectorAll('.ocr-highlight');
        existingHighlights.forEach(el => el.remove());

        // Find the PDF page container
        // PDF.js uses data-page-number attribute (1-indexed)
        const pdfViewer = iframeDoc.querySelector('.page[data-page-number="' + (pageNum + 1) + '"]');
        if (!pdfViewer) {
            console.warn("PDF page not found:", pageNum + 1);
            return;
        }

        // Find canvas to get actual rendered dimensions
        const pdfCanvas = pdfViewer.querySelector('canvas');
        if (!pdfCanvas) {
            console.warn("PDF canvas not found");
            return;
        }

        // Get page dimensions from OCR data (in PDF points)
        const ocrPage = this.ocrData.pages[pageNum];
        if (!ocrPage) {
            console.warn("OCR page data not found:", pageNum);
            return;
        }

        // Calculate scaling factor (PDF points → canvas pixels)
        const scaleX = pdfCanvas.width / ocrPage.page_width;
        const scaleY = pdfCanvas.height / ocrPage.page_height;

        console.debug("Highlight scaling:", {
            pageNum: pageNum + 1,
            pdfDims: { width: ocrPage.page_width, height: ocrPage.page_height },
            canvasDims: { width: pdfCanvas.width, height: pdfCanvas.height },
            scale: { x: scaleX, y: scaleY },
            bbox: bbox
        });

        // Calculate highlight position and size
        const left = bbox.x0 * scaleX;
        const top = bbox.y0 * scaleY;
        const width = (bbox.x1 - bbox.x0) * scaleX;
        const height = (bbox.y1 - bbox.y0) * scaleY;

        // Create highlight overlay
        const highlight = iframeDoc.createElement('div');
        highlight.className = 'ocr-highlight';
        highlight.style.cssText = `
            position: absolute;
            left: ${left}px;
            top: ${top}px;
            width: ${width}px;
            height: ${height}px;
            background: rgba(255, 255, 0, 0.3);
            border: 2px solid #ffcc00;
            pointer-events: none;
            z-index: 9999;
            box-shadow: 0 0 10px rgba(255, 204, 0, 0.5);
        `;

        // Ensure page container is positioned
        pdfViewer.style.position = 'relative';
        pdfViewer.appendChild(highlight);

        // Scroll to highlighted region
        highlight.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    /**
     * Get CSS class for confidence badge based on score
     */
    getConfidenceClass(confidence) {
        if (confidence >= 0.9) return 'text-success';
        if (confidence >= 0.7) return 'text-warning';
        return 'text-danger';
    }
}

// Register widget
registry.category("view_widgets").add("raw_ocr_viewer", {
    component: RawOCRViewer,
});
