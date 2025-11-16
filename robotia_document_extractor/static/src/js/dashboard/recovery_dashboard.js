/** @odoo-module **/

import { Component, useState, onWillStart, useRef, useEffect } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadBundle } from "@web/core/assets";
import { rpc } from "@web/core/network/rpc";
import {
    CHART_COLORS,
    LINE_CHART_OPTIONS,
    BAR_CHART_OPTIONS,
    PIE_CHART_OPTIONS,
    formatNumber,
    getColorByIndex,
    hexToRgba,
} from "../utils/chart_utils";

/**
 * Recovery Dashboard Component
 * Displays analytics for collection, reuse, recycle, and destruction
 */
export class RecoveryDashboard extends Component {
    static template = "robotia_document_extractor.RecoveryDashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        // Chart refs
        this.trendChartRef = useRef("trendChart");
        this.pieChartRef = useRef("pieChart");
        this.reuseChartRef = useRef("reuseChart");
        this.recycleChartRef = useRef("recycleChart");

        // Chart instances
        this.trendChart = null;
        this.pieChart = null;
        this.reuseChart = null;
        this.recycleChart = null;

        // State
        this.state = useState({
            loading: true,
            error: null,
            info: {},
            kpiData: {
                totalCollected: 0,
                totalReused: 0,
                totalRecycled: 0,
                totalDestroyed: 0,
            },
            trendByYear: [],
            reuseBySubstance: [],
            recycleByTechnology: [],
            details: [],
            // Filters
            filters: {
                substance_id: null,
                organization_id: null,
                year_from: null,
                year_to: null,
            }
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
        }, () => [this.state.loading]);
    }

    /**
     * Load dashboard data from backend
     */
    async loadData() {
        try {
            this.state.loading = true;
            this.state.error = null;

            // Fetch recovery dashboard data via RPC controller
            const dashboardData = await rpc('/document_extractor/recovery_dashboard_data', {
                substance_id: this.state.filters.substance_id,
                organization_id: this.state.filters.organization_id,
                year_from: this.state.filters.year_from,
                year_to: this.state.filters.year_to,
            });

            // Check for errors in response
            if (dashboardData.error) {
                throw new Error(dashboardData.message || 'Failed to fetch dashboard data');
            }

            // Update info
            this.state.info = dashboardData.info || {};

            // Update KPI data
            this.state.kpiData = {
                totalCollected: dashboardData.kpis?.total_collected || 0,
                totalReused: dashboardData.kpis?.total_reused || 0,
                totalRecycled: dashboardData.kpis?.total_recycled || 0,
                totalDestroyed: dashboardData.kpis?.total_destroyed || 0,
            };

            // Update chart data
            this.state.trendByYear = dashboardData.charts?.trend_by_year || [];
            this.state.reuseBySubstance = dashboardData.charts?.reuse_by_substance || [];
            this.state.recycleByTechnology = dashboardData.charts?.recycle_by_technology || [];

            // Update details
            this.state.details = dashboardData.details || [];

            this.state.loading = false;
        } catch (error) {
            console.error('Error loading recovery dashboard data:', error);
            this.state.error = error.message || 'Failed to load dashboard data';
            this.state.loading = false;
        }
    }

    /**
     * Render all charts
     */
    renderCharts() {
        this.renderTrendChart();
        this.renderPieChart();
        this.renderReuseChart();
        this.renderRecycleChart();
    }

    /**
     * Render trend by year line chart
     */
    renderTrendChart() {
        if (!this.trendChartRef.el || this.state.trendByYear.length === 0) return;

        const ctx = this.trendChartRef.el.getContext('2d');

        if (this.trendChart) {
            this.trendChart.destroy();
        }

        const labels = this.state.trendByYear.map(d => d.year);
        const data = this.state.trendByYear.map(d => d.collected);

        this.trendChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Lượng thu gom (kg)',
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
                        text: 'Xu hướng thu gom theo năm',
                        font: { size: 14, weight: 'bold' }
                    }
                }
            }
        });
    }

    /**
     * Render collection structure pie chart
     */
    renderPieChart() {
        if (!this.pieChartRef.el) return;

        const ctx = this.pieChartRef.el.getContext('2d');

        if (this.pieChart) {
            this.pieChart.destroy();
        }

        const labels = ['Thu gom', 'Tái sử dụng', 'Tái chế', 'Tiêu hủy'];
        const data = [
            this.state.kpiData.totalCollected,
            this.state.kpiData.totalReused,
            this.state.kpiData.totalRecycled,
            this.state.kpiData.totalDestroyed
        ];
        const colors = [
            CHART_COLORS.primary,
            CHART_COLORS.success,
            CHART_COLORS.warning,
            CHART_COLORS.danger
        ];

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
                        text: 'Cơ cấu thu gom',
                        font: { size: 14, weight: 'bold' }
                    }
                }
            }
        });
    }

    /**
     * Render reuse by substance bar chart
     */
    renderReuseChart() {
        if (!this.reuseChartRef.el || this.state.reuseBySubstance.length === 0) return;

        const ctx = this.reuseChartRef.el.getContext('2d');

        if (this.reuseChart) {
            this.reuseChart.destroy();
        }

        const labels = this.state.reuseBySubstance.map(d => d.substance);
        const data = this.state.reuseBySubstance.map(d => d.reused);
        const colors = this.state.reuseBySubstance.map((_, i) => getColorByIndex(i));

        this.reuseChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Lượng tái sử dụng (kg)',
                    data: data,
                    backgroundColor: colors.map(c => hexToRgba(c, 0.7)),
                    borderColor: colors,
                    borderWidth: 1,
                }]
            },
            options: {
                ...BAR_CHART_OPTIONS,
                plugins: {
                    ...BAR_CHART_OPTIONS.plugins,
                    title: {
                        display: true,
                        text: 'Tái sử dụng theo chất',
                        font: { size: 14, weight: 'bold' }
                    }
                }
            }
        });
    }

    /**
     * Render recycle by technology bar chart
     */
    renderRecycleChart() {
        if (!this.recycleChartRef.el || this.state.recycleByTechnology.length === 0) return;

        const ctx = this.recycleChartRef.el.getContext('2d');

        if (this.recycleChart) {
            this.recycleChart.destroy();
        }

        const labels = this.state.recycleByTechnology.map(d => d.technology);
        const data = this.state.recycleByTechnology.map(d => d.recycled);
        const colors = this.state.recycleByTechnology.map((_, i) => getColorByIndex(i));

        this.recycleChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Lượng tái chế (kg)',
                    data: data,
                    backgroundColor: colors.map(c => hexToRgba(c, 0.7)),
                    borderColor: colors,
                    borderWidth: 1,
                }]
            },
            options: {
                ...BAR_CHART_OPTIONS,
                plugins: {
                    ...BAR_CHART_OPTIONS.plugins,
                    title: {
                        display: true,
                        text: 'Tái chế theo công nghệ',
                        font: { size: 14, weight: 'bold' }
                    }
                }
            }
        });
    }

    /**
     * Destroy all chart instances
     */
    destroyCharts() {
        if (this.trendChart) {
            this.trendChart.destroy();
            this.trendChart = null;
        }
        if (this.pieChart) {
            this.pieChart.destroy();
            this.pieChart = null;
        }
        if (this.reuseChart) {
            this.reuseChart.destroy();
            this.reuseChart = null;
        }
        if (this.recycleChart) {
            this.recycleChart.destroy();
            this.recycleChart = null;
        }
    }

    /**
     * Formatted values for display
     */
    formatNumber(value, decimals = 0) {
        return formatNumber(value, decimals);
    }
}

// Register the dashboard as a client action
registry.category("actions").add("document_extractor.recovery_dashboard", RecoveryDashboard);
