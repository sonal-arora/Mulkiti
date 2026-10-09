from datetime import timedelta

from markupsafe import Markup

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

# Content of a Published document is locked: set it back to Draft to edit.
LOCKED_FIELDS = {
    'name', 'folder_id', 'category_id', 'tag_ids', 'description', 'document_file',
    'document_filename', 'document_url', 'company_id', 'published_date',
}

# Marks the temporary attachments created by /company-documents/upload.
UPLOAD_TAG = 'company_documents.pending_upload'


class CompanyDocument(models.Model):
    _name = 'company.document'
    _description = 'Company Document'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, name'

    folder_id = fields.Many2one(
        comodel_name='company.document.folder',
        string='Folder',
        index=True,
        tracking=True,
        domain="[('company_id', '=', company_id)]",
        ondelete='restrict',
    )

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
    # Document status. Kept under the technical name "visibility" (values
    # public/private) so existing data and record rules stay unchanged.
    # Who sees a published document is decided by its folder.
    visibility = fields.Selection(
        selection=[
            ('private', 'Draft'),
            ('public', 'Published'),
        ],
        string='Status',
        required=True,
        default='private',
        tracking=True,
        help='Draft: only HR / Document Managers can see it.\n'
             'Published: visible to the users of its folder.',
    )
    # Managers only: employees get the file through the tracking controllers,
    # which enforce the folder's Allow Preview / Allow Download options. This
    # also closes /web/content/company.document/<id>/document_file for them.
    document_file = fields.Binary(
        string='Document File',
        attachment=True,
        groups='company_documents.group_company_document_manager',
    )
    document_filename = fields.Char(string='File Name')
    # Set by the form's upload widget: id of a temporary attachment uploaded
    # through /company-documents/upload (multipart), moved into document_file
    # on save. This keeps the file content out of the JSON-RPC calls.
    upload_attachment_id = fields.Integer(
        string='Uploaded File',
        compute='_compute_upload_attachment_id',
        inverse='_inverse_upload_attachment_id',
        groups='company_documents.group_company_document_manager',
    )
    has_file = fields.Boolean(string='Has File', compute='_compute_has_file', compute_sudo=True)
    can_preview = fields.Boolean(string='Can Preview', compute='_compute_file_access')
    can_download = fields.Boolean(string='Can Download', compute='_compute_file_access')
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

    @api.constrains('folder_id', 'company_id')
    def _check_folder_company(self):
        for doc in self:
            if doc.folder_id and doc.folder_id.company_id != doc.company_id:
                raise ValidationError(_(
                    'Document "%(doc)s" belongs to %(doc_company)s but folder '
                    '"%(folder)s" belongs to %(folder_company)s.',
                    doc=doc.name, doc_company=doc.company_id.name,
                    folder=doc.folder_id.name, folder_company=doc.folder_id.company_id.name,
                ))

    @api.onchange('folder_id')
    def _onchange_folder_id(self):
        if self.folder_id:
            self.company_id = self.folder_id.company_id

    def _compute_upload_attachment_id(self):
        self.upload_attachment_id = 0

    def _inverse_upload_attachment_id(self):
        # Handled in create() / write() by _pop_uploaded_file().
        pass

    def _pop_uploaded_file(self, vals):
        """Replace upload_attachment_id in vals by the content of that
        temporary attachment; return the attachment to delete after saving."""
        attachment_id = vals.pop('upload_attachment_id', False)
        if not attachment_id:
            return self.env['ir.attachment']
        attachment = self.env['ir.attachment'].sudo().browse(attachment_id).exists()
        if (not attachment
                or attachment.description != UPLOAD_TAG
                or attachment.res_model != self._name
                or attachment.res_id
                or attachment.create_uid != self.env.user):
            raise UserError(_('The uploaded file was not found. Please upload it again.'))
        vals['document_file'] = attachment.datas
        vals.setdefault('document_filename', attachment.name)
        return attachment

    @api.autovacuum
    def _gc_pending_uploads(self):
        """Delete files uploaded in a form that was never saved."""
        self.env['ir.attachment'].sudo().search([
            ('res_model', '=', self._name),
            ('res_id', '=', 0),
            ('description', '=', UPLOAD_TAG),
            ('create_date', '<', fields.Datetime.now() - timedelta(days=1)),
        ]).unlink()

    # No @api.depends on document_file on purpose: a dependency makes the form
    # fire an onchange on upload, which re-sends the whole base64 file in the
    # RPC and crashes the browser (Out of memory) on large files. has_file is
    # recomputed on read, so it updates once the record is saved.
    def _compute_has_file(self):
        for doc in self:
            doc.has_file = bool(doc.document_file)

    @api.depends('folder_id.allow_preview', 'folder_id.allow_download')
    def _compute_file_access(self):
        # The Preview / Download / Open Link buttons follow the folder options
        # for everyone, managers included, so what HR sees is what employees
        # see. Managers can still get the file from the form's file field.
        for doc in self:
            doc.can_preview, doc.can_download = doc._get_folder_file_options()

    def _get_folder_file_options(self):
        """(allow_preview, allow_download) set on the document's folder."""
        self.ensure_one()
        folder = self.sudo().folder_id
        if not folder:
            return True, True
        return folder.allow_preview, folder.allow_download

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

    def web_read(self, specification):
        # The form view loads a single record through web_read, so this is
        # where an employee "opening" a document is recorded. Document
        # managers are skipped: they open documents to edit them, which
        # would inflate the employee view count.
        result = super().web_read(specification)
        if (len(self) == 1
                and not self.env.context.get('skip_document_view_log')
                and not self.env.user.has_group('company_documents.group_company_document_manager')):
            self.action_log_view()
        return result

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
        """Download through the tracking controller, which writes the log."""
        self.ensure_one()
        if not self.has_file:
            raise UserError(_('This document has no file to download.'))
        if not self.can_download:
            raise UserError(_('Download is not allowed for the documents of this folder.'))
        return {
            'type': 'ir.actions.act_url',
            'url': '/company-documents/download/%d' % self.id,
            'target': 'self',
        }

    def action_preview(self):
        """Open the file in the browser viewer (new tab), logged as a view."""
        self.ensure_one()
        if not self.has_file:
            raise UserError(_('This document has no file to preview.'))
        if not self.can_preview:
            raise UserError(_('Preview is not allowed for the documents of this folder.'))
        return {
            'type': 'ir.actions.act_url',
            'url': '/company-documents/preview/%d' % self.id,
            'target': 'new',
        }

    def action_open_link(self):
        """Open an External URL document (new tab), logged as a view.
        Follows the folder's Allow Preview option."""
        self.ensure_one()
        if not self.document_url:
            raise UserError(_('This document has no external link.'))
        if not self.can_preview:
            raise UserError(_('Viewing is not allowed for the documents of this folder.'))
        self.action_log_view()
        return {
            'type': 'ir.actions.act_url',
            'url': self.document_url,
            'target': 'new',
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

    def action_publish(self):
        # Draft -> Published notifies the folder's users through write()
        self.write({'visibility': 'public', 'published_date': fields.Date.today()})

    def action_set_draft(self):
        self.write({'visibility': 'private'})

    def action_send_notification(self):
        """Manually notify the users who can access this document."""
        self.ensure_one()
        if self.visibility != 'public':
            raise UserError(_('You can only send notifications for Published documents.'))

        count = self._notify_document_update('manual', manual=True)
        if not count:
            raise UserError(_('No users have access to this document, nobody to notify.'))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Notification Sent'),
                'message': _('Notification sent to %d user(s).') % count,
                'type': 'success',
                'sticky': False,
            },
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Automatic notification on add / update
    # ─────────────────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [dict(vals) for vals in vals_list]
        uploads = self.env['ir.attachment']
        for vals in vals_list:
            uploads |= self._pop_uploaded_file(vals)
        docs = super().create(vals_list)
        uploads.unlink()
        if not self.env.context.get('skip_document_notification'):
            docs._notify_document_update('added')
        return docs

    def write(self, vals):
        vals = dict(vals)
        uploads = self._pop_uploaded_file(vals)
        if (LOCKED_FIELDS & vals.keys()
                and vals.get('visibility') != 'private'
                and not self.env.context.get('document_allow_published_edit')):
            published = self.filtered(lambda d: d.visibility == 'public')
            if published:
                raise UserError(_(
                    'Document "%s" is Published and cannot be edited. '
                    'Click "Set to Draft" first, make your changes, then Publish again.',
                    published[0].name,
                ))

        # Editing is only possible in Draft, so the folder's users are notified
        # when a document is (re)published.
        newly_published = self.browse()
        if vals.get('visibility') == 'public' and not self.env.context.get('skip_document_notification'):
            newly_published = self.filtered(lambda d: d.visibility != 'public')
        announced_before = {doc.id: doc.notification_sent for doc in newly_published}
        res = super().write(vals)
        uploads.unlink()
        for doc in newly_published:
            doc._notify_document_update('updated' if announced_before[doc.id] else 'added')
        return res

    def _get_notification_users(self):
        """Users who can see this document, minus the person making the change."""
        self.ensure_one()
        if self.folder_id:
            users = self.folder_id._get_recipient_users()
        else:
            employees = self.env['hr.employee'].sudo().search([
                ('company_id', '=', self.company_id.id),
                ('user_id', '!=', False),
            ])
            users = employees.user_id.filtered(lambda u: u.active and not u.share)
        return users - self.env.user

    def _notify_document_update(self, change, manual=False):
        """Email + Odoo inbox notification to the users of the document folder.

        Automatic notifications only go out for public, active documents in a
        folder with "Notify on Update" enabled. Returns the number of users
        notified (for a single document).
        """
        count = 0
        for doc in self:
            if doc.visibility != 'public' or not doc.active:
                continue
            if not manual and not (doc.folder_id and doc.folder_id.notify_on_update):
                continue
            users = doc._get_notification_users()
            if not users:
                continue
            doc._send_update_notification(users, change)
            doc.with_context(skip_document_notification=True).write({
                'notification_sent': True,
                'notification_count': len(users),
            })
            count = len(users)
        return count

    def _send_update_notification(self, users, change):
        self.ensure_one()
        titles = {
            'added': _('New Document Added'),
            'updated': _('Document Updated'),
            'manual': _('Please Review This Document'),
        }
        messages = {
            'added': _('A new document has been added to %s.'),
            'updated': _('This document has been updated in %s.'),
            'manual': _('Please review this document in %s.'),
        }
        folder_name = self.folder_id.name or _('Company Documents')
        title = titles[change]
        message = messages[change] % folder_name
        doc_url = '%s/odoo/company-documents/%d' % (self.get_base_url(), self.id)

        # Odoo inbox: message_post routes each user by their own preference —
        # "Handle in Odoo" users get an inbox notification, "Handle by Emails"
        # users get it as an email instead.
        self.message_post(
            body=Markup('<p><strong>%s</strong><br/>%s</p><p><a href="%s">%s</a></p>') % (
                title, message, doc_url, _('View Document')),
            subject='%s: %s' % (title, self.name),
            partner_ids=users.partner_id.ids,
            message_type='notification',
            subtype_xmlid='mail.mt_note',
        )

        # Email: "Handle in Odoo" users only got the inbox entry above, so they
        # also get the template email. Queued, so the save is not slowed down.
        template = self.env.ref(
            'company_documents.email_template_document_notification',
            raise_if_not_found=False,
        )
        if not template:
            return
        for user in users.filtered(lambda u: u.notification_type == 'inbox' and u.email):
            template.with_context(
                recipient_name=user.name,
                change_title=title,
                change_message=message,
                doc_url=doc_url,
            ).send_mail(self.id, email_values={'email_to': user.email})

    @api.model
    def get_public_documents(self):
        """Return public documents for portal/employee view."""
        return self.search([
            ('visibility', '=', 'public'),
            ('company_id', 'in', self.env.companies.ids),
        ])
