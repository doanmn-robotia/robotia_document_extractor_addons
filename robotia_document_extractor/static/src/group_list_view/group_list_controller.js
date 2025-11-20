/** @odoo-module **/

import { GroupedListArchParser } from "./group_list_arch_parser";
import { GroupedListRenderer } from "./group_list_renderer";
import { listView } from "@web/views/list/list_view";
import { registry } from "@web/core/registry";

// Patch the default list view to support grouped headers
const patchedListView = {
    ...listView,
    ArchParser: GroupedListArchParser,
    Renderer: GroupedListRenderer
};

// Override the default "list" view registration
registry.category("views").add("list", patchedListView, { force: true });
