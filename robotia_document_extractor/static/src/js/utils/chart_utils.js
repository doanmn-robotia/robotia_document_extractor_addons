/** @odoo-module **/

/**
 * Chart utilities for dashboard analytics
 * Provides color palettes, default options, and helper functions for Chart.js
 *
 * IMPORTANT: Chart colors are aligned with backend_theme CSS variables.
 * These colors match the default theme palette (Indigo/Slate) but are hardcoded
 * in JavaScript since Chart.js cannot directly use CSS variables.
 *
 * If you change the theme colors in Settings > Backend Theme, you may want to
 * update these values to match your custom theme.
 */

// Color palette for charts - Aligned with backend_theme CSS variables
export const CHART_COLORS = {
    primary: '#6366f1',      // Indigo-500 (matches var(--primary-accent))
    success: '#10b981',      // Emerald-500 (matches var(--success))
    warning: '#f59e0b',      // Amber-500 (matches var(--warning))
    danger: '#ef4444',       // Red-500 (matches var(--error))
    info: '#3b82f6',         // Blue-500 (matches var(--info))
    purple: '#a855f7',       // Purple-500
    orange: '#fb923c',       // Orange-400
    teal: '#14b8a6',         // Teal-500
    pink: '#ec4899',         // Pink-500
    indigo: '#6366f1',       // Indigo-500 (same as primary)
};

// Array of colors for multi-series charts - Aligned with theme palette
export const CHART_COLOR_ARRAY = [
    '#6366f1', // Primary (Indigo)
    '#10b981', // Success (Emerald)
    '#f59e0b', // Warning (Amber)
    '#ef4444', // Error (Red)
    '#3b82f6', // Info (Blue)
    '#a855f7', // Purple
    '#fb923c', // Orange
    '#14b8a6', // Teal
    '#ec4899', // Pink
    '#8b5cf6', // Violet
    '#06b6d4', // Cyan
    '#84cc16', // Lime
    '#f97316', // Orange-600
    '#eab308', // Yellow
    '#22c55e'  // Green
];

// Default chart options (common for all charts)
export const DEFAULT_CHART_OPTIONS = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
        legend: {
            position: 'right',
            labels: {
                padding: 15,
                font: {
                    size: 12,
                    family: "'Open Sans', 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif"
                },
                boxWidth: 12,
                boxHeight: 12,
            }
        },
        tooltip: {
            enabled: true,
            backgroundColor: 'rgba(0, 0, 0, 0.8)',
            titleFont: {
                size: 13,
                weight: 'bold'
            },
            bodyFont: {
                size: 12
            },
            padding: 12,
            cornerRadius: 4,
        }
    }
};

// Line chart specific options
export const LINE_CHART_OPTIONS = {
    ...DEFAULT_CHART_OPTIONS,
    plugins: {
        ...DEFAULT_CHART_OPTIONS.plugins,
        legend: {
            ...DEFAULT_CHART_OPTIONS.plugins.legend,
            position: 'top',
        }
    },
    scales: {
        x: {
            grid: {
                display: false
            },
            ticks: {
                font: {
                    size: 11
                }
            }
        },
        y: {
            beginAtZero: true,
            grid: {
                color: 'rgba(0, 0, 0, 0.05)'
            },
            ticks: {
                font: {
                    size: 11
                },
                callback: function(value) {
                    return formatNumber(value, 0);
                }
            }
        }
    }
};

// Bar chart specific options
export const BAR_CHART_OPTIONS = {
    ...DEFAULT_CHART_OPTIONS,
    plugins: {
        ...DEFAULT_CHART_OPTIONS.plugins,
        legend: {
            display: false
        }
    },
    scales: {
        x: {
            grid: {
                display: false
            },
            ticks: {
                font: {
                    size: 11
                },
                maxRotation: 45,
                minRotation: 0
            }
        },
        y: {
            beginAtZero: true,
            grid: {
                color: 'rgba(0, 0, 0, 0.05)'
            },
            ticks: {
                font: {
                    size: 11
                },
                callback: function(value) {
                    return formatNumber(value, 0);
                }
            }
        }
    }
};

// Pie/Doughnut chart specific options
export const PIE_CHART_OPTIONS = {
    ...DEFAULT_CHART_OPTIONS,
    plugins: {
        ...DEFAULT_CHART_OPTIONS.plugins,
        legend: {
            ...DEFAULT_CHART_OPTIONS.plugins.legend,
            position: 'right',
        },
        tooltip: {
            ...DEFAULT_CHART_OPTIONS.plugins.tooltip,
            callbacks: {
                label: function(context) {
                    const label = context.label || '';
                    const value = context.parsed || 0;
                    const total = context.dataset.data.reduce((a, b) => a + b, 0);
                    const percentage = total > 0 ? ((value / total) * 100).toFixed(1) : 0;
                    return `${label}: ${formatNumber(value, 0)} (${percentage}%)`;
                }
            }
        }
    }
};

/**
 * Format number with thousands separator
 * @param {number} value - Number to format
 * @param {number} decimals - Number of decimal places
 * @returns {string} Formatted number
 */
export function formatNumber(value, decimals = 0) {
    if (value === null || value === undefined || isNaN(value)) {
        return '0';
    }
    return value.toLocaleString('vi-VN', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
    });
}

/**
 * Format CO2 equivalent value
 * @param {number} value - CO2e value in tons
 * @returns {string} Formatted CO2e with unit
 */
export function formatCO2e(value) {
    if (value === null || value === undefined || isNaN(value)) {
        return '0 tấn CO₂tđ';
    }
    return `${formatNumber(value, 2)} tấn CO₂tđ`;
}

/**
 * Format weight in kg
 * @param {number} value - Weight in kg
 * @returns {string} Formatted weight with unit
 */
export function formatWeight(value) {
    if (value === null || value === undefined || isNaN(value)) {
        return '0 kg';
    }
    return `${formatNumber(value, 0)} kg`;
}

/**
 * Get color from palette by index (cycling)
 * @param {number} index - Color index
 * @returns {string} Color hex code
 */
export function getColorByIndex(index) {
    return CHART_COLOR_ARRAY[index % CHART_COLOR_ARRAY.length];
}

/**
 * Generate gradient color for charts
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {string} color - Base color
 * @returns {CanvasGradient} Gradient
 */
export function createGradient(ctx, color) {
    const gradient = ctx.createLinearGradient(0, 0, 0, 400);
    gradient.addColorStop(0, color);
    gradient.addColorStop(1, color + '33'); // Add transparency
    return gradient;
}

/**
 * Convert hex color to rgba
 * @param {string} hex - Hex color code
 * @param {number} alpha - Alpha value (0-1)
 * @returns {string} RGBA color string
 */
export function hexToRgba(hex, alpha = 1) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}
