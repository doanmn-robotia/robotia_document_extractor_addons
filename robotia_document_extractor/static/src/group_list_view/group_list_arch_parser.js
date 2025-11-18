/** @odoo-module **/

import { evaluateExpr } from "@web/core/py_js/py";
import { ListArchParser } from "@web/views/list/list_arch_parser";

export class GroupedListArchParser extends ListArchParser {
    processButton(node) {
        const buttonInfo = super.processButton(node)
        this.processGroupFields(node, buttonInfo)
        return buttonInfo
    }
    parseFieldNode(node, models, modelName) {
        const fieldInfo = super.parseFieldNode(node, models, modelName);
        
        // Parse group information from options attribute
        
        this.processGroupFields(node, fieldInfo)
        return fieldInfo;
    }

    processGroupFields(node, fieldInfo) {
        const contextAttr = node.getAttribute("context");
        if (contextAttr) {
            const context = evaluateExpr(contextAttr);

            // Support both static label (group_header) and dynamic label (group_label_field)
            if (context.group_header) {
                fieldInfo.groupName = context.group_header;
                fieldInfo.hasGroupHeader = true;
            }

            // Dynamic group label from field
            if (context.group_label_field) {
                fieldInfo.groupLabelField = context.group_label_field;
                fieldInfo.hasGroupHeader = true;
            }

            if (context.group_start) {
                fieldInfo.groupStart = true;
            }

            if (context.group_end) {
                fieldInfo.groupEnd = true;
            }

            if (context.group_class) {
                fieldInfo.groupClass = context.group_class;
            }

        }
    }

}