from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CompanyDocument(models.Model):
    _name = 'company.document'
    _description = 'Company Document'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, name'

    name = fields.Char(
        string='Document Title',
        required=True,
        tracking=True,
    )
    sequence = fields.Integer(string='Sequence', default=10)
    category_id = fields.Many2one(
        comodel_name='company.document.category',
        string='Category',
        tracking=True,
    )
    description = fields.Html(
        string='Description',
        sanitize=True,
    )
    visibility = fields.Selection(
        selection=[
            ('public', 'Public (All Employees)'),
            ('private', 'Private (HR / Admin Only)'),
        ],
        string='Visibility',
        required=True,
        default='public',
        tracking=True,
    )
    document_file = fields.Binary(
        string='Document File',
        attachment=True,
    )
    document_filename = fields.Char(string='File Name')
    document_url = fields.Char(string='External URL')
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    active = fields.Boolean(string='Active', default=True)
    published_date = fields.Date(
        string='Published Date',
        default=fields.Date.today,
        tracking=True,
    )
    tag_ids = fields.Many2many(
        comodel_name='company.document.category',
        string='Tags',
        relation='company_document_tag_rel',
        column1='document_id',
        column2='category_id',
    )
    notification_sent = fields.Boolean(
        string='Notification Sent',
        default=False,
        copy=False,
        help='Whether email notification has been sent to employees for this document.',
    )
    notification_count = fields.Integer(
        string='Notified Employees',
        default=0,
        copy=False,
    )
    signature_ids = fields.One2many(
        comodel_name='company.document.signature',
        inverse_name='document_id',
        string='Signature Requests',
        readonly=True,
    )
    signature_count = fields.Integer(
        string='Signatures',
        compute='_compute_signature_count',
    )

    @api.depends('signature_ids', 'signature_ids.state')
    def _compute_signature_count(self):
        for doc in self:
            doc.signature_count = len(doc.signature_ids.filtered(
                lambda s: s.state == 'signed'))

    log_ids = fields.One2many(
        comodel_name='company.document.log',
        inverse_name='document_id',
        string='View/Download History',
        readonly=True,
    )
    view_count = fields.Integer(
        string='Total Views',
        compute='_compute_view_count',
        store=True,
    )
    download_count = fields.Integer(
        string='Total Downloads',
        compute='_compute_view_count',
        store=True,
    )

    # ─────────────────────────────────────────────────────────────────────────
    # View / Download Tracking
    # ─────────────────────────────────────────────────────────────────────────

    @api.depends('log_ids', 'log_ids.action')
    def _compute_view_count(self):
        for doc in self:
            doc.view_count = len(doc.log_ids.filtered(lambda l: l.action == 'viewed'))
            doc.download_count = len(doc.log_ids.filtered(lambda l: l.action == 'downloaded'))

    def action_log_view(self):
        """Called when employee opens/reads the document."""
        self.ensure_one()
        # Avoid duplicate logs for same user same day
        today_log = self.env['company.document.log'].sudo().search([
            ('document_id', '=', self.id),
            ('user_id', '=', self.env.user.id),
            ('action', '=', 'viewed'),
            ('date', '>=', fields.Datetime.today()),
        ], limit=1)
        if not today_log:
            self.env['company.document.log'].sudo().create({
                'document_id': self.id,
                'user_id': self.env.user.id,
                'action': 'viewed',
            })
        return True

    def action_log_download(self):
        """Called when employee downloads the document."""
        self.ensure_one()
        self.env['company.document.log'].sudo().create({
            'document_id': self.id,
            'user_id': self.env.user.id,
            'action': 'downloaded',
        })
        # Return the actual file download
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/company.document/%d/document_file/%s?download=true' % (
                self.id, self.document_filename or 'document'
            ),
            'target': 'self',
        }

    def action_view_history(self):
        """Open full history for this document."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Document History — %s' % self.name,
            'res_model': 'company.document.log',
            'view_mode': 'list',
            'domain': [('document_id', '=', self.id)],
            'context': {'default_document_id': self.id},
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Email Notification
    # ─────────────────────────────────────────────────────────────────────────

    def action_view_notification_info(self):
        """Show info about the notification that was sent."""
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Notification Info'),
                'message': _('Email notification was sent to %d employee(s) for this document.') % self.notification_count,
                'type': 'info',
                'sticky': True,
            },
        }

    def action_send_notification(self):
        """Send email notification to all active employees about this document."""
        self.ensure_one()
        if self.visibility != 'public':
            raise UserError(_('You can only send notifications for Public documents.'))

        # Get all active employees with linked users (company email)
        employees = self.env['hr.employee'].sudo().search([
            ('company_id', '=', self.company_id.id),
            ('active', '=', True),
        ])

        template = self.env.ref(
            'company_documents.email_template_document_notification',
            raise_if_not_found=False,
        )

        email_list = []
        for emp in employees:
            email = emp.work_email or (emp.user_id and emp.user_id.email)
            if not email:
                continue
            email_list.append(email)
            if template:
                template.with_context(
                    recipient_name=emp.name,
                    recipient_email=email,
                ).send_mail(
                    self.id,
                    force_send=True,
                    email_values={'email_to': email},
                )

        if not email_list:
            raise UserError(_('No employee email addresses found to send notification.'))

        if not template:
            self._send_simple_email(email_list)

        self.write({
            'notification_sent': True,
            'notification_count': len(set(email_list)),
        })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Notification Sent'),
                'message': _('Email sent to %d employees successfully!') % len(set(email_list)),
                'type': 'success',
                'sticky': False,
            },
        }

    def _send_simple_email(self, email_list):
        """Fallback simple email sender."""
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        doc_url = '%s/odoo/company-documents' % base_url

        body = """
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background-color: #875A7B; padding: 20px; text-align: center;">
                <h2 style="color: white; margin: 0;">New Document Published</h2>
            </div>
            <div style="padding: 30px; background-color: #f9f9f9;">
                <h3 style="color: #333;">%s</h3>
                %s
                <p style="color: #666;">
                    <strong>Category:</strong> %s<br/>
                    <strong>Published:</strong> %s
                </p>
                <div style="text-align: center; margin-top: 30px;">
                    <a href="%s"
                       style="background-color: #875A7B; color: white; padding: 12px 30px;
                              text-decoration: none; border-radius: 5px; font-weight: bold;">
                        View Document
                    </a>
                </div>
            </div>
            <div style="padding: 15px; text-align: center; color: #999; font-size: 12px;">
                This is an automated notification from %s.
            </div>
        </div>
        """ % (
            self.name,
            self.description or '',
            self.category_id.name if self.category_id else 'General',
            self.published_date or '',
            doc_url,
            self.company_id.name,
        )

        mail_values = {
            'subject': _('New Document Published: %s') % self.name,
            'body_html': body,
            'email_from': self.env.company.email or self.env.user.email,
            'email_to': ','.join(set(email_list)),
            'auto_delete': True,
        }
        self.env['mail.mail'].sudo().create(mail_values).send()

    @api.model
    def get_public_documents(self):
        """Return public documents for portal/employee view."""
        return self.search([
            ('visibility', '=', 'public'),
            ('company_id', 'in', self.env.companies.ids),
        ])
