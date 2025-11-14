/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { UploadArea } from "./upload_area";
import { StatisticsCard } from "./statistics_card";
import { RecentExtractions } from "./recent_extractions";


export class Dashboard extends Component {
    static template = "robotia_document_extractor.Dashboard";
    static components = { UploadArea, StatisticsCard, RecentExtractions };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this.state = useState({
            statistics: {
                registrations: 0,
                reports: 0
            },
            loading: true
        });

        onWillStart(async () => {
            await this.loadStatistics();
            this.state.loading = false;
        });
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

    onCardClick(docType) {
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

    async onExtractionComplete() {
        // Reload statistics after successful extraction
        await this.loadStatistics();
    }
}

registry.category("actions").add("document_extractor.dashboard", Dashboard);
