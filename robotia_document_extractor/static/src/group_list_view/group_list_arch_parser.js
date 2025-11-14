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
        const optionsAttr = node.getAttribute("context");
        const text = node.getAttribute("add-label")
        if (optionsAttr) {
            const options = evaluateExpr(optionsAttr);

            if (options.group_header || text) {
                fieldInfo.groupName = options.group_header || text;
                fieldInfo.hasGroupHeader = true;
            }
            
            if (options.group_start) {
                fieldInfo.groupStart = true;
            }
            
            if (options.group_end) {
                fieldInfo.groupEnd = true;
            }

            if (options.group_class) {
                fieldInfo.groupClass = options.group_class;
            }
        
        }
    }

}