/** @odoo-module **/

import { registry } from "@web/core/registry";
import { SelectionField, selectionField } from "@web/views/fields/selection/selection_field";
import { _t } from "@web/core/l10n/translation";

export class CardSelectionField extends SelectionField {
    static template = "robotia_document_extractor.CardSelectionField";

    // Handle card click - update value directly
    onCardClick(value) {
        if (!this.props.readonly) {
            this.props.record.update({ [this.props.name]: value });
        }
    }

    // Add helper methods for card rendering
    getCardIcon(value) {
        const iconMap = {
            'viewer': 'fa-eye',
            'checker': 'fa-check-circle',
            'maker': 'fa-edit',
            'admin': 'fa-shield',
            'none': 'fa-ban'
        };
        return iconMap[value] || 'fa-user';
    }

    getCardColor(value) {
        const colorMap = {
            'viewer': 'blue',
            'checker': 'green',
            'maker': 'orange',
            'admin': 'purple',
            'none': 'gray'
        };
        return colorMap[value] || 'gray';
    }

    getCardDescription(value) {
        const descMap = {
            'viewer': _t('Can view documents and extractions (read-only)'),
            'checker': _t('Can review and validate extractions'),
            'maker': _t('Can create and edit document extractions'),
            'admin': _t('Full access to Document Extractor module including settings'),
            'none': _t('No Document Extractor access')
        };
        return descMap[value] || '';
    }
}

export const cardSelectionField = {
    ...selectionField,
    component: CardSelectionField,
};

registry.category("fields").add("card_selection", cardSelectionField);
