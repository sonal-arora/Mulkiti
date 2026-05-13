/** @odoo-module **/
import { FormController } from "@web/views/form/form_controller";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";

patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);
        this.rpc = useService("rpc");
    },

    async onWillStart() {
        await super.onWillStart(...arguments);
        if (
            this.props.resModel === "company.document" &&
            this.props.resId
        ) {
            try {
                await this.rpc("/company-documents/view/" + this.props.resId, {});
            } catch (_e) {
                // ignore tracking errors
            }
        }
    },
});
