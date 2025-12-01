/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export class ExtractionPageSelector extends Component {
    setup() {
        this.rpc = rpc;
        this.action = useService("action");
        this.notification = useService("notification");

        this.state = useState({
            fileName: "",
            images: [], // Array of base64 strings
            selectedPages: new Set(), // Set of page indices
            isProcessing: false,
            base64File: null, // Store base64 of the PDF
            previewImage: null, // Image to show in preview modal
            documentType: null, // Document type from upload screen
        });

        // Get file and documentType from action params
        const params = this.props.action.params;
        if (params && params.file) {
            this.state.documentType = params.documentType || '01'; // Default to '01' if not provided
            this.processInitialFile(params.file, params.fileName);
        } else {
            // No file provided (e.g., page reload) - redirect to dashboard
            this.notification.add(_t("No file selected. Please upload a file first."), { type: "warning" });
            this.action.doAction({
                type: 'ir.actions.client',
                tag: 'document_extractor.dashboard',
            });
        }
    }

    async processInitialFile(base64File, fileName) {
        this.state.fileName = fileName;
        this.state.isProcessing = true;
        await this.convertPdfToImages(base64File);
    }

    // File upload is handled by upload_area.js, this component only receives the file

    async convertPdfToImages(base64File) {
        try {
            const result = await this.rpc("/robotia/pdf_to_images", {
                pdf_file: base64File,
            });

            if (result.status === "success") {
                this.state.images = result.images;
                // Auto-select all pages by default
                this.state.selectedPages = new Set(result.images.map((_, i) => i));
                // Store base64 for extraction step
                this.state.base64File = base64File;
            } else {
                this.notification.add(result.message || _t("Error converting PDF"), { type: "danger" });
            }
        } catch (error) {
            this.notification.add(_t("Error processing file"), { type: "danger" });
        } finally {
            this.state.isProcessing = false;
        }
    }

    togglePage(index) {
        if (this.state.selectedPages.has(index)) {
            this.state.selectedPages.delete(index);
        } else {
            this.state.selectedPages.add(index);
        }
    }

    onPageDoubleClick(index) {
        this.state.previewImage = this.state.images[index];
    }

    closePreview() {
        this.state.previewImage = null;
    }

    selectAll() {
        this.state.images.forEach((_, i) => this.state.selectedPages.add(i));
    }

    deselectAll() {
        this.state.selectedPages.clear();
    }

    async onExtract() {
        if (this.state.selectedPages.size === 0) {
            this.notification.add(_t("Please select at least one page"), { type: "warning" });
            return;
        }

        if (!this.state.base64File) {
            this.notification.add(_t("No file data found"), { type: "danger" });
            return;
        }

        this.state.isProcessing = true;

        try {
            const result = await this.rpc("/robotia/extract_pages", {
                pdf_file: this.state.base64File,
                page_indices: Array.from(this.state.selectedPages).sort((a, b) => a - b),
                document_type: this.state.documentType, // Use documentType from upload screen
            });

            if (result.status === "success") {
                this.action.doAction(result.action);
            } else {
                this.notification.add(result.message || "Error extracting pages", { type: "danger" });
            }
            this.state.isProcessing = false;

        } catch (error) {
            this.notification.add("Error starting extraction", { type: "danger" });
            this.state.isProcessing = false;
        }
    }
}

ExtractionPageSelector.template = "robotia_document_extractor.ExtractionPageSelector";

registry.category("actions").add("robotia_document_extractor.page_selector", ExtractionPageSelector);
