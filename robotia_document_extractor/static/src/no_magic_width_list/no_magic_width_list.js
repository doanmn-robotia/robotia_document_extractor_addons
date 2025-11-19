import { registry } from "@web/core/registry";
import { X2ManyField, x2ManyField } from "@web/views/fields/x2many/x2many_field";
import { ListRenderer } from "@web/views/list/list_renderer";
import { listView } from "@web/views/list/list_view";

export class NoMagicColumnListRenderer extends ListRenderer {
    static useMagicColumnWidths = false

    setup() {
        super.setup()
    }

}

export class X2ManyNoMagicColumn extends X2ManyField {
    static components = {
        ...X2ManyField.components,
        ListRenderer: NoMagicColumnListRenderer
    }
}

registry.category("fields").add("x2many_no_magic_width_list", {
    ...x2ManyField,
    component: X2ManyNoMagicColumn
})

registry.category("views").add("no_magic_width_list", {
    ...listView,
    Renderer: NoMagicColumnListRenderer
});
