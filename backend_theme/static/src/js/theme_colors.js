/** @odoo-module */

import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";

/**
 * Color Manipulation Utilities
 */
const colorUtils = {
    /**
     * Convert hex to RGB
     */
    hexToRgb(hex) {
        const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
        return result ? {
            r: parseInt(result[1], 16),
            g: parseInt(result[2], 16),
            b: parseInt(result[3], 16)
        } : null;
    },

    /**
     * Convert RGB to hex
     */
    rgbToHex(r, g, b) {
        return "#" + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1);
    },

    /**
     * Darken a color by percentage
     */
    darken(hex, percent) {
        const rgb = this.hexToRgb(hex);
        if (!rgb) return hex;

        const factor = 1 - (percent / 100);
        return this.rgbToHex(
            Math.max(0, Math.floor(rgb.r * factor)),
            Math.max(0, Math.floor(rgb.g * factor)),
            Math.max(0, Math.floor(rgb.b * factor))
        );
    },

    /**
     * Lighten a color by percentage
     */
    lighten(hex, percent) {
        const rgb = this.hexToRgb(hex);
        if (!rgb) return hex;

        const factor = percent / 100;
        return this.rgbToHex(
            Math.min(255, Math.floor(rgb.r + (255 - rgb.r) * factor)),
            Math.min(255, Math.floor(rgb.g + (255 - rgb.g) * factor)),
            Math.min(255, Math.floor(rgb.b + (255 - rgb.b) * factor))
        );
    },

    /**
     * Create rgba string with opacity
     */
    withOpacity(hex, opacity) {
        const rgb = this.hexToRgb(hex);
        if (!rgb) return hex;
        return `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${opacity})`;
    }
};

/**
 * Theme Colors Service
 *
 * This service loads theme colors from backend settings and applies them
 * as CSS custom properties to the document root, enabling dynamic theming.
 */
const themeColorsService = {
    dependencies: [],

    /**
     * Start the service and load theme colors
     *
     * @returns {Promise} Promise that resolves when colors are loaded and applied
     */
    async start() {
        await this.loadAndApplyThemeColors();
    },

    /**
     * Load theme colors from backend and apply them to CSS variables
     *
     * Fetches the color configuration from ir.config_parameter and updates
     * the CSS custom properties on the document root element.
     */
    async loadAndApplyThemeColors() {
        try {
            const result = await rpc('/web/dataset/call_kw', {
                model: 'ir.config_parameter',
                method: 'search_read',
                args: [
                    [
                        ['key', 'in', [
                            'backend_theme.primary_color',
                            'backend_theme.secondary_color'
                        ]]
                    ],
                    ['key', 'value']
                ],
                kwargs: {}
            });

            // Create a map of colors from the result
            const colors = {};
            result.forEach(param => {
                if (param.key === 'backend_theme.primary_color') {
                    colors.primary = param.value || '#6366f1'; // Default: Indigo-500
                } else if (param.key === 'backend_theme.secondary_color') {
                    colors.secondary = param.value || '#f8fafc'; // Default: Slate-50
                }
            });

            // Apply colors to CSS variables
            this.applyColors(colors);

        } catch (error) {
            console.error('Failed to load theme colors:', error);
            // Apply default colors if loading fails (modern Indigo theme)
            this.applyColors({
                primary: '#6366f1', // Indigo-500
                secondary: '#f8fafc' // Slate-50
            });
        }
    },

    /**
     * Apply color values to CSS custom properties
     * Auto-generates all color variants (hover, active, light, dark)
     *
     * @param {Object} colors - Object containing primary and secondary colors
     * @param {string} colors.primary - Primary color hex value
     * @param {string} colors.secondary - Secondary color hex value
     */
    applyColors(colors) {
        const root = document.documentElement;

        if (colors.primary) {
            // Primary color and variants
            root.style.setProperty('--primary-accent', colors.primary);
            root.style.setProperty('--primary-hover', colorUtils.darken(colors.primary, 10));
            root.style.setProperty('--primary-active', colorUtils.darken(colors.primary, 15));
            root.style.setProperty('--primary-dark', colorUtils.darken(colors.primary, 25));
            root.style.setProperty('--primary-light', colorUtils.lighten(colors.primary, 90));
            root.style.setProperty('--primary-hover-05', colorUtils.withOpacity(colors.primary, 0.05));

            // Border
            root.style.setProperty('--primary-accent-border', colorUtils.lighten(colors.primary, 80));

            // Shadows with primary tint
            const primaryRgb = colorUtils.hexToRgb(colors.primary);
            if (primaryRgb) {
                root.style.setProperty('--shadow-primary',
                    `0 10px 15px -3px rgba(${primaryRgb.r}, ${primaryRgb.g}, ${primaryRgb.b}, 0.2), 0 4px 6px -2px rgba(${primaryRgb.r}, ${primaryRgb.g}, ${primaryRgb.b}, 0.15)`
                );
                root.style.setProperty('--shadow-primary-sm',
                    `0 4px 12px -2px rgba(${primaryRgb.r}, ${primaryRgb.g}, ${primaryRgb.b}, 0.15)`
                );
            }
        }

        if (colors.secondary) {
            root.style.setProperty('--secondary-accent', colors.secondary);
            root.style.setProperty('--secondary-hover', colorUtils.darken(colors.secondary, 5));
            root.style.setProperty('--secondary-active', colorUtils.darken(colors.secondary, 10));
        }

        console.log('Theme colors applied with variants:', {
            primary: colors.primary,
            'primary-hover': colorUtils.darken(colors.primary, 10),
            'primary-active': colorUtils.darken(colors.primary, 15),
            'primary-light': colorUtils.lighten(colors.primary, 90),
            secondary: colors.secondary
        });
    }
};

// Register the service to run on webclient startup
registry.category("services").add("themeColors", themeColorsService);
