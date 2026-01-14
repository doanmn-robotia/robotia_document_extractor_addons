/** @odoo-module **/

import { Component, useState, onWillUnmount, onMounted } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { ExtractionSkeleton } from "./components/skeleton_loader";

export class ExtractionPageSelector extends Component {

    static props = {
        ...standardActionServiceProps
    }

    static components = {
        ExtractionSkeleton
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
            activePageId: null, // Currently visible page (>50% in viewport)
            isProcessing: false,
            base64File: null, // Store base64 of the PDF
            previewUrl: null, // URL to show in preview modal
            documentType: null, // Document type from upload screen
            // PDF preview for progress_only mode
            mergedPdfUrl: null, // URL for merged PDF preview during retry
            // Job polling state
            jobUUID: null,
            jobState: null, // 'pending', 'processing', 'done', 'error'
            progress: 0,
            progressMessage: "",
            errorMessage: "",
            currentStep: 'queue_pending', // Current step key for stepper UI (default to queue pending)
            // Sub-step state for category-level progress
            detectedCategories: [], // Category keys detected in mapping step
            currentSubStep: null, // Current category being processed
            // Store sub-steps per step (persisted when step completes)
            stepSubSteps: {}, // { 'llama_ocr': ['cat1', 'cat2'], 'ai_batch_processing': ['cat1'] }
        });

        this.pollingInterval = null;
        this.intersectionObserver = null;
        this.isProgrammaticScroll = false; // Flag to prevent scroll conflicts

        onMounted(() => {
            this.setupIntersectionObserver();
        });

        onWillUnmount(() => {
            if (this.pollingInterval) {
                clearInterval(this.pollingInterval);
            }
            if (this.intersectionObserver) {
                this.intersectionObserver.disconnect();
            }
            this.unsubscribe(this.state.jobUUID)
        });

        // Get params from action
        const params = this.props.action.params;
        const job_id = params?.job_id || params?.job_uuid;

        if (job_id) {
            this.state.isProcessing = true
            this.state.jobUUID = job_id

            if (params.retry_from_step) {
                this.state.currentStep = params.retry_from_step
            }

            if (params.progress) {
                this.state.progress = params.progress
            }

            this.state.documentType = params.document_type || '01';

            this.subscribe(job_id)
            this.startJobPolling()
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
            const previousStep = this.state.currentStep

            // If step changed, save current sub-step to previous step and reset for new step
            if (previousStep !== progress.step) {
                // Save the last sub-step to completed list for previous step
                if (this.state.currentSubStep && (previousStep === 'llama_ocr' || previousStep === 'ai_batch_processing')) {
                    const prevSubSteps = this.state.stepSubSteps[previousStep] || []
                    if (!prevSubSteps.includes(this.state.currentSubStep)) {
                        this.state.stepSubSteps = {
                            ...this.state.stepSubSteps,
                            [previousStep]: [...prevSubSteps, this.state.currentSubStep]
                        }
                    }
                }
                // Reset current sub-step for new step
                this.state.currentSubStep = null
            }

            this.state.currentStep = progress.step
            this.props.updateActionState({
                retry_from_step: progress.step
            })
        }

        // Handle detected categories (from category_mapping step)
        if (progress.detected_categories) {
            this.state.detectedCategories = progress.detected_categories
        }

        // Handle current sub-step (from llama_ocr / ai_batch_processing)
        if (progress.current_sub_step) {
            const currentStep = this.state.currentStep

            // Mark previous sub-step as completed if switching
            if (this.state.currentSubStep && this.state.currentSubStep !== progress.current_sub_step) {
                const stepSubSteps = this.state.stepSubSteps[currentStep] || []
                if (!stepSubSteps.includes(this.state.currentSubStep)) {
                    this.state.stepSubSteps = {
                        ...this.state.stepSubSteps,
                        [currentStep]: [...stepSubSteps, this.state.currentSubStep]
                    }
                }
            }
            this.state.currentSubStep = progress.current_sub_step
        }
    }

    /**
     * Get completed sub-steps for a specific step
     */
    getStepCompletedSubSteps(stepKey) {
        return this.state.stepSubSteps[stepKey] || []
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

                // Re-setup intersection observer for new pages
                setTimeout(() => this.setupIntersectionObserver(), 200);
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
     * Thumbnail click handler
     * - Normal click: Scroll to page only (no toggle)
     * - Ctrl/Cmd+Click: Toggle selection only (multi-select)
     */
    onThumbnailClick(page, event) {
        // Prevent default and stop propagation
        event.preventDefault();
        event.stopPropagation();

        // Ctrl/Cmd+Click: Toggle selection (multi-select mode)
        if (event.ctrlKey || event.metaKey) {
            this.togglePage(page.attachment_id);
            return;
        }

        // Normal click: Scroll to page + update active immediately
        this.state.activePageId = page.attachment_id; // Update immediately for visual feedback
        this.scrollToPage(page.attachment_id);
    }

    /**
     * Scroll to page in main view
     */
    scrollToPage(attachmentId) {
        const element = document.querySelector(`[data-page-id="${attachmentId}"]`);
        if (element) {
            // Set flag to prevent Intersection Observer from interfering
            this.isProgrammaticScroll = true;

            // Scroll to center of viewport
            element.scrollIntoView({
                behavior: 'smooth',
                block: 'center',
                inline: 'nearest'
            });

            // Clear flag after scroll completes (smooth scroll ~500ms)
            setTimeout(() => {
                this.isProgrammaticScroll = false;
                // Manually update active page after scroll
                this.state.activePageId = attachmentId;
            }, 600);
        }
    }

    /**
     * Scroll thumbnail into view in sidebar
     */
    scrollThumbnailIntoView(attachmentId) {
        const thumbnail = document.querySelector(`[data-thumbnail-id="${attachmentId}"]`);
        if (thumbnail) {
            thumbnail.scrollIntoView({
                behavior: 'smooth',
                block: 'center',
                inline: 'center'
            });
        }
    }

    /**
     * Setup Intersection Observer to auto-activate thumbnails
     * Activates thumbnail for page closest to viewport center
     */
    setupIntersectionObserver() {
        // Disconnect existing observer if any
        if (this.intersectionObserver) {
            this.intersectionObserver.disconnect();
        }

        // Create new observer
        this.intersectionObserver = new IntersectionObserver((entries) => {
            // Skip during programmatic scroll
            if (this.isProgrammaticScroll) {
                return;
            }

            // Find page closest to viewport center
            const viewportCenterY = window.innerHeight / 2;
            let closestDistance = Infinity;
            let closestPageId = null;

            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const rect = entry.target.getBoundingClientRect();
                    const pageCenterY = rect.top + rect.height / 2;
                    const distance = Math.abs(pageCenterY - viewportCenterY);

                    if (distance < closestDistance) {
                        closestDistance = distance;
                        closestPageId = parseInt(entry.target.dataset.pageId);
                    }
                }
            });

            // Update active page to the one closest to center
            if (closestPageId !== null && this.state.activePageId !== closestPageId) {
                this.state.activePageId = closestPageId;
                // Auto-scroll thumbnail into view
                this.scrollThumbnailIntoView(closestPageId);
            }
        }, {
            root: null, // Use viewport as root
            rootMargin: '50px'
        });

        // Observe all page items
        setTimeout(() => {
            const pageElements = document.querySelectorAll('.page-stack-item[data-page-id]');
            pageElements.forEach(el => {
                this.intersectionObserver.observe(el);
            });
        }, 100); // Small delay to ensure DOM is ready
    }

    /**
     * Get step configuration for progress stepper
     */
    getStepConfig() {
        return [
            { key: 'queue_pending', label: _t('Chuẩn bị tài nguyên'), number: 1 },
            { key: 'upload_validate', label: _t('Upload & Validate'), number: 2 },
            { key: 'category_mapping', label: _t('Category Mapping'), number: 3 },
            { key: 'llama_ocr', label: _t('Llama OCR'), number: 4 },
            { key: 'ai_batch_processing', label: _t('AI Processing'), number: 5 },
            { key: 'merge_validate', label: _t('Merge & Validate'), number: 6 },
        ];
    }

    /**
     * Get user-friendly label for category key based on document type
     */
    getCategoryLabel(categoryKey) {
        const LABELS_FORM_01 = {
            'metadata': 'Thông tin doanh nghiệp',
            'substance_usage': 'Bảng 1.1 - Sử dụng chất',
            'equipment_product': 'Bảng 1.2 - Thiết bị sản phẩm',
            'equipment_ownership': 'Bảng 1.3 - Sở hữu thiết bị',
            'collection_recycling': 'Bảng 1.4 - Thu gom tái chế',
        };
        const LABELS_FORM_02 = {
            'metadata': 'Thông tin doanh nghiệp',
            'quota_usage': 'Bảng 2.1 - Hạn ngạch',
            'equipment_product_report': 'Bảng 2.2 - Thiết bị sản phẩm',
            'equipment_ownership_report': 'Bảng 2.3 - Sở hữu thiết bị',
            'collection_recycling_report': 'Bảng 2.4 - Thu gom tái chế',
        };

        const labels = this.state.documentType === '02' ? LABELS_FORM_02 : LABELS_FORM_01;
        return labels[categoryKey] || categoryKey;
    }

    selectAll() {
        this.state.selectedPages = new Set(
            this.state.pages.map(page => page.attachment_id)
        );
    }

    deselectAll() {
        this.state.selectedPages.clear();
    }

    subscribe(job_id) {
        this.props.updateActionState({
            job_id: job_id
        })
        this.bus.addChannel(job_id)
        this.bus.subscribe('update_progress', this.update_progress.bind(this))
    }

    unsubscribe(job_id) {
        this.bus.deleteChannel(job_id)
        this.bus.unsubscribe('update_progress', this.update_progress.bind(this))
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
                this.state.jobUUID = result.uuid;
                this.state.jobState = 'pending';
                this.state.progress = 0;
                this.state.progressMessage = _t("Job created, waiting to start...");

                this.notification.add(
                    _t("Extraction job created. Processing..."),
                    { type: "success" }
                );

                this.subscribe(result.uuid)
                this.startJobPolling()
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
        if (!this.state.jobUUID) return;

        try {
            const response = await this.rpc("/robotia/get_my_extraction_jobs", {
                offset: 0,
                limit: 20  // Get recent jobs
            });
            const job = response.jobs.find(j => j.uuid === this.state.jobUUID);

            if (!job) {
                console.error("Job not found:", this.state.jobUUID);
                return;
            }

            // Update state using queue_state
            this.state.jobState = job.queue_state;
            this.state.errorMessage = job.error_message || "";
            this.state.mergedPdfUrl = job.merged_pdf_url

            // Handle job completion based on queue_state
            if (job.queue_state === 'done') {
                clearInterval(this.pollingInterval);
                this.pollingInterval = null;
                this.state.isProcessing = false;

                // Open the extraction form
                if (job.result_action_json) {
                    const action = JSON.parse(job.result_action_json);

                    this.props.updateActionState({
                        retry_from_step: null,
                        job_id: null,
                        progress: null
                    })

                    await this.action.doAction(action, {
                        additionalContext: {
                            'no_breadcrumbs': true
                        }
                    });
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
