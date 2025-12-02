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
            pages: [], // Array of {attachment_id, url, page_num}
            selectedPages: new Set(), // Set of attachment IDs
            isProcessing: false,
            base64File: null, // Store base64 of the PDF
            previewUrl: null, // URL to show in preview modal
            documentType: null, // Document type from upload screen
        });

        // Get file URL and documentType from action params
        const params = this.props.action.params;
        if (params && params.fileUrl) {
            this.state.documentType = params.documentType || '01'; // Default to '01' if not provided
            this.processInitialFile(params.fileUrl, params.fileName);
        } else {
            // No file provided (e.g., page reload) - redirect to dashboard
            this.notification.add(_t("No file selected. Please upload a file first."), { type: "warning" });
            this.action.doAction({
                type: 'ir.actions.client',
                tag: 'document_extractor.dashboard',
            });
        }
    }

    async processInitialFile(fileUrl, fileName) {
        this.state.fileName = fileName;
        this.state.isProcessing = true;

        try {
            // Fetch the file from the blob URL
            const response = await fetch(fileUrl);
            const blob = await response.blob();

            // Convert blob to base64
            const base64File = await this.readFileAsBase64(blob);

            // Clean up the blob URL after reading
            URL.revokeObjectURL(fileUrl);

            await this.convertPdfToImages(base64File);
        } catch (error) {
            console.error("Error reading file from URL:", error);
            this.notification.add(_t("Error reading file"), { type: "danger" });
            this.state.isProcessing = false;
        }
    }

    readFileAsBase64(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();

            reader.onload = (e) => {
                // Remove the data:application/pdf;base64, prefix
                const base64 = e.target.result.split(',')[1];
                resolve(base64);
            };

            reader.onerror = (error) => {
                reject(error);
            };

            reader.readAsDataURL(file);
        });
    }

    // File upload is handled by upload_area.js, this component only receives the file

    async convertPdfToImages(base64File) {
        try {
            const result = await this.rpc("/robotia/pdf_to_images", {
                pdf_file: base64File,
            });

            if (result.status === "success") {
                this.state.pages = result.pages; // Metadata array
                // Auto-select all pages (using attachment IDs)
                this.state.selectedPages = new Set(
                    result.pages.map(page => page.attachment_id)
                );
                // Store original PDF base64 for extraction
                this.state.base64File = base64File;
            } else {
                this.notification.add(result.message || _t("Error converting PDF"), { type: "danger" });
            }
        } catch (error) {
            console.error("PDF conversion error:", error);
            this.notification.add(_t("Error processing file"), { type: "danger" });
        } finally {
            this.state.isProcessing = false;
        }
    }

    togglePage(attachmentId) {
        if (this.state.selectedPages.has(attachmentId)) {
            this.state.selectedPages.delete(attachmentId);
        } else {
            this.state.selectedPages.add(attachmentId);
        }
    }

    onPageDoubleClick(page) {
        this.state.previewUrl = page.url; // Use URL instead of base64
    }

    closePreview() {
        this.state.previewUrl = null;
    }

    selectAll() {
        this.state.selectedPages = new Set(
            this.state.pages.map(page => page.attachment_id)
        );
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
            this.notification.add(_t("File data is missing"), { type: "danger" });
            return;
        }

        this.state.isProcessing = true;

        try {
            // Send attachment IDs instead of page indices
            const selectedAttachmentIds = Array.from(this.state.selectedPages);

            const result = await this.rpc("/robotia/extract_pages", {
                pdf_file: this.state.base64File,
                attachment_ids: selectedAttachmentIds, // NEW: Send attachment IDs
                document_type: this.state.documentType,
            });

            if (result.type === 'ir.actions.act_window') {
                await this.action.doAction(result);
            } else if (result.type === 'ir.actions.client') {
                this.notification.add(result.params.message, {
                    type: result.params.type
                });
            }
        } catch (error) {
            console.error("Extraction error:", error);
            this.notification.add(_t("Error during extraction"), { type: "danger" });
        } finally {
            this.state.isProcessing = false;
        }
    }
}

ExtractionPageSelector.template = "robotia_document_extractor.ExtractionPageSelector";

registry.category("actions").add("robotia_document_extractor.page_selector", ExtractionPageSelector);
