/** @odoo-module **/

import { Component, useState, onWillStart, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
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
        });

        onWillStart(async () => {
            await this.loadStatistics();
            await this.loadJobs();
            this.state.loading = false;
        });

        // onMounted(() => {
        //     // Poll jobs every 5 seconds
        //     this.jobPolling = setInterval(() => this.loadJobs(), 5000);
        // });

        // onWillUnmount(() => {
        //     if (this.jobPolling) {
        //         clearInterval(this.jobPolling);
        //     }
        // });
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
        } catch (error) {
            console.error("Failed to load more jobs:", error);
        }
    }

    async onJobClick(job) {
        // Handle based on queue_state (not extraction.job state)
        if (job.queue_state === 'done' && job.result_action_json) {
            // Open result form
            try {
                const action = JSON.parse(job.result_action_json);
                await this.action.doAction(action);
            } catch (error) {
                console.error("Failed to parse job action:", error);
                this.notification.add("Error opening result", { type: "danger" });
            }
        } else if (job.queue_state === 'failed') {
            // Show error dialog
            this.notification.add(
                job.error_message || 'Extraction failed',
                {
                    title: 'Extraction Error',
                    type: 'danger',
                    sticky: true,
                }
            );
        } else if (job.queue_state === 'started') {
            // In progress - show notification
            this.notification.add(
                `${job.progress_message || 'Processing'} (${job.progress}%)`,
                { type: 'info' }
            );
        } else {
            // pending, enqueued, cancelled
            const stateLabels = {
                'pending': 'Queued',
                'enqueued': 'Queued',
                'cancelled': 'Cancelled'
            };
            this.notification.add(
                `Job is ${stateLabels[job.queue_state] || job.queue_state}`,
                { type: 'info' }
            );
        }
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
