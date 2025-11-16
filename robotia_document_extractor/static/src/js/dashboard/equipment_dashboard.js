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
    formatCO2e,
    getColorByIndex,
    hexToRgba,
} from "../utils/chart_utils";

/**
 * Equipment Dashboard Component
 * Displays analytics for a specific equipment type
 */
export class EquipmentDashboard extends Component {
    static template = "robotia_document_extractor.EquipmentDashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        // Chart refs
        this.trendChartRef = useRef("trendChart");
        this.pieChartRef = useRef("pieChart");
        this.capacityChartRef = useRef("capacityChart");
        this.refillChartRef = useRef("refillChart");

        // Chart instances
        this.trendChart = null;
        this.pieChart = null;
        this.capacityChart = null;
        this.refillChart = null;

        // Get equipment_type_id from params (priority), state (from URL), or context
        this.equipmentTypeId = this.props.action?.params?.equipment_type_id ||
                              this.props.action?.state?.equipment_type_id ||
                              this.props.action?.context?.default_equipment_type_id ||
                              null;
        this.equipmentTypeName = this.props.action?.params?.equipment_type_name ||
                                this.props.action?.context?.default_equipment_type_name ||
                                '';

        // State
        this.state = useState({
            loading: true,
            error: null,
            equipmentTypeId: this.equipmentTypeId,
            equipmentTypeName: this.equipmentTypeName,
            equipmentInfo: {},
            kpiData: {
                totalCount: 0,
                totalKg: 0,
                totalCO2e: 0,
                avgRefillFrequency: 0,
            },
            trendByYear: [],
            bySubstance: [],
            byCompany: [],
            details: [],
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

            if (!this.state.equipmentTypeId) {
                throw new Error('Equipment Type ID is required');
            }

            // Fetch equipment dashboard data via RPC controller
            const dashboardData = await rpc('/document_extractor/equipment_dashboard_data', {
                equipment_type_id: this.state.equipmentTypeId
            });

            // Check for errors in response
            if (dashboardData.error) {
                throw new Error(dashboardData.message || 'Failed to fetch dashboard data');
            }

            // Update equipment info
            this.state.equipmentInfo = dashboardData.equipment_info || {};
            this.state.equipmentTypeName = this.state.equipmentInfo.name || this.state.equipmentTypeName;

            // Update KPI data
            this.state.kpiData = {
                totalCount: dashboardData.kpis?.total_count || 0,
                totalKg: dashboardData.kpis?.total_kg || 0,
                totalCO2e: dashboardData.kpis?.total_co2e || 0,
                avgRefillFrequency: dashboardData.kpis?.avg_refill_frequency || 0,
            };

            // Update chart data
            this.state.trendByYear = dashboardData.charts?.trend_by_year || [];
            this.state.bySubstance = dashboardData.charts?.by_substance || [];
            this.state.byCompany = dashboardData.charts?.by_company || [];

            // Update details
            this.state.details = dashboardData.details || [];

            // Update URL state to persist equipment_type_id (for page refresh)
            if (this.equipmentTypeId && this.props.updateActionState) {
                this.props.updateActionState({
                    equipment_type_id: this.equipmentTypeId
                });
            }

            this.state.loading = false;
        } catch (error) {
            console.error('Error loading equipment dashboard data:', error);
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
        this.renderCapacityChart();
        this.renderRefillChart();
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
        const data = this.state.trendByYear.map(d => d.count);

        this.trendChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Số lượng thiết bị',
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
                        text: 'Xu hướng thiết bị theo năm',
                        font: { size: 14, weight: 'bold' }
                    }
                }
            }
        });
    }

    /**
     * Render substance distribution pie chart
     */
    renderPieChart() {
        if (!this.pieChartRef.el || this.state.bySubstance.length === 0) return;

        const ctx = this.pieChartRef.el.getContext('2d');

        if (this.pieChart) {
            this.pieChart.destroy();
        }

        const labels = this.state.bySubstance.map(d => d.substance);
        const data = this.state.bySubstance.map(d => d.total_kg);
        const colors = this.state.bySubstance.map((_, i) => getColorByIndex(i));

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
                        text: 'Phân bổ theo chất chứa trong thiết bị',
                        font: { size: 14, weight: 'bold' }
                    }
                }
            }
        });
    }

    /**
     * Render capacity by company bar chart
     */
    renderCapacityChart() {
        if (!this.capacityChartRef.el || this.state.byCompany.length === 0) return;

        const ctx = this.capacityChartRef.el.getContext('2d');

        if (this.capacityChart) {
            this.capacityChart.destroy();
        }

        // Sort by capacity and take top 10
        const sorted = [...this.state.byCompany].sort((a, b) => b.capacity - a.capacity).slice(0, 10);
        const labels = sorted.map(d => d.company);
        const data = sorted.map(d => d.capacity);
        const colors = sorted.map((_, i) => getColorByIndex(i));

        this.capacityChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Tổng công suất (kW)',
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
                        text: 'Tổng công suất theo doanh nghiệp',
                        font: { size: 14, weight: 'bold' }
                    }
                }
            }
        });
    }

    /**
     * Render refill trend (simplified as line chart)
     */
    renderRefillChart() {
        if (!this.refillChartRef.el || this.state.trendByYear.length === 0) return;

        const ctx = this.refillChartRef.el.getContext('2d');

        if (this.refillChart) {
            this.refillChart.destroy();
        }

        const labels = this.state.trendByYear.map(d => d.year);
        const data = this.state.trendByYear.map(d => d.count);

        this.refillChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Số thiết bị',
                    data: data,
                    borderColor: CHART_COLORS.success,
                    backgroundColor: hexToRgba(CHART_COLORS.success, 0.1),
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4,
                }]
            },
            options: {
                ...LINE_CHART_OPTIONS,
                plugins: {
                    ...LINE_CHART_OPTIONS.plugins,
                    title: {
                        display: true,
                        text: 'Ước tính rò rỉ – Refill theo năm',
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
        if (this.capacityChart) {
            this.capacityChart.destroy();
            this.capacityChart = null;
        }
        if (this.refillChart) {
            this.refillChart.destroy();
            this.refillChart = null;
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
registry.category("actions").add("document_extractor.equipment_dashboard", EquipmentDashboard);
