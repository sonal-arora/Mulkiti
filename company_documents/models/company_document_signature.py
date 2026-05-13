import secrets
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CompanyDocumentSignature(models.Model):
    _name = 'company.document.signature'
    _description = 'Document Signature Request'
    _order = 'create_date desc'

    document_id = fields.Many2one(
        comodel_name='company.document',
        string='Document',
        required=True,
        ondelete='cascade',
    )
    employee_id = fields.Many2one(
        comodel_name='hr.employee',
        string='Employee',
        required=True,
    )
    user_id = fields.Many2one(
        comodel_name='res.users',
        string='User',
        related='employee_id.user_id',
        store=True,
    )
    state = fields.Selection(
        selection=[
            ('pending', 'Pending'),
            ('signed', 'Signed'),
            ('declined', 'Declined'),
        ],
        string='Status',
        default='pending',
        tracking=True,
        required=True,
    )
    token = fields.Char(
        string='Token',
        default=lambda self: secrets.token_urlsafe(32),
        copy=False,
        readonly=True,
    )
    signature = fields.Binary(
        string='Signature',
        copy=False,
        attachment=True,
    )
    signed_date = fields.Datetime(
        string='Signed On',
        copy=False,
        readonly=True,
    )
    decline_reason = fields.Text(
        string='Decline Reason',
        copy=False,
    )
    sent_date = fields.Datetime(
        string='Sent On',
        default=fields.Datetime.now,
        readonly=True,
    )
    sign_url = fields.Char(
        string='Signature URL',
        compute='_compute_sign_url',
    )

    _sql_constraints = [
        ('unique_doc_employee', 'UNIQUE(document_id, employee_id)',
         'A signature request already exists for this employee and document.'),
    ]

    @api.depends('token', 'document_id')
    def _compute_sign_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for rec in self:
            rec.sign_url = '%s/document/sign/%s/%s' % (base_url, rec.document_id.id, rec.token)

    def action_send_email(self):
        """Send signature request email to employee."""
        self.ensure_one()
        template = self.env.ref(
            'company_documents.email_template_signature_request',
            raise_if_not_found=False,
        )
        if not template:
            raise UserError(_('Email template not found.'))

        email = (self.employee_id.work_email or
                 (self.user_id and self.user_id.email))
        if not email:
            raise UserError(_(
                'No email address found for employee %s.') % self.employee_id.name)

        template.send_mail(
            self.id,
            force_send=True,
            email_values={'email_to': email},
        )

    def action_mark_signed(self, signature_data):
        """Mark as signed with signature image."""
        self.write({
            'state': 'signed',
            'signature': signature_data,
            'signed_date': fields.Datetime.now(),
        })
        # Notify manager
        self._notify_manager_signed()

    def _notify_manager_signed(self):
        """Send notification to document manager when employee signs."""
        group = self.env.ref('company_documents.group_company_document_manager')
        managers = group.user_ids
        for manager in managers:
            self.document_id.message_post(
                body=_('%s has signed the document "%s".') % (
                    self.employee_id.name, self.document_id.name),
                message_type='notification',
                partner_ids=manager.partner_id.ids,
            )
