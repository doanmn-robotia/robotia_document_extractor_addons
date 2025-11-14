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

            if (formSheet && pdfPreview && window.Split) {
                // Use smaller minSize to support different zoom levels and screen sizes
                const splitInstance = Split([formSheet, pdfPreview], {
                    sizes: [55, 45],              // More balanced split
                    minSize: [300, 250],           // Smaller minimum sizes (was 400, 300)
                    expandToMin: false,            // Don't expand to min automatically
                    gutterSize: 10,                // Slightly larger gutter for easier dragging
                    snapOffset: 0,                 // Disable snapping
                    dragInterval: 1,               // Smooth dragging
                    cursor: 'col-resize',          // Explicit cursor
                });

                // Cleanup function to destroy split instance
                return () => {
                    if (splitInstance) {
                        splitInstance.destroy();
                    }
                };
            }

        }, () => []);
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
