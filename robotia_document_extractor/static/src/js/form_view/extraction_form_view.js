/** @odoo-module **/

import { registry } from "@web/core/registry";
import { FormController } from "@web/views/form/form_controller";
import { formView } from "@web/views/form/form_view";
import { FormCompiler } from "@web/views/form/form_compiler";
import { FormRenderer } from "@web/views/form/form_renderer";
import { onWillStart, useEffect, xml } from "@odoo/owl";
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

        // Find the PDF preview container
        const pdfContainer = res.querySelector('.o_pdf_preview');

        if (pdfContainer && parentXml) {
            // Add class for styling
            pdfContainer.classList.add('o-pdf-container');
            // Move PDF container to parent (outside sheet)
            parentXml.appendChild(pdfContainer);
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

        // Load Split.js library
        onWillStart(async () => {
            await loadJS('/robotia_document_extractor/static/lib/split.js');
        });

        // Initialize Split.js after component is mounted
        useEffect(() => {
            const formSheet = document.querySelector(".o_form_renderer > .o_form_sheet_bg");
            const pdfPreview = document.querySelector(".o_form_renderer > .o_pdf_preview");

            if (!formSheet || !pdfPreview || !window.Split) {
                return;
            }

            let splitInstance = null;
            let currentDirection = null;

            // Function to initialize/destroy split based on screen size
            const handleResize = () => {
                const windowWidth = window.innerWidth;

                // Determine direction based on window width
                // Wide screen (>1400px): vertical split (side by side)
                // Medium screen (<=1400px): horizontal split (top/bottom)
                const shouldBeVertical = windowWidth > 1400;
                const newDirection = shouldBeVertical ? 'vertical' : 'horizontal';

                // If direction changed, destroy and recreate
                if (currentDirection !== newDirection) {
                    if (splitInstance) {
                        splitInstance.destroy();
                        splitInstance = null;
                    }

                    // Reset inline styles
                    formSheet.style.width = '';
                    formSheet.style.height = '';
                    pdfPreview.style.width = '';
                    pdfPreview.style.height = '';

                    // Create new split with appropriate direction
                    if (shouldBeVertical) {
                        // Vertical split (side by side)
                        splitInstance = Split([formSheet, pdfPreview], {
                            direction: 'horizontal', // Split.js uses 'horizontal' for vertical layout
                            sizes: [55, 45],
                            minSize: [300, 250],
                            expandToMin: false,
                            gutterSize: 10,
                            snapOffset: 0,
                            dragInterval: 1,
                            cursor: 'col-resize',
                        });
                    } else {
                        // Horizontal split (top/bottom)
                        splitInstance = Split([formSheet, pdfPreview], {
                            direction: 'vertical', // Split.js uses 'vertical' for horizontal layout
                            sizes: [60, 40],
                            minSize: [200, 150],
                            expandToMin: false,
                            gutterSize: 10,
                            snapOffset: 0,
                            dragInterval: 1,
                            cursor: 'row-resize',
                        });
                    }

                    currentDirection = newDirection;
                }
            };

            // Initial setup
            handleResize();

            // Listen to window resize
            window.addEventListener('resize', handleResize);

            // Cleanup function
            return () => {
                window.removeEventListener('resize', handleResize);
                if (splitInstance) {
                    splitInstance.destroy();
                }
            };

        }, () => []);
    }

    async beforeExecuteActionButton(clickParams) {

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
