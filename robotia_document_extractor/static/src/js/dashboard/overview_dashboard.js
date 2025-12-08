/** @odoo-module **/

import { Component, useState, onWillStart, useRef, useEffect } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadBundle } from "@web/core/assets";
import { rpc } from "@web/core/network/rpc";
import {
    CHART_COLORS,
    CHART_COLOR_ARRAY,
    BAR_CHART_OPTIONS,
    formatNumber,
    formatCO2e,
    formatWeight,
    getColorByIndex,
} from "../utils/chart_utils";

/**
 * Overview Dashboard Component
 * Displays overall system analytics with KPIs, charts, and quick actions
 */
export class OverviewDashboard extends Component {
    static template = "robotia_document_extractor.OverviewDashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        // Chart refs
        this.yearChartRef = useRef("yearChart");
        this.substanceChartRef = useRef("substanceChart");

        // Chart instances
        this.yearChart = null;
        this.substanceChart = null;

        // State
        this.state = useState({
            loading: true,
            error: null,
            kpiData: {
                total_usage_kg: 0,
                total_co2e: 0,
                organization_count: 0,
                document_count: 0,
                total_docs: 0,
                form01_count: 0,
                form02_count: 0,
                status_counts: {
                    draft: 0,
                    validated: 0,
                    completed: 0
                }
            },
            trendByYear: [],
            topSubstances: [],
            activityTypes: [],
            recentActivity: []
        });

        // Load Chart.js and fetch data
        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            await this.loadData();
        });

        // Render charts after data is loaded
        useEffect(() => {
            if (!this.state.loading && !this.state.error) {
                this.renderCharts();
            }
            // Cleanup charts on unmount
            return () => {
                this.destroyCharts();
            };
        }, () => [this.state.loading, this.state.trendByYear, this.state.topSubstances]);
    }

    /**
     * Load dashboard data from backend
     */
    async loadData() {
        try {
            this.state.loading = true;
            this.state.error = null;

            const data = await rpc('/document_extractor/overview_dashboard_data');

            if (data.error) {
                throw new Error(data.message || 'Failed to load dashboard data');
            }

            // Update state with fetched data
            this.state.kpiData = data.kpis;
            this.state.trendByYear = data.charts.trend_by_year || [];
            this.state.topSubstances = data.charts.top_substances || [];
            this.state.activityTypes = data.charts.by_activity_type || [];
            this.state.recentActivity = data.recent_activity || [];

            this.state.loading = false;
        } catch (error) {
            console.error('Error loading overview dashboard data:', error);
            this.state.error = error.message || 'An error occurred while loading the dashboard';
            this.state.loading = false;
        }
    }

    /**
     * Render all charts
     */
    renderCharts() {
        this.renderYearChart();
        this.renderSubstanceChart();
    }

    /**
     * Render Usage by Year Chart (Vertical Bar)
     */
    renderYearChart() {
        const canvas = this.yearChartRef.el;
        if (!canvas) return;

        const ctx = canvas.getContext('2d');

        // Destroy existing chart
        if (this.yearChart) {
            this.yearChart.destroy();
        }

        // Prepare data
        const years = this.state.trendByYear.map(d => d.year);
        const totalKg = this.state.trendByYear.map(d => d.total_kg || 0);

        // Create chart
        this.yearChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: years,
                datasets: [{
                    label: 'Tổng sử dụng (kg)',
                    data: totalKg,
                    backgroundColor: CHART_COLORS.primary,
                    borderColor: CHART_COLORS.primary,
                    borderWidth: 1
                }]
            },
            options: {
                ...BAR_CHART_OPTIONS,
                plugins: {
                    ...BAR_CHART_OPTIONS.plugins,
                    title: {
                        display: false
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return `Sử dụng: ${formatWeight(context.parsed.y)}`;
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'Khối lượng (kg)'
                        },
                        ticks: {
                            callback: function(value) {
                                return formatNumber(value, 0) + ' kg';
                            }
                        }
                    },
                    x: {
                        title: {
                            display: true,
                            text: 'Năm'
                        }
                    }
                }
            }
        });
    }

    /**
     * Render Top Substances Chart (Horizontal Bar)
     */
    renderSubstanceChart() {
        const canvas = this.substanceChartRef.el;
        if (!canvas) return;

        const ctx = canvas.getContext('2d');

        // Destroy existing chart
        if (this.substanceChart) {
            this.substanceChart.destroy();
        }

        // Prepare data - take top 5
        const substances = this.state.topSubstances;
        const labels = substances.map(s => s.name);
        const values = substances.map(s => s.value || 0);

        // Create chart
        this.substanceChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'CO₂ (tCO₂)',
                    data: values,
                    backgroundColor: '#10b981', // emerald-500
                    borderColor: '#10b981',
                    borderWidth: 1
                }]
            },
            options: {
                indexAxis: 'y', // Horizontal bar
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return `CO₂: ${formatNumber(context.parsed.x, 0)} tCO₂`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'Lượng CO₂ (tCO₂)'
                        },
                        ticks: {
                            callback: function(value) {
                                return formatNumber(value, 0) + ' tCO₂';
                            }
                        }
                    }
                }
            }
        });
    }

    /**
     * Destroy all charts
     */
    destroyCharts() {
        if (this.yearChart) {
            this.yearChart.destroy();
            this.yearChart = null;
        }
        if (this.substanceChart) {
            this.substanceChart.destroy();
            this.substanceChart = null;
        }
    }

    /**
     * Format number helper
     */
    formatNumber(value, decimals = 0) {
        return formatNumber(value, decimals);
    }

    /**
     * Format weight helper
     */
    formatWeight(value) {
        return formatWeight(value);
    }

    /**
     * Format CO2e helper
     */
    formatCO2e(value) {
        return formatCO2e(value);
    }

    /**
     * Quick Action: Navigate to Upload (Main Dashboard)
     */
    onUploadClick() {
        this.action.doAction({
            type: 'ir.actions.client',
            tag: 'document_extractor.dashboard',
            target: 'current'
        });
    }

    /**
     * Quick Action: Navigate to Documents List
     */
    onDocumentsClick() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'All Documents',
            res_model: 'document.extraction',
            views: [[false, 'list'], [false, 'form']],
            target: 'current'
        });
    }

    /**
     * Quick Action: Navigate to HFC Dashboard (Reports)
     */
    onReportsClick() {
        this.action.doAction('robotia_document_extractor.action_hfc_dashboard');
    }

    /**
     * Quick Action: Navigate to AI Chat
     */
    onAIChatClick() {
        this.action.doAction({
            type: 'ir.actions.client',
            tag: 'document_extractor.chatbot',
            target: 'current'
        });
    }

    /**
     * Click handler for status items (Draft/Validated/Completed)
     * Opens list view with filter for the selected status
     */
    onStatusClick(status) {
        // Use the existing action and add domain filter
        this.action.doAction('robotia_document_extractor.action_document_extraction_all', {
            additionalContext: {
                search_default_filter_draft: status === 'draft' ? 1 : 0,
                search_default_filter_validated: status === 'validated' ? 1 : 0,
                search_default_filter_completed: status === 'completed' ? 1 : 0,
            }
        });
    }

    /**
     * Click handler for activity items
     * Opens document form if exists, otherwise opens log record form
     */
    onActivityClick(activity) {
        if (activity.document_id) {
            // Has document: open document form
            this.action.doAction('robotia_document_extractor.action_document_extraction_all', {
                viewType: 'form',
                props: {
                    resId: activity.document_id
                }
            });
        } else if (activity.log_id) {
            // No document: open log record form
            this.action.doAction('robotia_document_extractor.action_google_drive_extraction_log', {
                viewType: 'form',
                props: {
                    resId: activity.log_id
                }
            });
        } else {
            console.warn('No document or log ID available for this activity:', activity);
        }
    }
}

// Register the dashboard as a client action
registry.category("actions").add("document_extractor.overview_dashboard", OverviewDashboard);
