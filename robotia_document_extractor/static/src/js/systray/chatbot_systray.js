/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/**
 * Systray button to open AI Assistant chatbot
 *
 * Features:
 * - Gemini-like multi-color sparkle icon
 * - Animated pulse effect on hover
 * - Opens chatbot in full-screen mode
 */
export class ChatbotSystray extends Component {
    static template = "robotia_document_extractor.ChatbotSystray";

    setup() {
        this.action = useService("action");
    }

    /**
     * Open AI Assistant chatbot
     */
    openChatbot() {
        this.action.doAction({
            type: 'ir.actions.client',
            tag: 'document_extractor.chatbot',
            target: 'current',
        });
    }
}

// Register in systray with middle sequence (20-30 range)
registry.category("systray").add("chatbot_ai_assistant", {
    Component: ChatbotSystray,
}, { sequence: 25 });
