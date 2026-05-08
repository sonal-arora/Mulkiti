from odoo import fields, models, _
from odoo.exceptions import UserError


class HrLeaveRefuseWizard(models.TransientModel):
    _name = 'hr.leave.refuse.wizard'
    _description = 'Leave Refusal Reason'

    leave_ids = fields.Many2many(
        comodel_name='hr.leave',
        string='Leave Requests',
    )
    reason = fields.Text(
        string='Reason for Refusal',
        # required enforced at view level only — not ORM level
        # so wizard.create() works without pre-filling reason
    )

    def action_refuse(self):
        """Store reason on each leave then perform the actual refusal."""
        self.ensure_one()
        if not self.leave_ids:
            raise UserError(_('No leave request found.'))
        if not (self.reason or '').strip():
            raise UserError(_('Please enter a reason for refusal.'))

        # Save reason on each leave record
        self.leave_ids.write({'refuse_reason': self.reason})

        # Call actual action_refuse bypassing the wizard trigger
        self.leave_ids.with_context(skip_refuse_wizard=True).action_refuse()

        return {'type': 'ir.actions.act_window_close'}
