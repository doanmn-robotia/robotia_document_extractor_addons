/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";


export class RecentExtractions extends Component {
    static template = "robotia_document_extractor.RecentExtractions";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this.state = useState({
            recentDocuments: [],
            loading: true
        });

        onWillStart(async () => {
            await this.loadRecentDocuments();
            this.state.loading = false;
        });
    }

    async loadRecentDocuments() {
        try {
            const documents = await this.orm.searchRead(
                "document.extraction",
                [],
                ["name", "document_type", "organization_id", "year", "extraction_date", "state"],
                {
                    limit: 10,
                    order: "extraction_date desc"
                }
            );

            this.state.recentDocuments = documents;
        } catch (error) {
            console.error("Failed to load recent documents:", error);
        }
    }

    openDocument(documentId) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'document.extraction',
            res_id: documentId,
            views: [[false, 'form']],
            target: 'current'
        });
    }

    getDocumentTypeLabel(docType) {
        return docType === '01' ? 'Form 01' : 'Form 02';
    }

    getStateBadgeClass(state) {
        const badges = {
            'draft': 'badge bg-info',
            'validated': 'badge bg-warning',
            'completed': 'badge bg-success'
        };
        return badges[state] || 'badge bg-secondary';
    }

    getStateLabel(state) {
        const labels = {
            'draft': _t('Draft'),
            'validated': _t('Validated'),
            'completed': _t('Completed')
        };
        return labels[state] || state;
    }

    formatDate(dateString) {
        if (!dateString) return '';
        const date = new Date(dateString);
        return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
    }
}
