/** @odoo-module **/

import { registry } from "@web/core/registry";
import { FormController } from "@web/views/form/form_controller";
import { formView } from "@web/views/form/form_view";
import { FormCompiler } from "@web/views/form/form_compiler";
import { FormRenderer } from "@web/views/form/form_renderer";
import { onWillStart, useEffect, useState, xml } from "@odoo/owl";
import { loadJS } from "@web/core/assets";


/**
 * Custom Form Compiler for Document Extraction
 * Extracts the PDF preview container and moves it outside the sheet
 */
export class DocumentExtractionFormCompiler extends FormCompiler {
    compile(node, params) {
        const res = super.compile(node, params);

        // Find the form sheet container
        const formSheetBg = res.querySelector(".o_form_sheet_bg");
        const parentXml = formSheetBg && formSheetBg.parentNode;

        // Find OCR panel container (NEW)
        const ocrPanel = res.querySelector('.o_ocr_panel');

        // Find the PDF preview container
        const pdfContainer = res.querySelector('.o_pdf_preview');

        if (formSheetBg && parentXml) {
            // Move OCR panel to be FIRST child (before form sheet)
            if (ocrPanel) {
                ocrPanel.classList.add('o-ocr-container');
                parentXml.insertBefore(ocrPanel, formSheetBg);
            }

            // Move PDF container to be LAST child (after form sheet)
            if (pdfContainer) {
                pdfContainer.classList.add('o-pdf-container');
                parentXml.appendChild(pdfContainer);
            }
        }

        return res;
    }
}


/**
 * Custom Form Renderer for Document Extraction
 */
export class DocumentExtractionFormRenderer extends FormRenderer {
    static props = {
        ...FormRenderer.props,
        controller: { type: Object, optional: false }
    };

    static template = xml`
        <t t-call="{{ templates.FormRenderer }}"
           t-call-context="{ __comp__: Object.assign(Object.create(this), { this: this })}" />
    `;
}


/**
 * Custom Form Controller for Document Extraction
 * Handles Split.js initialization for split view with PDF preview
 * Responsive: Only enables split on desktop (>=992px), stacks on mobile
 */
export class DocumentExtractionFormController extends FormController {
    static template = "robotia_document_extractor.ExtractionFormView";

    setup() {
        super.setup();

        // Toggle state for OCR panel
        this.ocrState = useState({
            isVisible: true  // Default: show OCR if data exists
        });

        // Load Split.js library
        onWillStart(async () => {
            await loadJS('/robotia_document_extractor/static/lib/split.js');
        });

        // Initialize Split.js after component is mounted
        useEffect(() => {
            const ocrPanel = document.querySelector(".o_form_renderer > .o_ocr_panel");
            const formSheet = document.querySelector(".o_form_renderer > .o_form_sheet_bg");
            const pdfPreview = document.querySelector(".o_form_renderer > .o_pdf_preview");

            if (!formSheet || !pdfPreview || !window.Split) {
                return;
            }

            // Check if OCR data exists
            const hasOcrData = ocrPanel && this.model.root.data.raw_ocr_data;

            let splitInstance = null;
            let currentMode = null; // Tracks: '3-panel-horizontal', '2-panel-horizontal', 'stacked', etc.

            const handleResize = () => {
                const windowWidth = window.innerWidth;

                // Determine layout mode
                let newMode;
                if (windowWidth <= 991) {
                    // Mobile: stack vertically (no split)
                    newMode = 'stacked';
                } else if (hasOcrData && this.ocrState.isVisible) {
                    // Desktop with OCR visible: 3-panel split
                    newMode = windowWidth > 1400 ? '3-panel-horizontal' : '3-panel-vertical';
                } else {
                    // Desktop without OCR: 2-panel split
                    newMode = windowWidth > 1400 ? '2-panel-horizontal' : '2-panel-vertical';
                }

                // Recreate split if mode changed
                if (currentMode !== newMode) {
                    // Destroy existing split
                    if (splitInstance) {
                        splitInstance.destroy();
                        splitInstance = null;
                    }

                    // Reset inline styles
                    formSheet.style.width = '';
                    formSheet.style.height = '';
                    pdfPreview.style.width = '';
                    pdfPreview.style.height = '';
                    if (ocrPanel) {
                        ocrPanel.style.width = '';
                        ocrPanel.style.height = '';
                        ocrPanel.style.display = '';
                    }

                    // Create appropriate split configuration
                    if (newMode === 'stacked') {
                        // Mobile: CSS-only stacking, hide OCR if not visible
                        if (ocrPanel) {
                            ocrPanel.style.display = this.ocrState.isVisible ? 'block' : 'none';
                        }
                    } else if (newMode === '3-panel-horizontal') {
                        // Desktop horizontal: OCR | Form | PDF
                        ocrPanel.style.display = 'block';
                        splitInstance = Split([ocrPanel, formSheet, pdfPreview], {
                            direction: 'horizontal',
                            sizes: [25, 40, 35],
                            minSize: [200, 300, 250],
                            gutterSize: 10,
                            cursor: 'col-resize',
                        });
                    } else if (newMode === '3-panel-vertical') {
                        // Tablet vertical: OCR / Form / PDF
                        ocrPanel.style.display = 'block';
                        splitInstance = Split([ocrPanel, formSheet, pdfPreview], {
                            direction: 'vertical',
                            sizes: [25, 40, 35],
                            minSize: [150, 200, 150],
                            gutterSize: 10,
                            cursor: 'row-resize',
                        });
                    } else if (newMode === '2-panel-horizontal') {
                        // Desktop horizontal without OCR: Form | PDF
                        if (ocrPanel) ocrPanel.style.display = 'none';
                        splitInstance = Split([formSheet, pdfPreview], {
                            direction: 'horizontal',
                            sizes: [50, 50],
                            minSize: [300, 250],
                            gutterSize: 10,
                            cursor: 'col-resize',
                        });
                    } else if (newMode === '2-panel-vertical') {
                        // Tablet vertical without OCR: Form / PDF
                        if (ocrPanel) ocrPanel.style.display = 'none';
                        splitInstance = Split([formSheet, pdfPreview], {
                            direction: 'vertical',
                            sizes: [60, 40],
                            minSize: [200, 150],
                            gutterSize: 10,
                            cursor: 'row-resize',
                        });
                    }

                    currentMode = newMode;
                }
            };

            // Initial setup
            handleResize();

            // Listen to window resize
            window.addEventListener('resize', handleResize);

            // Cleanup
            return () => {
                window.removeEventListener('resize', handleResize);
                if (splitInstance) {
                    splitInstance.destroy();
                }
            };
        }, () => [this.ocrState.isVisible]); // Re-run when OCR visibility changes
    }

    async beforeExecuteActionButton(clickParams) {
        // Handle OCR panel toggle
        if (clickParams.name === 'action_toggle_ocr_panel') {
            this.ocrState.isVisible = !this.ocrState.isVisible;
            return false; // Prevent server call
        }

        // Handle reanalyze button
        if (clickParams.name == 'action_reanalyze_with_ai') {
            try {
                const saved = super.beforeExecuteActionButton(clickParams)
                if (saved == false) {
                    return saved
                }
                this.ui.block()
                const res = await this.orm.call(this.model.root.resModel, 'action_reanalyze_with_ai', [[this.model.root.resId]])
                // res should be an array of: json data to change and brief message to notify user
                // extract data to update and message from res
                const [data, message] = res
                // update record:
                // this.model.root.update(data)

            } finally {
                this.ui.unblock()
            }

            return false
        }
    }
}


/**
 * Register the custom form view
 */
registry.category('views').add('document_extraction_form', {
    ...formView,
    Controller: DocumentExtractionFormController,
    Compiler: DocumentExtractionFormCompiler,
    Renderer: DocumentExtractionFormRenderer
});
