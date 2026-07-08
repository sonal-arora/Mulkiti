from odoo import _, fields, models
from odoo.exceptions import UserError


class PmsRejectWizard(models.TransientModel):
    _name = "pms.reject.wizard"
    _description = "PMS Reject / Cancel / Reset Wizard"

    appraisal_id = fields.Many2one("pms.appraisal", required=True)
    is_cancel = fields.Boolean(default=False)
    is_reset_draft = fields.Boolean(default=False)
    cancel_reason = fields.Text(string="Reason", required=True)

    def action_confirm(self):
        self.ensure_one()
        if not self.cancel_reason or not self.cancel_reason.strip():
            raise UserError(_("Please enter a reason."))
        if self.is_reset_draft:
            self.appraisal_id._do_reset_draft(self.cancel_reason)
        elif self.is_cancel:
            self.appraisal_id._do_cancel(self.cancel_reason)
        else:
            self.appraisal_id._do_reject(self.cancel_reason)
        return {"type": "ir.actions.act_window_close"}
