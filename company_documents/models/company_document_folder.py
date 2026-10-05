from odoo import api, fields, models, _


class CompanyDocumentFolder(models.Model):
    _name = 'company.document.folder'
    _description = 'Company Document Folder'
    _inherit = ['mail.thread']
    _order = 'sequence, name'

    name = fields.Char(string='Folder Name', required=True, tracking=True)
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True)
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
    )
    access_type = fields.Selection(
        selection=[
            ('all', 'All Employees'),
            ('specific', 'Specific Users'),
        ],
        string='Access',
        required=True,
        default='specific',
        tracking=True,
        help='All Employees: every internal user of the folder company can see it.\n'
             'Specific Users: only the users listed below can see it.',
    )
    user_ids = fields.Many2many(
        comodel_name='res.users',
        relation='company_document_folder_user_rel',
        column1='folder_id',
        column2='user_id',
        string='Allowed Users',
        domain="[('share', '=', False), ('company_ids', 'in', company_id)]",
    )
    notify_on_update = fields.Boolean(
        string='Notify on Update',
        default=True,
        help='Send an email and Odoo inbox notification to the users who can '
             'access this folder when a document is added or updated in it.',
    )
    description = fields.Text(string='Description')
    document_ids = fields.One2many(
        comodel_name='company.document',
        inverse_name='folder_id',
        string='Documents',
    )
    document_count = fields.Integer(string='Document Count', compute='_compute_stats')
    view_count = fields.Integer(string='Total Views', compute='_compute_stats')
    download_count = fields.Integer(string='Total Downloads', compute='_compute_stats')
    user_count = fields.Integer(string='Users', compute='_compute_stats')

    @api.depends('document_ids', 'document_ids.view_count',
                 'document_ids.download_count', 'user_ids', 'access_type')
    def _compute_stats(self):
        for folder in self:
            docs = folder.document_ids
            folder.document_count = len(docs)
            folder.view_count = sum(docs.mapped('view_count'))
            folder.download_count = sum(docs.mapped('download_count'))
            folder.user_count = len(folder._get_recipient_users())

    @api.onchange('company_id')
    def _onchange_company_id(self):
        if self.company_id:
            self.user_ids = self.user_ids.filtered(
                lambda u: self.company_id in u.company_ids)

    def _get_recipient_users(self):
        """Users that can access this folder (used for notifications)."""
        self.ensure_one()
        if self.access_type == 'specific':
            return self.user_ids.filtered(
                lambda u: u.active and not u.share and self.company_id in u.company_ids)
        employees = self.env['hr.employee'].sudo().search([
            ('company_id', '=', self.company_id.id),
            ('user_id', '!=', False),
        ])
        return employees.user_id.filtered(lambda u: u.active and not u.share)

    def action_view_documents(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'company.document',
            'view_mode': 'list,kanban,form',
            'domain': [('folder_id', '=', self.id)],
            'context': {
                'default_folder_id': self.id,
                'default_company_id': self.company_id.id,
            },
        }

    def action_view_history(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Folder History — %s', self.name),
            'res_model': 'company.document.log',
            'view_mode': 'list',
            'domain': [('document_id.folder_id', '=', self.id)],
        }
