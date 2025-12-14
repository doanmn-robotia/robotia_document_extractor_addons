/** @odoo-module **/

import { Component, useState, useRef, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { useService } from "@web/core/utils/hooks";

/**
 * Raw OCR Viewer Widget
 *
 * Displays OCR items with interactive bounding box highlighting on PDF.
 * Users can click items to see their location highlighted on the PDF preview.
 */
export class RawOCRViewer extends Component {
    static template = "robotia_document_extractor.RawOCRViewer";
    static props = {
        ...standardWidgetProps
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.state = useState({
            selectedPage: 0,
            selectedItem: null,
            expandedPages: new Set([0]), // First page expanded by default
            markedLoaded: false
        });

        onMounted(() => {
            // Load marked.js from CDN if not already loaded
            this.loadMarkedJS();
        });
    }

    /**
     * Load marked.js from CDN
     */
    loadMarkedJS() {
        if (window.marked) {
            this.state.markedLoaded = true;
            return; // Already loaded
        }

        const script = document.createElement('script');
        script.src = 'https://cdn.jsdelivr.net/npm/marked@11.1.1/marked.min.js';
        script.async = true;
        script.onload = () => {
            this.state.markedLoaded = true;
        };
        document.head.appendChild(script);
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
     * Parse OCR data and group items by page
     * Returns: [{ page: 1, items: [...], width, height }]
     */
    get pages() {
        if (!this.ocrData || !Array.isArray(this.ocrData)) {
            return [];
        }

        return this.ocrData.map((pageData, index) => ({
            page: pageData.page || index + 1,
            items: pageData.items || [],
            width: pageData.width || 0,
            height: pageData.height || 0,
            md: pageData.md || ''
        }));
    }

    /**
     * Get total number of items across all pages
     */
    get totalItems() {
        return this.pages.reduce((sum, page) => sum + page.items.length, 0);
    }

    /**
     * Get current page data
     */
    get currentPage() {
        return this.pages.find(p => p.page === this.state.selectedPage) || this.pages[0];
    }

    /**
     * Get PDF container from external viewer
     */
    getPDFContainer() {
        return document.querySelector('.o_pdf_preview_content');
    }

    /**
     * Get PDF iframe from external viewer
     */
    getPDFIframe() {
        const container = this.getPDFContainer();
        if (!container) return null;
        return container.querySelector('iframe');
    }

    /**
     * Get scaled bounding box for current selected item
     */
    get scaledBox() {
        if (!this.state.selectedItem || !this.state.selectedItem.bBox) {
            return null;
        }

        const page = this.currentPage;
        if (!page) return null;

        const bbox = this.state.selectedItem.bBox;
        const pdfWidth = page.width;
        const pdfHeight = page.height;

        // Find external PDF container
        const container = this.getPDFContainer();
        if (!container) return null;

        const iframeWidth = container.offsetWidth;
        const iframeHeight = container.offsetHeight;

        // Calculate scale
        const scaleX = iframeWidth / pdfWidth;
        const scaleY = iframeHeight / pdfHeight;

        return {
            x: bbox.x * scaleX,
            y: bbox.y * scaleY,
            w: bbox.w * scaleX,
            h: bbox.h * scaleY
        };
    }

    /**
     * Select an item and highlight it on PDF
     */
    selectItem(item, pageIndex) {
        this.state.selectedPage = pageIndex;
        this.state.selectedItem = item;

        // Create or update overlay on external PDF
        this.updateExternalOverlay();
    }

    /**
     * Create/update SVG overlay on external PDF container
     */
    updateExternalOverlay() {
        const container = this.getPDFContainer();
        if (!container) {
            console.warn('PDF preview container (.o_pdf_preview_content) not found');
            return;
        }

        // Remove existing overlay
        const existingOverlay = container.querySelector('.ocr-bbox-overlay');
        if (existingOverlay) {
            existingOverlay.remove();
        }

        // If no item selected, just remove overlay
        if (!this.state.selectedItem || !this.scaledBox) {
            return;
        }

        // Create SVG overlay
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.classList.add('ocr-bbox-overlay');
        svg.style.position = 'absolute';
        svg.style.top = '0';
        svg.style.left = '0';
        svg.style.width = '100%';
        svg.style.height = '100%';
        svg.style.pointerEvents = 'none';
        svg.style.zIndex = '1000';

        // Create rectangle
        const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        const box = this.scaledBox;
        rect.setAttribute('x', box.x);
        rect.setAttribute('y', box.y);
        rect.setAttribute('width', box.w);
        rect.setAttribute('height', box.h);
        rect.setAttribute('fill', 'rgba(255, 193, 7, 0.25)');
        rect.setAttribute('stroke', '#ffc107');
        rect.setAttribute('stroke-width', '2');
        rect.style.animation = 'pulse-highlight 1.5s ease-in-out infinite';

        svg.appendChild(rect);
        container.appendChild(svg);
    }

    /**
     * Toggle page expansion
     */
    togglePage(pageIndex) {
        if (this.state.expandedPages.has(pageIndex)) {
            this.state.expandedPages.delete(pageIndex);
        } else {
            this.state.expandedPages.add(pageIndex);
        }
        // Force re-render
        this.state.expandedPages = new Set(this.state.expandedPages);
    }

    /**
     * Check if page is expanded
     */
    isPageExpanded(pageIndex) {
        return this.state.expandedPages.has(pageIndex);
    }

    /**
     * Get icon class for item type
     */
    getItemIcon(type) {
        const iconMap = {
            'text': 'fa fa-file-text-o',
            'heading': 'fa fa-header',
            'table': 'fa fa-table'
        };
        return iconMap[type] || 'fa fa-file-o';
    }

    /**
     * Get preview text for item (truncated)
     */
    getItemPreview(item) {
        const text = item.value || item.md || '';
        return text.length > 100 ? text.substring(0, 100) + '...' : text;
    }

    /**
     * Render markdown content to HTML
     */
    renderMarkdown(mdContent) {
        if (!mdContent) {
            return '';
        }

        if (!this.state.markedLoaded || !window.marked) {
            // Return plain text in pre tag if marked not loaded yet
            return `<pre>${mdContent}</pre>`;
        }

        try {
            return window.marked.parse(mdContent);
        } catch (e) {
            console.error("Failed to render markdown:", e);
            return `<pre>${mdContent}</pre>`;
        }
    }
}

// Register widget
registry.category("view_widgets").add("raw_ocr_viewer", {
    component: RawOCRViewer,
});
