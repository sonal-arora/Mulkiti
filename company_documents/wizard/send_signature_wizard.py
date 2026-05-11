from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SendSignatureWizard(models.TransientModel):
    _name = 'company.document.send.signature.wizard'
    _description = 'Send Document for Signature'

    document_id = fields.Many2one(
        comodel_name='company.document',
        string='Document',
        required=True,
        readonly=True,
    )
    employee_ids = fields.Many2many(
        comodel_name='hr.employee',
        string='Employees',
        required=True,
        domain="[('active', '=', True), ('company_id', '=', company_id)]",
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        related='document_id.company_id',
    )
    message = fields.Text(
        string='Message to Employee',
        default='Please review and sign the attached document.',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self.env.context.get('active_id'):
            res['document_id'] = self.env.context['active_id']
        return res

    def action_send(self):
        """Create signature requests and send emails."""
        self.ensure_one()
        if not self.employee_ids:
            raise UserError(_('Please select at least one employee.'))

        sent_count = 0
        skipped = []

        for employee in self.employee_ids:
            # Check if already sent
            existing = self.env['company.document.signature'].search([
                ('document_id', '=', self.document_id.id),
                ('employee_id', '=', employee.id),
                ('state', '!=', 'declined'),
            ], limit=1)

            if existing:
                skipped.append(employee.name)
                continue

            # Create signature request
            sig = self.env['company.document.signature'].create({
                'document_id': self.document_id.id,
                'employee_id': employee.id,
            })
            # Send email
            try:
                sig.with_context(wizard_message=self.message).action_send_email()
                sent_count += 1
            except Exception:
                skipped.append(employee.name)

        msg = _('Signature request sent to %d employee(s).') % sent_count
        if skipped:
            msg += _('\nSkipped (already sent or no email): %s') % ', '.join(skipped)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Sent!'),
                'message': msg,
                'type': 'success',
                'sticky': False,
            },
        }
