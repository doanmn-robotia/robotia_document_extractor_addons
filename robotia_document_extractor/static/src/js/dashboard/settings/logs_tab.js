/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class LogsTab extends Component {
    static template = "robotia_document_extractor.SettingsLogsTab";

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            devices: [],
            searchQuery: '',
            userFilter: null,
            loading: true
        });

        onWillStart(async () => {
            await this.loadDevices();
            this.state.loading = false;
        });
    }

    async loadDevices(userId = null) {
        // Query res.device using ORM service
        const domain = userId ? [["user_id", "=", userId]] : [];

        this.state.devices = await this.orm.searchRead(
            "res.device",
            domain,
            [
                "id", "display_name", "user_id", "session_identifier",
                "platform", "browser", "ip_address", "country", "city",
                "device_type", "first_activity", "last_activity",
                "is_current", "revoked", "linked_ip_addresses"
            ],
            {
                order: "is_current desc, last_activity desc"
            }
        );
    }

    async revokeDevice(deviceId) {
        // Call revoke method on res.device
        await this.orm.call(
            "res.device",
            "revoke",
            [[deviceId]]
        );
        // Reload devices after revocation
        await this.loadDevices(this.state.userFilter);
    }

    getRelativeTime(dateStr) {
        // Use native JavaScript for relative time formatting
        if (!dateStr) return "Unknown";

        try {
            const date = new Date(dateStr);
            const now = new Date();
            const diffMs = now - date;
            const diffSec = Math.floor(diffMs / 1000);
            const diffMin = Math.floor(diffSec / 60);
            const diffHour = Math.floor(diffMin / 60);
            const diffDay = Math.floor(diffHour / 24);

            if (diffMin < 1) return "just now";
            if (diffMin < 60) return `${diffMin} minute${diffMin > 1 ? 's' : ''} ago`;
            if (diffHour < 24) return `${diffHour} hour${diffHour > 1 ? 's' : ''} ago`;
            if (diffDay < 30) return `${diffDay} day${diffDay > 1 ? 's' : ''} ago`;
            return date.toLocaleDateString();
        } catch (e) {
            return dateStr;
        }
    }

    formatDateTime(dateStr) {
        // Format full datetime
        if (!dateStr) return "";

        try {
            const date = new Date(dateStr);
            return date.toLocaleString('en-US', {
                year: 'numeric',
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
        } catch (e) {
            return dateStr;
        }
    }

    get filteredDevices() {
        return this.state.devices.filter(device => {
            if (!this.state.searchQuery) return true;

            const query = this.state.searchQuery.toLowerCase();
            return device.display_name.toLowerCase().includes(query) ||
                   (device.ip_address && device.ip_address.includes(query)) ||
                   (device.country && device.country.toLowerCase().includes(query)) ||
                   (device.city && device.city.toLowerCase().includes(query)) ||
                   (device.user_id && device.user_id[1].toLowerCase().includes(query));
        });
    }

    onSearchInput(ev) {
        this.state.searchQuery = ev.target.value;
    }

    async filterByUser(userId) {
        this.state.userFilter = userId;
        await this.loadDevices(userId);
    }

    getLocationString(device) {
        const parts = [];
        if (device.country) parts.push(device.country);
        if (device.city) parts.push(device.city);
        return parts.join(', ') || 'Unknown';
    }
}
