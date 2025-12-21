/** @odoo-module **/

import { Component, useState, useRef, onMounted, markup } from "@odoo/owl";
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
     * IMPORTANT: Must find container in PDF panel (right side), NOT in OCR panel (left side)
     */
    getPDFContainer() {
        // Find PDF panel specifically (using multiple selectors for safety)
        // The PDF panel should be the 3rd child in the form renderer (OCR | Form | PDF)
        const formRenderer = document.querySelector('.o_form_renderer');
        if (!formRenderer) {
            console.error('❌ Form renderer not found');
            return null;
        }

        // Find all direct children
        const children = formRenderer.children;
        console.log('🔍 Form renderer children:', children.length);

        // Look for PDF panel (should be last child, or one with .o_pdf_preview class)
        let pdfPanel = null;
        for (let i = 0; i < children.length; i++) {
            const child = children[i];
            console.log(`🔍 Child ${i}:`, child.className);

            if (child.classList.contains('o_pdf_preview') ||
                child.classList.contains('o-pdf-container')) {
                pdfPanel = child;
                console.log('✅ Found PDF panel:', child.className);
                break;
            }
        }

        if (!pdfPanel) {
            console.error('❌ PDF panel not found in form renderer children');
            return null;
        }

        // Find content container within PDF panel
        const container = pdfPanel.querySelector('.o_pdf_preview_content');
        if (!container) {
            console.error('❌ .o_pdf_preview_content not found in PDF panel');
            console.log('🔍 PDF panel innerHTML:', pdfPanel.innerHTML.substring(0, 300));
            return null;
        }

        console.log('✅ PDF container found:', container);
        return container;
    }

    /**
     * Get PDF iframe from external viewer
     */
    getPDFIframe() {
        const container = this.getPDFContainer();
        if (!container) {
            console.warn('Cannot get iframe: container not found');
            return null;
        }

        const iframe = container.querySelector('iframe');
        if (!iframe) {
            console.warn('iframe not found in container');
            console.log('Container innerHTML:', container.innerHTML.substring(0, 200));
        }

        return iframe;
    }

    /**
     * Get scaled bounding box for current selected item
     */
    get scaledBox() {
        if (!this.state.selectedItem || !this.state.selectedItem.bBox) {
            return null;
        }

        // Get current page data (contains actual PDF dimensions)
        const page = this.currentPage;
        if (!page || !page.width || !page.height) {
            console.warn('Page dimensions not found in OCR data');
            return null;
        }

        const bbox = this.state.selectedItem.bBox;

        // OCR data dimensions (actual PDF page size in pixels)
        const pdfPageWidth = page.width;
        const pdfPageHeight = page.height;

        // Find external PDF container
        const container = this.getPDFContainer();
        if (!container) return null;

        // Get iframe element and its rendered dimensions
        const iframe = this.getPDFIframe();
        if (!iframe) return null;

        const iframeRect = iframe.getBoundingClientRect();
        const iframeWidth = iframeRect.width;
        const iframeHeight = iframeRect.height;

        // Calculate scale ratios for both dimensions
        const scaleX = iframeWidth / pdfPageWidth;
        const scaleY = iframeHeight / pdfPageHeight;

        // Use uniform scale (smaller value) to maintain aspect ratio
        // PDF viewers use "fit to page" which preserves aspect ratio
        const scale = Math.min(scaleX, scaleY);

        // Calculate centering offsets (when aspect ratios don't match)
        const scaledPageWidth = pdfPageWidth * scale;
        const scaledPageHeight = pdfPageHeight * scale;
        const offsetX = (iframeWidth - scaledPageWidth) / 2;
        const offsetY = (iframeHeight - scaledPageHeight) / 2;

        return {
            x: (bbox.x * scale) + offsetX,
            y: (bbox.y * scale) + offsetY,
            w: bbox.w * scale,
            h: bbox.h * scale
        };
    }

    /**
     * Select an item and highlight it on PDF
     */
    selectItem(item, pageIndex) {
        this.state.selectedPage = pageIndex;
        this.state.selectedItem = item;

        // Ensure PDF tab is active before highlighting
        this.activatePDFTab();

        // Wait a bit for tab switch, then highlight
        setTimeout(() => {
            this.updateExternalOverlay();
        }, 100);
    }

    /**
     * Activate PDF tab in notebook (if not already active)
     */
    activatePDFTab() {
        // Find PDF preview panel
        const pdfPanel = document.querySelector('.o_pdf_preview, .o-pdf-container');
        if (!pdfPanel) {
            console.warn('⚠️ PDF panel not found');
            return;
        }

        // Find all nav links in the notebook
        const navLinks = pdfPanel.querySelectorAll('.nav-link');
        console.log('🔍 Found nav links:', navLinks.length);

        // Find the PDF tab (first tab, or one containing "PDF")
        let pdfTab = null;
        for (const link of navLinks) {
            const text = link.textContent.trim();
            console.log('🔍 Tab text:', text);

            // Match "PDF Document Preview" or similar
            if (text.includes('PDF') || text.includes('Document')) {
                pdfTab = link;
                break;
            }
        }

        // Fallback: use first tab
        if (!pdfTab && navLinks.length > 0) {
            pdfTab = navLinks[0];
        }

        if (!pdfTab) {
            console.warn('⚠️ PDF tab not found in notebook');
            return;
        }

        console.log('✅ PDF tab found:', pdfTab.textContent.trim());

        // Click tab if not active
        if (!pdfTab.classList.contains('active')) {
            console.log('🔄 Switching to PDF tab...');
            pdfTab.click();
        } else {
            console.log('ℹ️ PDF tab already active');
        }
    }

    /**
     * Create/update SVG overlay on external PDF container
     */
    updateExternalOverlay() {
        const container = this.getPDFContainer();
        if (!container) {
            console.error('❌ PDF preview container (.o_pdf_preview_content) not found!');
            console.log('🔍 Available containers:', document.querySelectorAll('.o_pdf_preview'));
            return;
        }

        console.log('✅ PDF container found:', container);

        // Try to find iframe and textLayer (PDF.js viewer)
        const iframe = this.getPDFIframe();
        let overlayTarget = container;
        let useTextLayer = false;

        if (iframe) {
            try {
                // Access iframe content document
                const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                const textLayer = iframeDoc.querySelector('.textLayer');

                if (textLayer) {
                    console.log('✅ Found .textLayer in iframe, will use it for overlay');
                    overlayTarget = textLayer;
                    useTextLayer = true;
                } else {
                    console.log('⚠️ .textLayer not found in iframe, using container instead');
                }
            } catch (e) {
                console.warn('⚠️ Cannot access iframe content (CORS?):', e.message);
            }
        }

        // Remove existing overlay from both possible locations
        const existingInContainer = container.querySelector('.ocr-bbox-overlay');
        if (existingInContainer) {
            existingInContainer.remove();
        }

        if (useTextLayer) {
            const existingInTextLayer = overlayTarget.querySelector('.ocr-bbox-overlay');
            if (existingInTextLayer) {
                existingInTextLayer.remove();
            }
        }

        // If no item selected, just remove overlay
        if (!this.state.selectedItem) {
            console.log('ℹ️ No item selected, overlay cleared');
            return;
        }

        const scaledBox = this.scaledBox;
        if (!scaledBox) {
            console.error('❌ Failed to calculate scaled bounding box');
            console.log('🔍 Current page:', this.currentPage);
            console.log('🔍 Selected item bbox:', this.state.selectedItem.bBox);
            return;
        }

        console.log('✅ Scaled box calculated:', scaledBox);

        // Calculate padding/border offset if using container (not textLayer)
        let offsetX = 0;
        let offsetY = 0;

        if (!useTextLayer) {
            // IMPORTANT: Ensure container has position: relative for absolute positioning
            const computedStyle = window.getComputedStyle(container);
            const currentPosition = computedStyle.position;
            console.log('🔍 Container current position:', currentPosition);

            if (currentPosition === 'static') {
                console.log('⚠️ Container has position: static, setting to relative');
                container.style.position = 'relative';
            }

            // Calculate padding offset
            const paddingLeft = parseFloat(computedStyle.paddingLeft) || 0;
            const paddingTop = parseFloat(computedStyle.paddingTop) || 0;
            const borderLeft = parseFloat(computedStyle.borderLeftWidth) || 0;
            const borderTop = parseFloat(computedStyle.borderTopWidth) || 0;

            offsetX = paddingLeft + borderLeft;
            offsetY = paddingTop + borderTop;

            console.log('🔍 Container offsets:', { paddingLeft, paddingTop, borderLeft, borderTop, offsetX, offsetY });
        }

        // Log container dimensions and position
        const containerRect = overlayTarget.getBoundingClientRect();
        console.log('🔍 Overlay target rect:', {
            top: containerRect.top,
            left: containerRect.left,
            width: containerRect.width,
            height: containerRect.height
        });

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

        // Create rectangle with offset adjustments
        const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        const box = this.scaledBox;
        rect.setAttribute('x', box.x + offsetX);
        rect.setAttribute('y', box.y + offsetY);
        rect.setAttribute('width', box.w);
        rect.setAttribute('height', box.h);
        rect.setAttribute('fill', 'rgba(255, 193, 7, 0.25)');
        rect.setAttribute('stroke', '#ffc107');
        rect.setAttribute('stroke-width', '2');
        rect.style.animation = 'pulse-highlight 1.5s ease-in-out infinite';

        svg.appendChild(rect);
        overlayTarget.appendChild(svg);

        console.log(`✅ SVG overlay appended to ${useTextLayer ? 'textLayer' : 'container'}`);
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
     * Render markdown content to HTML using markup() for safe rendering
     * Returns markup object (not string) for use with t-out directive
     */
    renderMarkdown(mdContent) {
        if (!mdContent) {
            return markup('');
        }

        if (!this.state.markedLoaded || !window.marked) {
            // Fallback: return escaped plain text in pre tag
            const escaped = mdContent
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;');
            return markup(`<pre>${escaped}</pre>`);
        }

        try {
            const html = window.marked.parse(mdContent);
            return markup(html); // Wrap HTML in markup() for safe rendering
        } catch (e) {
            console.error("Failed to render markdown:", e);
            const escaped = mdContent
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;');
            return markup(`<pre>${escaped}</pre>`);
        }
    }
}

// Register widget
registry.category("view_widgets").add("raw_ocr_viewer", {
    component: RawOCRViewer,
});
