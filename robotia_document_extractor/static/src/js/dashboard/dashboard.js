/** @odoo-module **/

import { Component, useState, onWillStart, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { UploadArea } from "./upload_area";
import { StatisticsCard } from "./statistics_card";
import { RecentExtractions } from "./recent_extractions";
import { rpc } from "@web/core/network/rpc";


export class Dashboard extends Component {
    static template = "robotia_document_extractor.Dashboard";
    static components = { UploadArea, StatisticsCard, RecentExtractions };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.rpc = rpc
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.bus = useService("bus_service");

        this.state = useState({
            statistics: {
                registrations: 0,
                reports: 0
            },
            loading: true,
            uploading: false,
            jobs: [],  // Extraction jobs list
            jobsOffset: 0,  // Pagination offset
            jobsHasMore: false,  // Whether there are more jobs
            subscribeCallbacks: {}
        });

        onWillStart(async () => {
            await this.loadStatistics();
            await this.loadJobs();
            this.state.loading = false;
        });

        onWillUnmount(() => {
            for(let job of this.state.jobs) {
                this.ubsubscribe(job)
            }
        });
    }

    subscribe(job) {

        if (!this.state.subscribeCallbacks[job.uuid]) {
            this.bus.addChannel(job.uuid)
            const updateProgress = (progress) => {
                job.progress = progress.progress
                job.progress_message = progress.message
                job.current_step = progress.step
            }
            this.state.subscribeCallbacks[job.uuid] = updateProgress
            this.bus.subscribe('update_progress', updateProgress)
        }

    }

    getStepString(step) {
        return {
            upload_validate: {
                message: _t('Uploaded'),
                class: "badge bg-primary text-white"
            },
            category_mapping: {
                message: _t('Categorizing'),
                class: "badge bg-info text-white"
            },
            llama_ocr: {
                message: _t('OCR'),
                class: "badge bg-info text-white opacity-75"
            },
            ai_batch_processing: {
                message: _t('AI processing'),
                class: "badge bg-success text-white opacity-75"
            },
            merge_validate: {
                message: _t('Validating'),
                class: "badge bg-success text-white"
            },
            completed: {
                message: _t('Complete'),
                class: "badge bg-success text-white fw-bold"
            },
        }[step]
    }

    ubsubscribe(job) {
        const cb = this.state.subscribeCallbacks[job.uuid]
        if (cb) {
            this.bus.deleteChannel(job.uuid)
            this.bus.unsubscribe('update_progress', cb)
        }
    }

    async loadStatistics() {
        try {
            const [registrationCount, reportCount] = await Promise.all([
                this.orm.searchCount("document.extraction", [["document_type", "=", "01"]]),
                this.orm.searchCount("document.extraction", [["document_type", "=", "02"]])
            ]);

            this.state.statistics.registrations = registrationCount;
            this.state.statistics.reports = reportCount;
        } catch (error) {
            console.error("Failed to load statistics:", error);
        }
    }

    async loadJobs() {
        try {
            const response = await this.rpc("/robotia/get_my_extraction_jobs", {
                offset: 0,
                limit: 10
            });
            this.state.jobs = response.jobs || [];
            this.state.jobsOffset = 0;
            this.state.jobsHasMore = response.has_more || false;

            // Subscribe to bus for real-time updates
            this.subscribeToJobs();
        } catch (error) {
            console.error("Failed to load jobs:", error);
        }
    }

    async loadMoreJobs() {
        try {
            const newOffset = this.state.jobsOffset + 10;
            const response = await this.rpc("/robotia/get_my_extraction_jobs", {
                offset: newOffset,
                limit: 10
            });
            // Append new jobs to existing list
            this.state.jobs = [...this.state.jobs, ...(response.jobs || [])];
            this.state.jobsOffset = newOffset;
            this.state.jobsHasMore = response.has_more || false;

            // Subscribe to new jobs
            this.subscribeToJobs();
        } catch (error) {
            console.error("Failed to load more jobs:", error);
        }
    }

    subscribeToJobs() {
        // Subscribe to bus for all processing jobs
        const processingJobs = this.state.jobs.filter(job =>
            job.extraction_state === 'processing' ||
            job.extraction_state === 'pending' ||
            job.queue_state === 'started'
        );
        // Subscribe to each processing job's UUID
        for (const job of processingJobs) {
            this.subscribe(job)
        }
    }

    formatDate(dateString) {
        // Format datetime with timezone handling (same as recent_extractions.js)
        if (!dateString) return '';
        const date = new Date(dateString + 'Z');  // Force UTC

        return luxon.DateTime.fromJSDate(date, {
            zone: 'utc'
        }).setZone('local').toFormat('dd/MM/yyyy HH:mm')
    }

    async onJobClick(job) {
        // CRITICAL: Use extraction_state as primary source of truth
        // queue_state is secondary (reflects job runner status)

        // Case 1: Extraction completed successfully → Open extraction form
        // Check extraction_state='done' (primary business logic)
        if (job.extraction_state === 'done' && job.result_action_json) {
            try {
                const action = JSON.parse(job.result_action_json);
                await this.action.doAction(action);
            } catch (error) {
                console.error("Failed to parse job action:", error);
                this.notification.add("Error opening result", { type: "danger" });
            }
            return;
        }

        // Case 2: Extraction failed → Show error dialog
        // Check extraction_state='error' (primary) OR queue_state='failed' (fallback)
        if (job.extraction_state === 'error' || job.queue_state === 'failed') {
            this.showErrorDialog(job);
            return;
        }

        // Case 3: Extraction processing → Open progress view
        // Check extraction_state='processing' (primary) OR queue_state='started' (fallback)
        if (job.extraction_state === 'processing' || job.queue_state === 'started') {
            this.openProgressView(job)
            return;
        }

        // Case 4: Other states (pending, enqueued, cancelled) → Show info notification
        // Use extraction_state if available, fallback to queue_state
        const state = job.extraction_state || job.queue_state;
        const stateLabels = {
            'pending': 'Queued',
            'enqueued': 'Queued',
            'cancelled': 'Cancelled'
        };
        this.notification.add(
            `Job is ${stateLabels[state] || state}`,
            { type: 'info' }
        );
    }

    async showErrorDialog(job) {
        // Open queue.job form in dialog/popup mode using custom extraction dialog form
        // This form shows: Last Step + Error + Action Buttons (Requeue, Set to Done, Cancel)
        await this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'queue.job',
            res_id: job.queue_job_id,
            views: [[false, 'form']],
            target: 'new',  // Open in dialog/popup
            context: {
                'form_view_ref': 'robotia_document_extractor.view_queue_job_extraction_dialog_form'
            }
        });
    }

    async openProgressView(job) {
        // Open ExtractionPageSelector in progress-only mode
        await this.action.doAction({
            type: 'ir.actions.client',
            tag: 'robotia_document_extractor.page_selector',
            params: {
                job_id: job.uuid,
                document_type: job.document_type,
                merged_pdf_url: job.merged_pdf_url || null,  // PDF preview URL
                retry_from_step: job.current_step || null,  // Initialize progress stepper at current step
                progress: job.progress
            },
            target: 'current',
        });
    }

    onCardClick(docType) {
        // Don't allow navigation while uploading
        if (this.state.uploading) {
            return;
        }

        const domain = [['document_type', '=', docType]];
        const name = docType === '01' ? 'Registrations (Form 01)' : 'Reports (Form 02)';

        this.action.doAction({
            type: 'ir.actions.act_window',
            name: name,
            res_model: 'document.extraction',
            views: [[false, 'list'], [false, 'form']],
            domain: domain,
            target: 'current'
        });
    }

    onUploadStart() {
        this.state.uploading = true;
    }

    onUploadEnd() {
        this.state.uploading = false;
    }

    async onExtractionComplete() {
        // Reload statistics after successful extraction
        await this.loadStatistics();
        await this.loadJobs();
    }
}

registry.category("actions").add("document_extractor.dashboard", Dashboard);
