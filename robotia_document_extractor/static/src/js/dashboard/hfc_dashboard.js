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
    PIE_CHART_OPTIONS,
    formatNumber,
    formatCO2e,
    getColorByIndex,
    hexToRgba
} from "../utils/chart_utils";

/**
 * HFC Dashboard Component
 *
 * Displays aggregated data for all controlled substances (HFC/HCFC)
 * with comprehensive filtering sidebar and multiple chart visualizations.
 */
export class HfcDashboard extends Component {
    static template = "robotia_document_extractor.HfcDashboard";

    setup() {
        // Services
        this.orm = useService("orm");
        this.action = useService("action");

        // Chart references
        this.barChartRef = useRef("barChart");
        this.pieChartRef = useRef("pieChart");
        this.barChart = null;
        this.pieChart = null;
        this.ui = useService("ui")

        // State management
        this.state = useState({
            loading: true,
            error: null,

            // Filter state (13 filters)
            filters: {
                organization_search: '',
                organization_code: '',
                province: '',
                substance_name: '',
                hs_code: '',
                substance_group_id: null,        // Changed: ID instead of string
                activity_field_ids: [],          // Changed: IDs instead of codes
                year_from: null,
                year_to: null,
                quantity_min: null,
                quantity_max: null,
                quota_min: null,
                status: ['completed'],  // Default: only show completed reports
            },

            // Filter metadata for dropdowns
            filterMetadata: {
                provinces: [],
                years: [],
                substanceGroups: [],      // NEW: Dynamic groups
                activityFields: [],       // NEW: Dynamic activity fields
                statusOptions: [],        // NEW: Dynamic status options
            },

            // Dashboard data
            kpiData: {
                total_organizations: 0,
                total_kg: 0,
                total_co2e: 0,
                verified_percentage: 0,
                quota_utilization: 0,    // NEW: % quota used (Form 02)
                total_eol_kg: 0,         // NEW: Collection/Recycling total
            },

            // Chart data
            trendData: [],              // Bar chart: year × substance
            activityTypeData: [],       // Pie chart: activity breakdown
            topRecordsData: [],         // Top 10 table
            pivotData: [],              // Pivot table: DN × Substance × Year

            // UI state
            sidebarVisible: true,
        });

        // Lifecycle hooks
        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            await this.loadFilterMetadata();
            await this.loadData();
        });

        useEffect(() => {
            if (!this.state.loading && !this.state.error) {
                this.renderCharts();
            }
            return () => {
                this.destroyCharts();
            };
        }, () => [this.state.loading, this.state.trendData, this.state.activityTypeData]);
    }

    /**
     * Load filter metadata (provinces, years, groups, fields, statuses) for dropdowns
     */
    async loadFilterMetadata() {
        try {
            // Load all metadata in parallel
            const [states, substanceGroups, activityFields] = await Promise.all([
                // Load provinces from res.country.state
                this.orm.searchRead(
                    'res.country.state',
                    [],
                    ['name'],
                    { order: 'name' }
                ),
                // Load substance groups
                this.orm.searchRead(
                    'substance.group',
                    [['active', '=', true]],
                    ['id', 'name', 'code'],
                    { order: 'sequence, name' }
                ),
                // Load activity fields
                this.orm.searchRead(
                    'activity.field',
                    [['active', '=', true]],
                    ['id', 'name', 'code'],
                    { order: 'sequence, name' }
                )
            ]);

            // Status options (from document.extraction state field)
            const statusOptions = [
                { value: 'draft', label: 'Nháp' },
                { value: 'validated', label: 'Đã xác thực' },
                { value: 'completed', label: 'Hoàn thành' }
            ];

            // Years range
            const currentYear = new Date().getFullYear();
            const years = Array.from({ length: 5 }, (_, i) => currentYear - 4 + i);

            // Update state
            this.state.filterMetadata = {
                provinces: states.map(s => s.name),
                years: years,
                substanceGroups: substanceGroups,
                activityFields: activityFields,
                statusOptions: statusOptions
            };

            console.log("Filter metadata loaded:", this.state.filterMetadata);

        } catch (error) {
            console.error("Error loading filter metadata:", error);
        }
    }

    /**
     * Load dashboard data from backend
     */
    async loadData() {
        try {
            this.state.loading = true;
            this.state.error = null;

            // Prepare filters - if status is empty array, set to all statuses
            const filters = { ...this.state.filters };
            if (!filters.status || filters.status.length === 0) {
                filters.status = ['draft', 'validated', 'completed'];  // All statuses
            }

            const dashboardData = await rpc(
                '/document_extractor/hfc_dashboard_data',
                { filters: filters }
            );

            if (dashboardData.error) {
                throw new Error(dashboardData.message);
            }

            // Update state with response
            this.state.kpiData = dashboardData.kpis;
            this.state.trendData = dashboardData.charts.trend_by_year_substance || [];
            this.state.activityTypeData = dashboardData.charts.by_activity_type || [];
            this.state.topRecordsData = dashboardData.charts.top_10_records || [];
            this.state.pivotData = dashboardData.charts.pivot_data || [];

            // Update years metadata from response
            if (dashboardData.filter_metadata?.available_years) {
                this.state.filterMetadata.years = dashboardData.filter_metadata.available_years;
            }

            this.state.loading = false;
            console.log("HFC dashboard data loaded successfully");

        } catch (error) {
            console.error("Error loading HFC dashboard:", error);
            this.state.error = error.message || "Lỗi tải dữ liệu dashboard";
            this.state.loading = false;
        }
    }

    /**
     * Apply current filters and reload data
     */
    applyFilters() {
        this.loadData();
    }

    /**
     * Clear all filters and reload
     */
    clearFilters() {
        this.state.filters = {
            organization_search: '',
            organization_code: '',
            province: '',
            substance_name: '',
            hs_code: '',
            substance_group_id: null,       // Changed: null instead of ''
            activity_field_ids: [],         // Changed: field name
            year_from: null,
            year_to: null,
            quantity_min: null,
            quantity_max: null,
            quota_min: null,
            status: ['completed'],  // Reset to default
        };
        this.loadData();
    }

    /**
     * Toggle activity field checkbox
     */
    toggleActivityField(fieldId) {
        const idx = this.state.filters.activity_field_ids.indexOf(fieldId);
        if (idx > -1) {
            this.state.filters.activity_field_ids.splice(idx, 1);
        } else {
            this.state.filters.activity_field_ids.push(fieldId);
        }
    }

    /**
     * Toggle status checkbox
     */
    toggleStatus(status) {
        const idx = this.state.filters.status.indexOf(status);
        if (idx > -1) {
            this.state.filters.status.splice(idx, 1);
        } else {
            this.state.filters.status.push(status);
        }
    }

    /**
     * Render all charts
     */
    renderCharts() {
        this.renderBarChart();
        this.renderPieChart();
    }

    /**
     * Render grouped bar chart: Year × Substance
     */
    renderBarChart() {
        if (!this.barChartRef.el || this.state.trendData.length === 0) {
            console.log("Bar chart: No data or canvas not ready");
            return;
        }

        const ctx = this.barChartRef.el.getContext('2d');
        if (this.barChart) this.barChart.destroy();

        // Group by year, then by substance
        const years = [...new Set(this.state.trendData.map(d => d.year))].sort();
        const substances = [...new Set(this.state.trendData.map(d => d.substance_name))];

        const datasets = substances.map((substance, idx) => {
            const data = years.map(year => {
                const record = this.state.trendData.find(
                    d => d.year === year && d.substance_name === substance
                );
                return record ? record.total_kg : 0;
            });

            return {
                label: substance,
                data: data,
                backgroundColor: getColorByIndex(idx),
                borderColor: getColorByIndex(idx),
                borderWidth: 1,
            };
        });

        this.barChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: years,
                datasets: datasets
            },
            options: {
                ...BAR_CHART_OPTIONS,
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: true,
                        text: 'Biểu đồ khối lượng HFC theo năm & chất (kg)',
                        font: { size: 14, weight: 'bold' }
                    },
                    legend: {
                        display: true,
                        position: 'top',
                        labels: { font: { size: 11 } }
                    },
                    tooltip: {
                        callbacks: {
                            label: (context) => {
                                const label = context.dataset.label || '';
                                const value = formatNumber(context.parsed.y, 0);
                                return `${label}: ${value} kg`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        stacked: false,
                        grid: { display: false },
                        ticks: { font: { size: 11 } }
                    },
                    y: {
                        stacked: false,
                        beginAtZero: true,
                        ticks: {
                            font: { size: 11 },
                            callback: (value) => formatNumber(value, 0)
                        }
                    }
                }
            }
        });

        console.log("Bar chart rendered successfully");
    }

    /**
     * Render pie chart: Activity type distribution
     */
    renderPieChart() {
        if (!this.pieChartRef.el || this.state.activityTypeData.length === 0) {
            console.log("Pie chart: No data or canvas not ready");
            return;
        }

        const ctx = this.pieChartRef.el.getContext('2d');
        if (this.pieChart) this.pieChart.destroy();

        const labels = this.state.activityTypeData.map(d => d.activity_label);
        const data = this.state.activityTypeData.map(d => d.total_kg);
        const colors = this.state.activityTypeData.map((_, idx) => getColorByIndex(idx));

        this.pieChart = new Chart(ctx, {
            type: 'pie',
            data: {
                labels: labels,
                datasets: [{
                    data: data,
                    backgroundColor: colors,
                    borderWidth: 1,
                    borderColor: '#fff',
                }]
            },
            options: {
                ...PIE_CHART_OPTIONS,
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: true,
                        text: 'Cơ cấu hoạt động (kg)',
                        font: { size: 14, weight: 'bold' }
                    },
                    legend: {
                        display: true,
                        position: 'right',
                        labels: { font: { size: 10 } }
                    },
                    tooltip: {
                        callbacks: {
                            label: (context) => {
                                const label = context.label || '';
                                const value = formatNumber(context.parsed, 0);
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const percentage = ((context.parsed / total) * 100).toFixed(1);
                                return `${label}: ${value} kg (${percentage}%)`;
                            }
                        }
                    }
                }
            }
        });

        console.log("Pie chart rendered successfully");
    }

    /**
     * Clean up charts
     */
    destroyCharts() {
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
     * Navigate to organization dashboard
     */
    viewOrganization(organizationId) {
        this.action.doAction({
            type: 'ir.actions.client',
            tag: 'document_extractor.company_dashboard',
            params: {
                organization_id: organizationId,
            }
        });
    }

    /**
     * Navigate to substance dashboard
     */
    viewSubstance(substanceId) {
        this.action.doAction({
            type: 'ir.actions.client',
            tag: 'document_extractor.substance_dashboard',
            params: {
                substance_id: substanceId,
            }
        });
    }

    /**
     * Export report to Excel
     */
    async exportReport() {
        try {
            // Show loading notification
            this.action.doAction({
                type: 'ir.actions.client',
                tag: 'display_notification',
                params: {
                    title: 'Đang xuất báo cáo...',
                    message: 'Vui lòng đợi trong giây lát',
                    type: 'info',
                    sticky: false,
                }
            });

            this.ui.block()

            // Prepare filters - if status is empty array, set to all statuses
            const filters = { ...this.state.filters };
            if (!filters.status || filters.status.length === 0) {
                filters.status = ['draft', 'validated', 'completed'];  // All statuses
            }

            // Prepare form data
            const formData = new FormData();
            formData.append('filters', JSON.stringify(filters));

            // Call backend via HTTP POST (not RPC because we need binary response)
            const response = await fetch('/document_extractor/export_hfc_report', {
                method: 'POST',
                body: formData,
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            // Check if response is JSON (error) or Excel file
            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                const error = await response.json();
                throw new Error(error.message || 'Unknown error');
            }

            // Get the blob (Excel file)
            const blob = await response.blob();

            // Generate filename with timestamp
            const timestamp = new Date().toISOString().slice(0, 19).replace(/:/g, '-').replace('T', '_');
            const filename = `HFC_Report_${timestamp}.xlsx`;

            // Create download link
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();

            // Cleanup
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);

            // Show success notification
            this.action.doAction({
                type: 'ir.actions.client',
                tag: 'display_notification',
                params: {
                    title: 'Xuất báo cáo thành công',
                    message: `File ${filename} đã được tải xuống`,
                    type: 'success',
                    sticky: false,
                }
            });

            console.log("Export completed successfully");

        } catch (error) {
            console.error("Error exporting report:", error);
            this.action.doAction({
                type: 'ir.actions.client',
                tag: 'display_notification',
                params: {
                    title: 'Lỗi xuất báo cáo',
                    message: error.message || 'Đã xảy ra lỗi khi xuất báo cáo',
                    type: 'danger',
                    sticky: true,
                }
            });
        } finally {
            this.ui.unblock()
        }
    }

    /**
     * Toggle sidebar visibility
     */
    toggleSidebar() {
        this.state.sidebarVisible = !this.state.sidebarVisible;
    }

    // ===== Helper methods for template =====

    formatNumber(value, decimals = 0) {
        return formatNumber(value, decimals);
    }

    formatCO2e(value) {
        return formatCO2e(value);
    }

    getStatusBadgeClass(status) {
        const statusMap = {
            'validated': 'badge-success',
            'completed': 'badge-success',
            'draft': 'badge-warning',
        };
        return statusMap[status] || 'badge-warning';
    }

    getStatusLabel(status) {
        const labelMap = {
            'validated': 'Đã xác thực',
            'completed': 'Hoàn thành',
            'draft': 'Nháp',
        };
        return labelMap[status] || status;
    }
}

// Register as client action
registry.category("actions").add("document_extractor.hfc_dashboard", HfcDashboard);
