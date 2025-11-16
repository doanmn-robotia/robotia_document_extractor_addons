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
    formatNumber,
    formatCO2e,
    formatWeight,
    getColorByIndex,
    hexToRgba,
} from "../utils/chart_utils";

/**
 * Company Dashboard Component
 * Displays analytics for a specific organization with 6 tabs
 */
export class CompanyDashboard extends Component {
    static template = "robotia_document_extractor.CompanyDashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        // Chart refs
        this.trendChartRef = useRef("trendChart");
        this.quotaChartRef = useRef("quotaChart");

        // Chart instances
        this.trendChart = null;
        this.quotaChart = null;

        // Get organization_id from params (priority), state (from URL), or context
        this.organizationId = this.props.action?.params?.organization_id ||
                             this.props.action?.state?.organization_id ||
                             this.props.action?.context?.default_organization_id ||
                             null;
        this.organizationName = this.props.action?.params?.organization_name ||
                               this.props.action?.context?.default_organization_name ||
                               '';

        // State
        this.state = useState({
            loading: true,
            error: null,
            organizationId: this.organizationId,
            organizationName: this.organizationName,
            companyInfo: {},
            kpiData: {
                totalSubstances: 0,
                totalKg: 0,
                totalCO2e: 0,
                recoveryRate: 0,
            },
            trendData: {},
            quotaData: [],
            activeTab: 'table_1_1',
            tabData: {
                table_1_1: [],
                table_1_2: [],
                table_1_3: [],
                table_2_1: [],
                table_2_4: [],
                ocr_history: [],
            },
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
        }, () => [this.state.loading, this.state.trendData, this.state.quotaData]);
    }

    /**
     * Load dashboard data from backend
     */
    async loadData() {
        try {
            this.state.loading = true;
            this.state.error = null;

            if (!this.state.organizationId) {
                throw new Error('Organization ID is required');
            }

            // Fetch company dashboard data via RPC controller
            const dashboardData = await rpc('/document_extractor/company_dashboard_data', {
                organization_id: this.state.organizationId
            });

            // Check for errors in response
            if (dashboardData.error) {
                throw new Error(dashboardData.message || 'Failed to fetch dashboard data');
            }

            // Update company info
            this.state.companyInfo = dashboardData.company_info || {};
            this.state.organizationName = this.state.companyInfo.name || this.state.organizationName;

            // Update KPI data
            this.state.kpiData = {
                totalSubstances: dashboardData.kpis?.total_substances || 0,
                totalKg: dashboardData.kpis?.total_kg || 0,
                totalCO2e: dashboardData.kpis?.total_co2e || 0,
                recoveryRate: dashboardData.kpis?.recovery_rate || 0,
            };

            // Update chart data
            this.state.trendData = dashboardData.charts?.trend_by_year || {};
            this.state.quotaData = dashboardData.charts?.quota_data || [];

            // Update tab data
            this.state.tabData = dashboardData.tabs || {
                table_1_1: [],
                table_1_2: [],
                table_1_3: [],
                table_2_1: [],
                table_2_4: [],
                ocr_history: [],
            };

            // Update URL state to persist organization_id (for page refresh)
            if (this.organizationId && this.props.updateActionState) {
                this.props.updateActionState({
                    organization_id: this.organizationId
                });
            }

            this.state.loading = false;
        } catch (error) {
            console.error('Error loading company dashboard data:', error);
            this.state.error = error.message || 'Failed to load dashboard data';
            this.state.loading = false;
        }
    }

    /**
     * Render all charts
     */
    renderCharts() {
        this.renderTrendChart();
        this.renderQuotaChart();
    }

    /**
     * Render yearly trend line chart (multi-line by substance)
     */
    renderTrendChart() {
        if (!this.trendChartRef.el || Object.keys(this.state.trendData).length === 0) return;

        const ctx = this.trendChartRef.el.getContext('2d');

        // Destroy existing chart
        if (this.trendChart) {
            this.trendChart.destroy();
        }

        // Transform data: {year: {substance: kg}} → datasets per substance
        const years = Object.keys(this.state.trendData).sort();
        const allSubstances = new Set();
        years.forEach(year => {
            Object.keys(this.state.trendData[year]).forEach(sub => allSubstances.add(sub));
        });

        const datasets = Array.from(allSubstances).map((substance, index) => {
            const data = years.map(year => this.state.trendData[year][substance] || 0);
            const color = getColorByIndex(index);
            return {
                label: substance,
                data: data,
                borderColor: color,
                backgroundColor: hexToRgba(color, 0.1),
                borderWidth: 2,
                fill: false,
                tension: 0.4,
                pointRadius: 3,
                pointHoverRadius: 5,
            };
        });

        this.trendChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: years,
                datasets: datasets
            },
            options: {
                ...LINE_CHART_OPTIONS,
                plugins: {
                    ...LINE_CHART_OPTIONS.plugins,
                    title: {
                        display: true,
                        text: 'Xu hướng sử dụng chất theo năm',
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
     * Render quota allocated vs used bar chart
     */
    renderQuotaChart() {
        if (!this.quotaChartRef.el || this.state.quotaData.length === 0) return;

        const ctx = this.quotaChartRef.el.getContext('2d');

        // Destroy existing chart
        if (this.quotaChart) {
            this.quotaChart.destroy();
        }

        // Group by year
        const yearData = {};
        this.state.quotaData.forEach(item => {
            const year = item.year;
            if (!yearData[year]) {
                yearData[year] = { allocated: 0, used: 0 };
            }
            yearData[year].allocated += item.quota_allocated || 0;
            yearData[year].used += item.quota_used || 0;
        });

        const years = Object.keys(yearData).sort();
        const allocatedData = years.map(y => yearData[y].allocated);
        const usedData = years.map(y => yearData[y].used);

        this.quotaChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: years,
                datasets: [
                    {
                        label: 'Hạn ngạch phân bổ (kg)',
                        data: allocatedData,
                        backgroundColor: hexToRgba(CHART_COLORS.primary, 0.7),
                        borderColor: CHART_COLORS.primary,
                        borderWidth: 1,
                    },
                    {
                        label: 'Hạn ngạch sử dụng (kg)',
                        data: usedData,
                        backgroundColor: hexToRgba(CHART_COLORS.success, 0.7),
                        borderColor: CHART_COLORS.success,
                        borderWidth: 1,
                    }
                ]
            },
            options: {
                ...BAR_CHART_OPTIONS,
                plugins: {
                    ...BAR_CHART_OPTIONS.plugins,
                    title: {
                        display: true,
                        text: 'Hạn ngạch được phân bổ – sử dụng',
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
     * Destroy all chart instances
     */
    destroyCharts() {
        if (this.trendChart) {
            this.trendChart.destroy();
            this.trendChart = null;
        }
        if (this.quotaChart) {
            this.quotaChart.destroy();
            this.quotaChart = null;
        }
    }

    /**
     * Switch active tab
     */
    switchTab(tabName) {
        this.state.activeTab = tabName;
    }

    /**
     * Get active tab data
     */
    get activeTabData() {
        return this.state.tabData[this.state.activeTab] || [];
    }

    /**
     * Get tab label
     */
    getTabLabel(tabName) {
        const labels = {
            'table_1_1': 'Bảng 1.1 – SX/NK/XK',
            'table_1_2': 'Bảng 1.2 – Thiết bị chứa chất',
            'table_1_3': 'Bảng 1.3 – Sở hữu thiết bị',
            'table_2_1': 'Bảng 2.1 – Hạn ngạch',
            'table_2_4': 'Bảng 2.4 – Thu gom & Tái chế',
            'ocr_history': 'Lịch sử OCR & xác thực'
        };
        return labels[tabName] || tabName;
    }

    /**
     * Formatted values for display
     */
    formatNumber(value, decimals = 0) {
        return formatNumber(value, decimals);
    }

    formatWeight(value) {
        return formatWeight(value);
    }

    formatCO2e(value) {
        return formatCO2e(value);
    }
}

// Register the dashboard as a client action
registry.category("actions").add("document_extractor.company_dashboard", CompanyDashboard);
