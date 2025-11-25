/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { aceField, AceField } from "@web/views/fields/ace/ace_field";

/**
 * Ace Copy Field Widget
 * Extends standard AceField with copy to clipboard and download JSON features
 */
export class AceCopyField extends AceField {
    static template = "robotia_document_extractor.AceCopyField";

    setup() {
        super.setup();
        this.notification = useService("notification");
    }

    /**
     * Get current content from editor
     */
    get content() {
        return this.editedValue || this.state.initialValue || "";
    }

    /**
     * Copy content to clipboard and show notification
     */
    async onCopyClick() {
        try {
            await navigator.clipboard.writeText(this.content);
            this.notification.add(_t("Đã copy!"), { type: "success" });
        } catch (error) {
            this.notification.add(_t(`Copy failed: ${error.message}`), { type: "danger" });
        }
    }

    /**
     * Download content as JSON file with dynamic filename from record
     */
    onDownloadClick() {
        try {
            // Create blob from content
            const blob = new Blob([this.content], { type: 'application/json' });

            // Generate dynamic filename from record name
            const recordName = this.props.record.data.name || 'extraction';
            const filename = `${recordName}_log.json`;

            // Create temporary anchor element and trigger download
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = filename;
            document.body.appendChild(link);
            link.click();

            // Cleanup
            document.body.removeChild(link);
            URL.revokeObjectURL(url);
        } catch (error) {
            this.notification.add(_t(`Download failed: ${error.message}`), { type: "danger" });
        }
    }
}

export const aceCopyField = {
    ...aceField,
    component: AceCopyField,
    additionalClasses: ['o_field_ace']
};

registry.category("fields").add("ace_copy", aceCopyField);
