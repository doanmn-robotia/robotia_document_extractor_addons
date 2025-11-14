import { ListController } from "@web/views/list/list_controller";
import { GroupedListArchParser } from "./group_list_arch_parser";
import { GroupedListRenderer } from "./group_list_renderer";
import { listView } from "@web/views/list/list_view";
import { registry } from "@web/core/registry";

export const groupedListView = {
    ...listView,
    ArchParser: GroupedListArchParser,
    Renderer: GroupedListRenderer
};

registry.category("views").add("grouped_list", groupedListView);
