/** @odoo-module **/

/**
 * Chart utilities for dashboard analytics
 * Provides color palettes, default options, and helper functions for Chart.js
 */

// Color palette for charts
export const CHART_COLORS = {
    primary: '#1A73E8',      // Blue
    success: '#34A853',      // Green
    warning: '#FBBC04',      // Yellow
    danger: '#EA4335',       // Red
    info: '#4285F4',         // Light Blue
    purple: '#9C27B0',       // Purple
    orange: '#FF9800',       // Orange
    teal: '#009688',         // Teal
    pink: '#E91E63',         // Pink
    indigo: '#3F51B5',       // Indigo
};

// Array of colors for multi-series charts
export const CHART_COLOR_ARRAY = [
    '#1A73E8', '#34A853', '#FBBC04', '#EA4335', '#4285F4',
    '#9C27B0', '#FF9800', '#009688', '#E91E63', '#3F51B5',
    '#795548', '#607D8B', '#FF5722', '#00BCD4', '#8BC34A'
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
                    family: "'Inter', 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif"
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
 * Format weight with automatic unit scaling
 * Rules:
 * - < 1000 kg → display in kg
 * - >= 1000 kg → convert to tons (tấn)
 * - >= 1000 tons → apply metric prefixes (K, M, B, T)
 *
 * Examples:
 * - 500 → "500 kg"
 * - 1500 → "1.5 tấn"
 * - 1,500,000 → "1.5K tấn"
 * - 2,500,000,000 → "2.5M tấn"
 *
 * @param {number} value - Weight in kg
 * @returns {string} Formatted weight with appropriate unit
 */
export function formatWeight(value) {
    if (value === null || value === undefined || isNaN(value)) {
        return '0 kg';
    }

    // If less than 1000 kg, display in kg
    if (value < 1000) {
        return `${formatNumber(value, 0)} kg`;
    }

    // Convert to tons
    let tons = value / 1000;

    // If less than 1000 tons, display in tons
    if (tons < 1000) {
        // Show decimal if less than 10 tons, otherwise show whole number
        const decimals = tons < 10 ? 1 : 0;
        return `${formatNumber(tons, decimals)} tấn`;
    }

    // Apply metric prefixes for 1000+ tons
    const units = ['tấn', 'K tấn', 'M tấn', 'B tấn', 'T tấn'];
    let unitIndex = 0;

    while (tons >= 1000 && unitIndex < units.length - 1) {
        tons = tons / 1000;
        unitIndex++;
    }

    // Show 1 decimal place for scaled values
    const decimals = tons < 10 ? 1 : 0;
    return `${formatNumber(tons, decimals)} ${units[unitIndex]}`;
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
