/** @odoo-module **/

import { Component, useState, onWillStart, useRef, useEffect } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadBundle } from "@web/core/assets";
import { rpc } from "@web/core/network/rpc";
import {
    CHART_COLORS,
    CHART_COLOR_ARRAY,
    LINE_CHART_OPTIONS,
    BAR_CHART_OPTIONS,
    PIE_CHART_OPTIONS,
    formatNumber,
    formatCO2e,
    formatWeight,
    getColorByIndex,
    hexToRgba,
} from "../utils/chart_utils";

/**
 * Substance Dashboard Component
 * Displays analytics for a specific controlled substance
 */
export class SubstanceDashboard extends Component {
    static template = "robotia_document_extractor.SubstanceDashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        // Chart refs
        this.lineChartRef = useRef("lineChart");
        this.barChartRef = useRef("barChart");
        this.pieChartRef = useRef("pieChart");

        // Chart instances
        this.lineChart = null;
        this.barChart = null;
        this.pieChart = null;

        // Get substance_id from params (priority), state (from URL), or context
        this.substanceId = this.props.action?.params?.substance_id ||
                          this.props.action?.state?.substance_id ||
                          this.props.action?.context?.default_substance_id ||
                          null;
        this.substanceName = this.props.action?.params?.substance_name ||
                            this.props.action?.context?.default_substance_name ||
                            '';

        // State
        this.state = useState({
            loading: true,
            error: null,
            substanceId: this.substanceId,
            substanceName: this.substanceName,
            substanceInfo: {},
            kpiData: {
                totalUsageKg: 0,
                totalCO2e: 0,
                organizationCount: 0,
                documentCount: 0,
            },
            trendData: [],
            topCompaniesData: [],
            activityTypeData: [],  // Changed: was documentTypeData
            quotaComparisonData: [],  // Added: quota allocated vs used
            detailRecords: [],
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
        }, () => [this.state.loading, this.state.trendData, this.state.topCompaniesData, this.state.documentTypeData]);
    }

    /**
     * Load dashboard data from backend
     */
    async loadData() {
        try {
            this.state.loading = true;
            this.state.error = null;

            if (!this.state.substanceId) {
                throw new Error('Substance ID is required');
            }

            // Fetch substance info
            const substances = await this.orm.searchRead(
                'controlled.substance',
                [['id', '=', this.state.substanceId]],
                ['name', 'code', 'formula', 'cas_number', 'gwp']
            );

            if (substances.length === 0) {
                throw new Error('Substance not found');
            }

            this.state.substanceInfo = substances[0];
            this.state.substanceName = this.state.substanceInfo.name;

            // Fetch aggregated dashboard data via RPC controller
            const dashboardData = await rpc('/document_extractor/substance_dashboard_data', {
                substance_id: this.state.substanceId
            });

            // Check for errors in response
            if (dashboardData.error) {
                throw new Error(dashboardData.message || 'Failed to fetch dashboard data');
            }

            // Update KPI data
            this.state.kpiData = {
                totalUsageKg: dashboardData.kpis?.total_usage_kg || 0,
                totalCO2e: dashboardData.kpis?.total_co2e || 0,
                organizationCount: dashboardData.kpis?.organization_count || 0,
                documentCount: dashboardData.kpis?.document_count || 0,
            };

            // Update chart data
            this.state.trendData = dashboardData.charts?.trend_by_year || [];
            this.state.topCompaniesData = dashboardData.charts?.top_companies || [];
            this.state.activityTypeData = dashboardData.charts?.by_activity_type || [];  // Changed: was by_document_type
            this.state.quotaComparisonData = dashboardData.charts?.quota_comparison || [];  // Added: quota data

            // Update detail records
            this.state.detailRecords = dashboardData.details?.organizations || [];

            // Update URL state to persist substance_id (for page refresh)
            if (this.substanceId && this.props.updateActionState) {
                this.props.updateActionState({
                    substance_id: this.substanceId
                });
            }

            this.state.loading = false;
        } catch (error) {
            console.error('Error loading substance dashboard data:', error);
            this.state.error = error.message || 'Failed to load dashboard data';
            this.state.loading = false;
        }
    }

    /**
     * Render all charts
     */
    renderCharts() {
        this.renderLineChart();
        this.renderBarChart();
        this.renderPieChart();
    }

    /**
     * Render yearly trend line chart
     */
    renderLineChart() {
        if (!this.lineChartRef.el || this.state.trendData.length === 0) return;

        const ctx = this.lineChartRef.el.getContext('2d');

        // Destroy existing chart
        if (this.lineChart) {
            this.lineChart.destroy();
        }

        const labels = this.state.trendData.map(d => d.year);
        const data = this.state.trendData.map(d => d.total_kg);

        this.lineChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: `${this.state.substanceName} (kg)`,
                    data: data,
                    borderColor: CHART_COLORS.primary,
                    backgroundColor: hexToRgba(CHART_COLORS.primary, 0.1),
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 4,
                    pointHoverRadius: 6,
                }]
            },
            options: {
                ...LINE_CHART_OPTIONS,
                plugins: {
                    ...LINE_CHART_OPTIONS.plugins,
                    title: {
                        display: true,
                        text: 'Xu hướng sử dụng theo năm',
                        font: {
                            size: 14,
                            weight: 'bold'
                        }
                    }
                }
            }
        });
    }

    /**
     * Render quota comparison bar chart (Allocated vs Used)
     * Shows top 10 organizations by allocated quota
     */
    renderBarChart() {
        if (!this.barChartRef.el || this.state.quotaComparisonData.length === 0) return;

        const ctx = this.barChartRef.el.getContext('2d');

        // Destroy existing chart
        if (this.barChart) {
            this.barChart.destroy();
        }

        const labels = this.state.quotaComparisonData.map(d => d.organization_name);
        const allocatedData = this.state.quotaComparisonData.map(d => d.allocated_quota_kg);
        const usedData = this.state.quotaComparisonData.map(d => d.used_quota_kg);

        this.barChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Hạn ngạch được cấp',
                        data: allocatedData,
                        backgroundColor: hexToRgba(CHART_COLORS.primary, 0.7),
                        borderColor: CHART_COLORS.primary,
                        borderWidth: 2,
                    },
                    {
                        label: 'Hạn ngạch đã sử dụng',
                        data: usedData,
                        backgroundColor: hexToRgba(CHART_COLORS.success, 0.7),
                        borderColor: CHART_COLORS.success,
                        borderWidth: 2,
                    }
                ]
            },
            options: {
                ...BAR_CHART_OPTIONS,
                plugins: {
                    ...BAR_CHART_OPTIONS.plugins,
                    title: {
                        display: true,
                        text: `Hạn ngạch ${this.state.substanceName}: Được cấp vs Đã sử dụng`,
                        font: {
                            size: 14,
                            weight: 'bold'
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const label = context.dataset.label || '';
                                const value = formatWeight(context.parsed.y);
                                return `${label}: ${value}`;
                            },
                            afterLabel: function(context) {
                                // Show utilization rate for "used" dataset
                                if (context.datasetIndex === 1) {
                                    const index = context.dataIndex;
                                    const allocated = allocatedData[index];
                                    const used = usedData[index];
                                    const rate = allocated > 0 ? (used / allocated * 100).toFixed(1) : 0;
                                    return `Tỷ lệ sử dụng: ${rate}%`;
                                }
                                return '';
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
                        }
                    },
                    x: {
                        ticks: {
                            maxRotation: 45,
                            minRotation: 45
                        }
                    }
                },
                onClick: (_event, elements) => {
                    if (elements.length > 0) {
                        const index = elements[0].index;
                        const record = this.state.quotaComparisonData[index];
                        this.viewOrganization(record.organization_id);
                    }
                }
            }
        });
    }

    /**
     * Render activity type pie chart
     * Shows distribution by activity: Production, Import, Export, Collection, Reuse, Recycle, Disposal
     */
    renderPieChart() {
        if (!this.pieChartRef.el || this.state.activityTypeData.length === 0) return;

        const ctx = this.pieChartRef.el.getContext('2d');

        // Destroy existing chart
        if (this.pieChart) {
            this.pieChart.destroy();
        }

        const labels = this.state.activityTypeData.map(d => d.activity_label);
        const data = this.state.activityTypeData.map(d => d.total_kg);

        // Different colors for different activity types
        const colors = this.state.activityTypeData.map((_, index) => getColorByIndex(index));

        this.pieChart = new Chart(ctx, {
            type: 'pie',
            data: {
                labels: labels,
                datasets: [{
                    data: data,
                    backgroundColor: colors.map(c => hexToRgba(c, 0.7)),
                    borderColor: colors,
                    borderWidth: 2,
                }]
            },
            options: {
                ...PIE_CHART_OPTIONS,
                plugins: {
                    ...PIE_CHART_OPTIONS.plugins,
                    title: {
                        display: true,
                        text: 'Phân bổ theo loại hoạt động',
                        font: {
                            size: 14,
                            weight: 'bold'
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const label = context.label || '';
                                const value = formatWeight(context.parsed);
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const percentage = ((context.parsed / total) * 100).toFixed(1);
                                return `${label}: ${value} (${percentage}%)`;
                            }
                        }
                    }
                }
            }
        });
    }

    /**
     * Destroy all chart instances
     */
    destroyCharts() {
        if (this.lineChart) {
            this.lineChart.destroy();
            this.lineChart = null;
        }
        if (this.barChart) {
            this.barChart.destroy();
            this.barChart = null;
        }
        if (this.pieChart) {
            this.pieChart.destroy();
            this.pieChart = null;
        }
    }

    /**
     * View organization details (navigate to custom organization form view)
     */
    viewOrganization(partnerId) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'res.partner',
            res_id: partnerId,
            views: [[false, 'form']],
            target: 'current',
            context: {
                'form_view_ref': 'robotia_document_extractor.view_partner_organization_form',
                'tree_view_ref': 'robotia_document_extractor.view_partner_organization_list',
            },
        });
    }

    /**
     * View all documents for this substance
     */
    viewAllDocuments() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: `Tài liệu - ${this.state.substanceName}`,
            res_model: 'document.extraction',
            views: [[false, 'list'], [false, 'form']],
            domain: [
                '|',
                ['substance_usage_ids.substance_name', 'ilike', this.state.substanceName],
                ['quota_usage_ids.substance_name', 'ilike', this.state.substanceName]
            ],
            target: 'current',
        });
    }

    /**
     * Formatted values for display
     */
    get formattedTotalUsage() {
        return formatWeight(this.state.kpiData.totalUsageKg);
    }

    get formattedTotalCO2e() {
        return formatCO2e(this.state.kpiData.totalCO2e);
    }

    get formattedOrgCount() {
        return formatNumber(this.state.kpiData.organizationCount, 0);
    }

    get formattedDocCount() {
        return formatNumber(this.state.kpiData.documentCount, 0);
    }

    formatNumber(value) {
        return formatNumber(value)
    }

}

// Register the dashboard as a client action
registry.category("actions").add("document_extractor.substance_dashboard", SubstanceDashboard);
