/** @odoo-module **/

import { Component, useState, useRef, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { rpc } from "@web/core/network/rpc";

export class ChatBot extends Component {
    static template = "robotia_document_extractor.ChatBot";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.chatMessages = useRef("chatMessages");
        this.chatInput = useRef("chatInput");

        // Track conversation ID for multi-turn chat
        this.conversationId = null;

        this.state = useState({
            messages: [],
            inputMessage: "",
            isTyping: false,
            suggestions: [
                "Xem thống kê",
                "Tài liệu gần đây",
                "Hỗ trợ chất kiểm soát"
            ]
        });

        onMounted(async () => {
            // Load conversation ID from localStorage
            const savedConversationId = localStorage.getItem('chatbot_conversation_id');
            if (savedConversationId) {
                this.conversationId = parseInt(savedConversationId);
                await this.loadConversationHistory();
            }

            // Focus input on mount
            if (this.chatInput.el) {
                this.chatInput.el.focus();
            }
        });
    }

    /**
     * Format timestamp to readable time
     */
    formatTime(timestamp) {
        const date = new Date(timestamp);
        const hours = date.getHours().toString().padStart(2, '0');
        const minutes = date.getMinutes().toString().padStart(2, '0');
        return `${hours}:${minutes}`;
    }

    /**
     * Scroll chat to bottom
     */
    scrollToBottom() {
        setTimeout(() => {
            if (this.chatMessages.el) {
                this.chatMessages.el.scrollTop = this.chatMessages.el.scrollHeight;
            }
        }, 50);
    }

    /**
     * Add message to chat
     */
    addMessage(text, role = 'user', action = null) {
        const message = {
            id: Date.now(),
            text: text,
            role: role,
            timestamp: Date.now(),
            action: action  // Store action data if present
        };

        this.state.messages.push(message);
        this.scrollToBottom();
        return message;
    }

    /**
     * Send message
     */
    async sendMessage() {
        const message = this.state.inputMessage.trim();
        if (!message) return;

        // Add user message
        this.addMessage(message, 'user');
        this.state.inputMessage = "";

        // Show typing indicator
        this.state.isTyping = true;
        this.scrollToBottom();

        try {
            // Simulate bot response (replace with actual AI call later)
            await this.getBotResponse(message);
        } catch (error) {
            console.error("Error getting bot response:", error);
            this.notification.add("Failed to get response from ChatBot", {
                type: "danger"
            });
            this.state.isTyping = false;
        }
    }

    /**
     * Get bot response from AI service using Gemini Chat API
     */
    async getBotResponse(userMessage) {
        try {
            // Call real API endpoint
            const result = await rpc("/chatbot/message", {
                message: userMessage,
                conversation_id: this.conversationId
            });

            // Store conversation ID for multi-turn chat
            if (result.conversation_id) {
                this.conversationId = result.conversation_id;
                // Save to localStorage for persistence
                localStorage.setItem('chatbot_conversation_id', result.conversation_id);
            }

            // Hide typing indicator
            this.state.isTyping = false;

            // Add assistant message with action data (don't execute yet)
            this.addMessage(result.message, 'bot', result.action);

            // Update suggestions from AI
            if (result.suggestions && result.suggestions.length > 0) {
                this.state.suggestions = result.suggestions;
            }

        } catch (error) {
            console.error("Error getting bot response:", error);
            this.state.isTyping = false;
            this.addMessage("Xin lỗi, đã có lỗi xảy ra. Vui lòng thử lại.", 'bot');
            this.notification.add("Không thể kết nối với Trợ lý AI", {
                type: "danger"
            });
        }
    }

    /**
     * Load conversation history from backend
     */
    async loadConversationHistory() {
        try {
            const result = await rpc("/chatbot/conversation/history", {
                conversation_id: this.conversationId
            });

            if (result.error) {
                console.warn("Could not load conversation history:", result.error);
                // Clear invalid conversation ID
                this.conversationId = null;
                localStorage.removeItem('chatbot_conversation_id');
                return;
            }

            // Restore messages
            this.state.messages = result.messages.map(msg => ({
                id: msg.id,
                text: msg.content,
                role: msg.role,
                timestamp: new Date(msg.timestamp).getTime(),
                action: msg.action
            }));

            this.scrollToBottom();
        } catch (error) {
            console.error("Error loading conversation history:", error);
            // Clear invalid conversation ID on error
            this.conversationId = null;
            localStorage.removeItem('chatbot_conversation_id');
        }
    }

    /**
     * Execute action from button click
     */
    async executeActionFromButton(action) {
        if (!action) return;

        try {
            await this.executeAction(action);
        } catch (error) {
            console.error('Error executing action from button:', error);
            this.notification.add('Không thể thực hiện hành động', {
                type: 'warning'
            });
        }
    }

    /**
     * Execute action returned by AI
     */
    async executeAction(action) {
        try {
            // Validate action has required fields
            if (!action || !action.type || !action.params) {
                console.warn('Invalid action format:', action);
                return;
            }

            switch (action.type) {
                case 'open_dashboard':
                    // Map dashboard names to action tags
                    const dashboardMap = {
                        'main': 'document_extractor.dashboard',
                        'hfc': 'document_extractor.hfc_dashboard',
                        'substance': 'document_extractor.substance_dashboard',
                        'company': 'document_extractor.company_dashboard',
                        'equipment': 'document_extractor.equipment_dashboard',
                        'recovery': 'document_extractor.recovery_dashboard',
                    };

                    const dashboardTag = dashboardMap[action.params.dashboard];
                    if (dashboardTag) {
                        // Pass only relevant params (exclude 'dashboard' key)
                        const { dashboard, ...dashboardParams } = action.params;

                        await this.action.doAction({
                            type: 'ir.actions.client',
                            tag: dashboardTag,
                            params: dashboardParams  // Pass substance_id, organization_id, etc.
                        });
                    }
                    break;

                case 'view_substance':
                    // Open substance form view
                    if (action.params.substance_id) {
                        await this.action.doAction({
                            type: 'ir.actions.act_window',
                            res_model: 'controlled.substance',
                            res_id: action.params.substance_id,
                            views: [[false, 'form']],
                            target: 'current'
                        });
                    }
                    break;

                case 'search_documents':
                    // Open documents list with search filter
                    await this.action.doAction({
                        type: 'ir.actions.act_window',
                        name: 'Search Results',
                        res_model: 'document.extraction',
                        views: [[false, 'list'], [false, 'form']],
                        domain: action.params.domain || [],
                        context: action.params.context || {},
                        target: 'current'
                    });
                    break;

                case 'create_document':
                    // Open form to create new document
                    const docType = action.params.document_type || '01';
                    const actionName = docType === '01' ? 'action_document_extraction_registration' : 'action_document_extraction_report';

                    // Open the predefined action (has correct context)
                    await this.action.doAction(actionName, {
                        additionalContext: {
                            default_document_type: docType
                        }
                    });
                    break;

                default:
                    console.warn('Unknown action type:', action.type);
            }
        } catch (error) {
            console.error('Error executing action:', error);
            this.notification.add(`Không thể thực hiện hành động: ${action.type}`, {
                type: 'warning'
            });
        }
    }

    /**
     * Send quick action message
     */
    sendQuickAction(message) {
        this.state.inputMessage = message;
        this.sendMessage();
    }

    /**
     * Handle input keydown (Enter to send)
     */
    onInputKeydown(ev) {
        if (ev.key === 'Enter' && !ev.shiftKey) {
            ev.preventDefault();
            this.sendMessage();
        }
    }
}

// Register the ChatBot action
registry.category("actions").add("document_extractor.chatbot", ChatBot);
