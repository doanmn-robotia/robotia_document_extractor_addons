/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class UsersTab extends Component {
    static template = "robotia_document_extractor.SettingsUsersTab";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            users: [],
            systemGroupId: null,
            stats: { total: 0, admin: 0, maker: 0, checker: 0, viewer: 0 },
            searchQuery: '',
            roleFilter: 'All',
            statusFilter: 'All',
            loading: true
        });

        onWillStart(async () => {
            await this.loadSystemGroup();
            await this.loadUsers();
            this.computeStats();
            this.state.loading = false;
        });
    }

    async loadSystemGroup() {
        // Load base.group_system ID
        const groups = await this.orm.searchRead(
            "res.groups",
            [["name", "=", "Settings"]],
            ["id"]
        );
        if (groups.length > 0) {
            this.state.systemGroupId = groups[0].id;
        }
    }

    async loadUsers() {
        // Load all users with their groups
        this.state.users = await this.orm.searchRead(
            "res.users",
            [],
            ["id", "name", "login", "email", "phone", "active", "create_date", "groups_id"],
            {
                order: "create_date desc"
            }
        );
    }

    computeStats() {
        const users = this.state.users;
        this.state.stats.total = users.length;

        // Admin = users with base.group_system
        this.state.stats.admin = users.filter(u =>
            u.groups_id.includes(this.state.systemGroupId)
        ).length;

        // For now, Maker/Checker/Viewer stats are 0 (can be extended later)
        this.state.stats.maker = 0;
        this.state.stats.checker = 0;
        this.state.stats.viewer = 0;
    }

    get filteredUsers() {
        return this.state.users.filter(user => {
            const matchSearch = user.name.toLowerCase().includes(this.state.searchQuery.toLowerCase()) ||
                               (user.email && user.email.toLowerCase().includes(this.state.searchQuery.toLowerCase())) ||
                               (user.phone && user.phone.includes(this.state.searchQuery));

            // Admin filter = check if user has base.group_system
            const matchRole = this.state.roleFilter === 'All' ||
                             (this.state.roleFilter === 'Admin' && user.groups_id.includes(this.state.systemGroupId)) ||
                             (this.state.roleFilter !== 'Admin' && !user.groups_id.includes(this.state.systemGroupId));

            // Status filter by active field
            const matchStatus = this.state.statusFilter === 'All' ||
                               (this.state.statusFilter === 'Active' && user.active) ||
                               (this.state.statusFilter === 'Inactive' && !user.active);

            return matchSearch && matchRole && matchStatus;
        });
    }

    onRowClick(userId) {
        // Click row opens full form view (not popup)
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'res.users',
            res_id: userId,
            views: [[false, 'form']],
            view_mode: 'form',
            target: 'current'  // Open in current window, not popup
        });
    }

    onEditClick(userId, ev) {
        // Stop propagation to prevent row click
        ev.stopPropagation();

        // Edit button opens base.view_users_form_simple_modif in popup
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'res.users',
            res_id: userId,
            views: [[this.env.services.view.get('base.view_users_form_simple_modif'), 'form']],
            view_mode: 'form',
            target: 'new'  // Open as popup
        });
    }

    async onArchiveClick(userId, ev) {
        // Stop propagation to prevent row click
        ev.stopPropagation();

        // Call action_archive on user
        await this.orm.call(
            "res.users",
            "action_archive",
            [[userId]]
        );

        // Reload users
        await this.loadUsers();
        this.computeStats();
    }

    onAddUserClick() {
        // Add User opens full form view (not popup)
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'res.users',
            views: [[false, 'form']],
            view_mode: 'form',
            target: 'current'  // Open in current window
        });
    }

    onSearchInput(ev) {
        this.state.searchQuery = ev.target.value;
    }

    onRoleFilter(ev) {
        this.state.roleFilter = ev.target.value;
    }

    onStatusFilter(ev) {
        this.state.statusFilter = ev.target.value;
    }

    isAdmin(user) {
        return user.groups_id.includes(this.state.systemGroupId);
    }

    getUserInitial(name) {
        return name ? name[0].toUpperCase() : '?';
    }

    formatDate(dateStr) {
        luxon.DateTime.fromFormat
        if (!dateStr) return '';
        try {
            const date = new Date(dateStr);
            return date.toLocaleDateString('en-US', {
                year: 'numeric',
                month: 'short',
                day: 'numeric'
            });
        } catch (e) {
            return dateStr;
        }
    }
}
