/** @odoo-module */
import { NavBar } from "@web/webclient/navbar/navbar";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";

/**
 * NavSideBar Component
 *
 * Custom sidebar navigation component that extends the standard Odoo NavBar
 * to provide a vertical sidebar layout with app icons and menu sections.
 *
 * @extends NavBar
 */
export class NavSideBar extends NavBar {
    static template = "theme.NavSideBar"

    setup() {
        super.setup()
        this.user = user
        this.command = useService('command')
        this.company = useService('company')
    }

    /**
     * Opens the command palette for quick navigation
     *
     * @returns {Promise} Promise that resolves when the palette is opened
     */
    openCommand() {
        return this.command.openMainPalette({
            bypassEditableProtection: true,
            global: true,
        })
    }
}

