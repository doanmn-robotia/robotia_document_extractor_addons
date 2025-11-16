/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, xml } from "@odoo/owl";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

/**
 * PDF URL Viewer Widget
 * Displays PDF from URL in an iframe
 * Works with both saved records (res_id > 0) and unsaved records (public attachment)
 */
export class PdfUrlViewer extends Component {
    static template = xml`
        <div class="o_field_pdf_url_viewer" style="width: 100%; height: 100%;">
            <t t-if="props.record.data[props.name]">
                <iframe
                    t-att-src="props.record.data[props.name]"
                    type="application/pdf"
                    style="width: 100%; height: 100%; border: none;"
                    title="PDF Preview"
                />
            </t>
            <t t-else="">
                <div class="alert alert-info text-center" style="margin: 20px;">
                    <i class="fa fa-file-pdf-o fa-3x mb-2"/>
                    <p>No PDF file uploaded</p>
                </div>
            </t>
        </div>
    `;

    static props = {
        ...standardFieldProps,
    };
}

registry.category("fields").add("pdf_url_viewer", {
    component: PdfUrlViewer,
    additionalClasses: ['w-100', 'h-100']
});
