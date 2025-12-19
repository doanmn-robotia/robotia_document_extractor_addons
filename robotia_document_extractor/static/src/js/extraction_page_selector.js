/** @odoo-module **/

import { Component, useState, onWillUnmount } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

export class ExtractionPageSelector extends Component {

    static props = {
        ...standardActionServiceProps
    }

    setup() {
        this.rpc = rpc;
        this.action = useService("action");
        this.notification = useService("notification");

        this.bus = useService("bus_service")

        this.state = useState({
            fileName: "",
            pages: [], // Array of {attachment_id, url, page_num}
            selectedPages: new Set(), // Set of attachment IDs
            isProcessing: false,
            base64File: null, // Store base64 of the PDF
            previewUrl: null, // URL to show in preview modal
            documentType: null, // Document type from upload screen
            // PDF preview for progress_only mode
            mergedPdfUrl: null, // URL for merged PDF preview during retry
            // Job polling state
            jobId: null,
            jobUUID: null,
            jobState: null, // 'pending', 'processing', 'done', 'error'
            progress: 0,
            progressMessage: "",
            errorMessage: "",
            currentStep: 'upload_validate', // Current step key for stepper UI
        });

        this.pollingInterval = null;

        onWillUnmount(() => {
            if (this.pollingInterval) {
                clearInterval(this.pollingInterval);
            }
        });

        // Get params from action
        const params = this.props.action.params;
        const mode = params?.mode;  // 'progress_only' or undefined

        if (mode === 'progress_only') {
            // Progress-only mode: No file processing, just show progress
            this.state.documentType = params.document_type;
            this.state.jobId = params.job_id;
            this.state.jobUUID = params.job_uuid;
            this.state.mergedPdfUrl = params.merged_pdf_url || null;  // PDF URL for preview
            this.state.isProcessing = true;

            // Initialize currentStep from retry_from_step (if provided)
            // This makes progress stepper immediately highlight the retry step
            if (params.retry_from_step) {
                this.state.currentStep = params.retry_from_step;
            }

            // Subscribe to bus updates for real-time progress
            this.bus.addEventListener('notification', ({ detail }) => {
                if (detail[0][1] === this.state.jobUUID && detail[1] === 'update_progress') {
                    this.update_progress(detail[2]);
                }
            });

            // Start polling job status
            this.startJobPolling();
        } else if (params && params.fileUrl) {
            // Normal mode: Process file and show page selector
            this.state.documentType = params.documentType || '01';
            this.processInitialFile(params.fileUrl, params.fileName);
        } else {
            // No params → redirect to dashboard
            this.action.doAction({
                type: 'ir.actions.client',
                tag: 'document_extractor.dashboard',
            });
        }
    }

    update_progress(progress) {
        this.state.progress = progress.progress
        this.state.progressMessage = progress.message
        // Update current step if provided
        if (progress.step) {
            this.state.currentStep = progress.step
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
            this.state.isProcessing = false;
            this.action.doAction({
                type: 'ir.actions.client',
                tag: 'document_extractor.dashboard',
            });
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

    /**
     * Get step configuration for progress stepper
     */
    getStepConfig() {
        return [
            { key: 'upload_validate', label: _t('Upload & Validate'), number: 1 },
            { key: 'category_mapping', label: _t('Category Mapping'), number: 2 },
            { key: 'llama_ocr', label: _t('Llama OCR'), number: 3 },
            { key: 'ai_batch_processing', label: _t('AI Processing'), number: 4 },
            { key: 'merge_validate', label: _t('Merge & Validate'), number: 5 },
        ];
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
                attachment_ids: selectedAttachmentIds,
                document_type: this.state.documentType,
                filename: this.state.fileName,
            });

            if (result.type === 'success') {
                // Job created successfully - start polling
                this.state.jobId = result.job_id;
                this.state.jobUUID = result.uuid;
                this.state.jobState = 'pending';
                this.state.progress = 0;
                this.state.progressMessage = _t("Job created, waiting to start...");

                this.notification.add(
                    _t("Extraction job created. Processing..."),
                    { type: "success" }
                );

                this.props.updateActionState({
                    job_id: result.uuid
                })
                
                this.bus.addChannel(this.state.jobUUID)
                this.bus.subscribe('update_progress', this.update_progress.bind(this))

                // Start polling job status
                this.startJobPolling();
            } else if (result.type === 'error') {
                // Error creating job
                this.notification.add(
                    result.message || _t("Error creating extraction job"),
                    { type: "danger" }
                );
                this.state.isProcessing = false;
            }

        } catch (error) {
            console.error("Extraction error:", error);
            this.notification.add(_t("Error during extraction"), { type: "danger" });
            this.state.isProcessing = false;
        }
    }

    startJobPolling() {
        // Poll every 2 seconds
        this.pollingInterval = setInterval(() => this.pollJobStatus(), 2000);
        // Also poll immediately
        this.pollJobStatus();
    }

    async pollJobStatus() {
        if (!this.state.jobId) return;

        try {
            const response = await this.rpc("/robotia/get_my_extraction_jobs", {
                offset: 0,
                limit: 20  // Get recent jobs
            });
            const job = response.jobs.find(j => j.id === this.state.jobId);

            if (!job) {
                console.error("Job not found:", this.state.jobId);
                return;
            }

            // Update state using queue_state
            this.state.jobState = job.queue_state;
            this.state.errorMessage = job.error_message || "";

            // Handle job completion based on queue_state
            if (job.queue_state === 'done') {
                clearInterval(this.pollingInterval);
                this.pollingInterval = null;
                this.state.isProcessing = false;

                // Open the extraction form
                if (job.result_action_json) {
                    const action = JSON.parse(job.result_action_json);
                    await this.action.doAction(action);
                } else {
                    this.notification.add(_t("Extraction completed!"), { type: "success" });
                }
            } else if (job.queue_state === 'failed') {
                clearInterval(this.pollingInterval);
                this.pollingInterval = null;
                this.state.isProcessing = false;

                this.notification.add(
                    job.error_message || _t("Extraction failed"),
                    { type: "danger" }
                );
            } else if (job.queue_state === 'cancelled') {
                clearInterval(this.pollingInterval);
                this.pollingInterval = null;
                this.state.isProcessing = false;

                this.notification.add(
                    _t("Extraction job was cancelled"),
                    { type: "warning" }
                );
            }
            // For 'pending', 'enqueued', 'started' states, keep polling
        } catch (error) {
            console.error("Error polling job status:", error);
            this.bus.unsubscribe('update_progres', this.update_progress.bind(this))
        }
    }
}

ExtractionPageSelector.template = "robotia_document_extractor.ExtractionPageSelector";

registry.category("actions").add("robotia_document_extractor.page_selector", ExtractionPageSelector);
