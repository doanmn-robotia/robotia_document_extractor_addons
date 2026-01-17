/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { user } from "@web/core/user";
import { _t } from "@web/core/l10n/translation";

export class LogsTab extends Component {
    static template = "robotia_document_extractor.SettingsLogsTab";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");

        this.state = useState({
            devices: [],
            searchQuery: '',
            loading: true,
            isAdmin: false
        });

        onWillStart(async () => {
            // Check if admin using user.hasGroup()
            this.state.isAdmin =
                await user.hasGroup("base.group_system") ||
                await user.hasGroup("robotia_document_extractor.group_document_extractor_admin");

            await this.loadDevices();
            this.state.loading = false;
        });
    }

    async loadDevices() {
        // webSearchRead with EMPTY domain [] - ir.rule automatically filters:
        // - Admin: sees ALL devices
        // - User: sees ONLY own devices
        const result = await this.orm.webSearchRead(
            "res.device",
            [],  // Empty domain - let ir.rule handle filtering
            {
                specification: {
                    id: {},
                    display_name: {},
                    user_id: {},
                    session_identifier: {},
                    platform: {},
                    browser: {},
                    ip_address: {},
                    country: {},
                    city: {},
                    device_type: {},
                    first_activity: {},
                    last_activity: {},
                    is_current: {}
                },
                order: "is_current desc, last_activity desc"
            }
        );
        this.state.devices = result.records;
    }

    async revokeDevice(deviceId) {
        // Find device by ID
        const device = this.state.devices.find(d => d.id === deviceId);
        if (!device) return;

        this.dialog.add(ConfirmationDialog, {
            body: _t('Are you sure you want to revoke device "%s"? This session will be logged out immediately.', device.display_name),
            confirm: async () => {
                await this.action.doActionButton({
                    type: "object",
                    name: "revoke",
                    resModel: "res.device",
                    resId: device.id,
                    onClose: async () => {
                        await this.loadDevices();
                    }
                });
            },
            cancel: () => {}
        });
    }

    getRelativeTime(dateStr) {
        // Use luxon for relative time formatting with translations
        if (!dateStr) return _t("Unknown");

        try {
            const { DateTime } = luxon;
            const date = DateTime.fromJSDate(new Date(dateStr));
            const now = DateTime.now();
            const diff = now.diff(date, ['days', 'hours', 'minutes']).toObject();

            if (diff.minutes < 1) return _t("just now");
            if (diff.minutes < 60) {
                const min = Math.floor(diff.minutes);
                return min === 1 ? _t("1 minute ago") : _t("%s minutes ago", min);
            }
            if (diff.hours < 24) {
                const hrs = Math.floor(diff.hours);
                return hrs === 1 ? _t("1 hour ago") : _t("%s hours ago", hrs);
            }
            if (diff.days < 30) {
                const days = Math.floor(diff.days);
                return days === 1 ? _t("1 day ago") : _t("%s days ago", days);
            }
            return date;
        } catch (e) {
            return dateStr;
        }
    }

    formatDateTime(dateStr) {
        // Format full datetime using luxon
        if (!dateStr) return "";

        try {
            const { DateTime } = luxon;
            const date = DateTime.fromJSDate(new Date(dateStr));
            return date.toLocaleString(DateTime.DATETIME_MED);
        } catch (e) {
            return dateStr;
        }
    }

    get filteredDevices() {
        return this.state.devices.filter(device => {
            if (!this.state.searchQuery) return true;

            const query = this.state.searchQuery.toLowerCase();
            return (device.display_name && device.display_name.toLowerCase().includes(query)) ||
                   (device.ip_address && device.ip_address.toLowerCase().includes(query)) ||
                   (device.country && device.country.toLowerCase().includes(query)) ||
                   (device.city && device.city.toLowerCase().includes(query)) ||
                   (device.user_id && device.user_id[1] && device.user_id[1].toLowerCase().includes(query));
        });
    }

    onSearchInput(ev) {
        this.state.searchQuery = ev.target.value;
    }

    getLocationString(device) {
        const parts = [];
        if (device.country) parts.push(device.country);
        if (device.city) parts.push(device.city);
        return parts.join(', ') || 'Unknown';
    }
}
