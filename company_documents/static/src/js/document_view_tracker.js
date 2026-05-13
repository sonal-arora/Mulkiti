/** @odoo-module **/
import { FormController } from "@web/views/form/form_controller";
import { patch } from "@web/core/utils/patch";

patch(FormController.prototype, {
    async onWillStart() {
        await super.onWillStart(...arguments);
        if (this.props.resModel === "company.document" && this.props.resId) {
            try {
                await fetch("/company-documents/view/" + this.props.resId, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "call", params: {} }),
                });
            } catch (_e) {
                // ignore tracking errors silently
            }
        }
    },
});
