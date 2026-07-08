from odoo import _, fields, models
from odoo.exceptions import UserError


class PmsInitializeCancelWizard(models.TransientModel):
    _name = "pms.initialize.cancel.wizard"
    _description = "PMS Initialization Cancel Wizard"

    initialize_id = fields.Many2one("pms.initialize", required=True)
    cancel_reason = fields.Text(string="Cancellation Reason", required=True)

    def action_confirm(self):
        self.ensure_one()
        if not self.cancel_reason or not self.cancel_reason.strip():
            raise UserError(_("Please enter a cancellation reason."))
        self.initialize_id._do_cancel(self.cancel_reason)
        return {"type": "ir.actions.act_window_close"}
