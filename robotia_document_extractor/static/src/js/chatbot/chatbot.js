/** @odoo-module **/

import { Component, useState, useRef, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class ChatBot extends Component {
    static template = "robotia_document_extractor.ChatBot";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.chatMessages = useRef("chatMessages");
        this.chatInput = useRef("chatInput");

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

        onMounted(() => {
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
    addMessage(text, role = 'user') {
        const message = {
            id: Date.now(),
            text: text,
            role: role,
            timestamp: Date.now()
        };

        this.state.messages.push(message);
        this.scrollToBottom();
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
     * Get bot response (placeholder - will integrate with AI later)
     */
    async getBotResponse(userMessage) {
        // Simulate network delay
        await new Promise(resolve => setTimeout(resolve, 1000 + Math.random() * 1000));

        let response = "";

        // Simple keyword-based responses (placeholder)
        const lowerMessage = userMessage.toLowerCase();

        if (lowerMessage.includes("form 01") || lowerMessage.includes("registration")) {
            response = "Form 01 là mẫu đăng ký sử dụng chất kiểm soát. Bạn có thể upload file PDF và hệ thống sẽ tự động trích xuất thông tin bằng AI. Bạn có muốn tôi hướng dẫn chi tiết không?";
        } else if (lowerMessage.includes("form 02") || lowerMessage.includes("report")) {
            response = "Form 02 là mẫu báo cáo sử dụng chất kiểm soát. Tương tự Form 01, bạn chỉ cần upload PDF và hệ thống sẽ xử lý tự động. Bạn cần giúp gì về Form 02?";
        } else if (lowerMessage.includes("recent") || lowerMessage.includes("history")) {
            response = "Bạn có thể xem các tài liệu gần đây nhất trong phần Dashboard hoặc vào menu Documents > All Documents. Bạn muốn tôi mở trang đó cho bạn không?";
        } else if (lowerMessage.includes("substance") || lowerMessage.includes("chất")) {
            response = "Chất kiểm soát là các chất được quy định trong Nghị định thư Montreal. Hệ thống có danh sách đầy đủ các chất này trong Lookup & Summary > Controlled Substances. Bạn có muốn xem danh sách không?";
        } else if (lowerMessage.includes("help") || lowerMessage.includes("giúp")) {
            response = "Tôi có thể giúp bạn:\n• Hướng dẫn trích xuất Form 01/02\n• Giải thích về các chất kiểm soát\n• Xem thống kê và báo cáo\n• Tìm kiếm tài liệu\n\nBạn cần giúp gì cụ thể?";
        } else if (lowerMessage.includes("statistics") || lowerMessage.includes("thống kê")) {
            response = "Bạn có thể xem thống kê chi tiết tại:\n• Main Dashboard - tổng quan\n• HFC Dashboard - phân tích HFC\n• Thu gom - Tái chế - dữ liệu thu gom\n\nBạn muốn xem dashboard nào?";
        } else {
            response = `Cảm ơn bạn đã nhắn tin! Hiện tại tôi đang trong giai đoạn phát triển. Tôi có thể giúp bạn về:\n• Trích xuất Form 01/02\n• Thông tin về chất kiểm soát\n• Xem thống kê và dashboard\n\nBạn có câu hỏi gì khác không?`;
        }

        this.state.isTyping = false;
        this.addMessage(response, 'bot');

        // Update suggestions based on context
        this.updateSuggestions(lowerMessage);
    }

    /**
     * Update suggestions based on context
     */
    updateSuggestions(userMessage) {
        if (userMessage.includes("mẫu 01") || userMessage.includes("form 01")) {
            this.state.suggestions = [
                "Upload Mẫu 01",
                "Ví dụ Mẫu 01",
                "Các trường trong Mẫu 01"
            ];
        } else if (userMessage.includes("mẫu 02") || userMessage.includes("form 02")) {
            this.state.suggestions = [
                "Upload Mẫu 02",
                "Ví dụ Mẫu 02",
                "So sánh Mẫu 01 và 02"
            ];
        } else if (userMessage.includes("chất")) {
            this.state.suggestions = [
                "Danh sách chất",
                "Giá trị GWP",
                "Xem dashboard"
            ];
        } else {
            this.state.suggestions = [
                "Xem thống kê",
                "Tài liệu gần đây",
                "Hỗ trợ chất kiểm soát"
            ];
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
