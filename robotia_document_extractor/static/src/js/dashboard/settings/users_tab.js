/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";

export class UsersTab extends Component {
    static template = "robotia_document_extractor.SettingsUsersTab";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");

        this.state = useState({
            users: [],
            stats: { total: 0, admin: 0, maker: 0, checker: 0 },
            searchQuery: '',
            roleFilter: 'All',
            statusFilter: 'All',
            loading: true
        });

        onWillStart(async () => {
            await this.loadUsers();
            this.computeStats();
            this.state.loading = false;
        });
    }

    async loadUsers() {
        // webSearchRead with EMPTY domain [] - ir.rule automatically filters:
        // - System Admin: sees ALL users
        // - Doc Admin: sees only users with Document Extractor groups
        const result = await this.orm.webSearchRead(
            "res.users",
            [],  // Empty domain - let ir.rule handle filtering
            {
                specification: {
                    id: {},
                    name: {},
                    login: {},
                    email: {},
                    phone: {},
                    active: {},
                    create_date: {},
                    is_doc_admin: {},
                    is_doc_maker: {},
                    is_doc_checker: {},
                    is_system_admin: {}
                },
                order: "create_date desc"
            }
        );
        this.state.users = result.records;
    }

    computeStats() {
        const users = this.state.users.filter(u => u.active);
        this.state.stats.total = this.state.users.length;

        // Admin card counts BOTH System Admin AND Document Admin
        // Maker and Checker count only their respective roles
        this.state.stats.admin = 0;
        this.state.stats.maker = 0;
        this.state.stats.checker = 0;

        users.forEach(user => {
            // Admin card: count both System Admin and Document Admin
            if (user.is_system_admin || user.is_doc_admin) {
                this.state.stats.admin++;
            }
            // Only count Maker/Checker if user is NOT an admin
            else if (user.is_doc_maker) {
                this.state.stats.maker++;
            } else if (user.is_doc_checker) {
                this.state.stats.checker++;
            }
            // Users with no role are not counted in any category
        });
    }

    get filteredUsers() {
        return this.state.users.filter(user => {
            const matchSearch = !this.state.searchQuery ||
                user.name.toLowerCase().includes(this.state.searchQuery.toLowerCase()) ||
                (user.email && user.email.toLowerCase().includes(this.state.searchQuery.toLowerCase()));

            const matchRole = this.state.roleFilter === 'All' ||
                (this.state.roleFilter === 'Admin' && user.is_doc_admin) ||
                (this.state.roleFilter === 'Maker' && user.is_doc_maker) ||
                (this.state.roleFilter === 'Checker' && user.is_doc_checker);

            const matchStatus = this.state.statusFilter === 'All' ||
                (this.state.statusFilter === 'Active' && user.active) ||
                (this.state.statusFilter === 'Inactive' && !user.active);

            return matchSearch && matchRole && matchStatus;
        });
    }

    getUserRoles(user) {
        // Return only the highest role (selection groups, not implied)
        // Priority: System Admin > Document Admin > Maker > Checker > No role
        if (user.is_system_admin) {
            return [{ name: _t('System Admin'), class: 'bg-danger' }];
        } else if (user.is_doc_admin) {
            return [{ name: _t('Document Admin'), class: 'bg-danger' }];
        } else if (user.is_doc_maker) {
            return [{ name: _t('Maker'), class: 'bg-primary' }];
        } else if (user.is_doc_checker) {
            return [{ name: _t('Checker'), class: 'bg-warning' }];
        } else {
            return [{ name: _t('No Role'), class: 'bg-secondary' }];
        }
    }

    onRowClick(userId) {
        // Click row opens full form view (not popup)
        this.action.doAction('base.action_res_users', {
            viewType: 'form',
            props: {
                resId: userId
            }
        });
    }

    onEditClick(userId, ev) {
        // Stop propagation to prevent row click
        ev.stopPropagation();

        // Edit button opens base.view_users_form_simple_modif in popup
        this.action.doAction('base.action_res_users_my', {
            viewType: 'form',
            props: {
                resId: userId
            }
        });
    }

    async onArchiveClick(user, ev) {
        // Stop propagation to prevent row click
        ev.stopPropagation();

        this.dialog.add(ConfirmationDialog, {
            body: _t('Are you sure you want to archive user "%s"? This user will not be able to log in to the system.', user.name),
            confirm: async () => {
                await this.orm.call("res.users", "action_archive", [[user.id]]);
                await this.loadUsers();
                this.computeStats();
            },
            cancel: () => {}
        });
    }

    onAddUserClick() {
        // Add User opens full form view (not popup)
        this.action.doAction('base.action_res_users', {
            viewType: 'form'
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

    formatDate(dateStr) {
        if (!dateStr) return '';
        try {
            const { DateTime } = luxon;
            const date = DateTime.fromJSDate(new Date(dateStr));
            return date.toLocaleString(DateTime.DATE_MED);
        } catch {
            return dateStr;
        }
    }
}
