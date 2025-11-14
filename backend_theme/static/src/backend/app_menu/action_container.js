/** @odoo-module */
import { NavSideBar } from "./search_apps";
import { ActionContainer } from "@web/webclient/actions/action_container";
import { useState, useSubEnv, xml } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { WebClient } from "@web/webclient/webclient";
import { rpc } from "@web/core/network/rpc";

/**
 * WebClient Patch
 *
 * Extends WebClient to manage the navigation sidebar state and provide
 * toggle functionality throughout the application.
 */
patch(WebClient.prototype, {
    setup() {
        super.setup()

        // Initialize navbar state
        this.navbarState = useState({
            isOpen: true
        })

        this.rpc = rpc

        // Provide navbar state and toggle function to child components
        useSubEnv({
            navbarState: this.navbarState,
            toggleNavBar: () => {
                this.navbarState.isOpen = !this.navbarState.isOpen
            }
        })
    }
})

/**
 * ActionContainer Patch
 *
 * Extends ActionContainer to integrate the NavSideBar component
 * and manage its visibility based on device size and user preferences.
 */
patch(ActionContainer.prototype, {
    setup() {
        super.setup()
        this.navbarState = useState(this.env.navbarState)
    }
})

// Add NavSideBar to ActionContainer components
ActionContainer.components = {
    ...ActionContainer.components,
    NavSideBar
}

// Override ActionContainer template to include NavSideBar
ActionContainer.template = xml`
<t t-name="web.ActionContainer">
    <div class="o_action_manager">
        <NavSideBar t-if="!env.isSmall and navbarState.isOpen"/>
        <t t-if="info.Component" t-component="info.Component" className="'o_action'" t-props="info.componentProps" t-key="info.id"/>
    </div>
</t>`;

