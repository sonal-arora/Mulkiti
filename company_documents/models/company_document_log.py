from odoo import fields, models


class CompanyDocumentLog(models.Model):
    _name = 'company.document.log'
    _description = 'Document View/Download Log'
    _order = 'date desc'

    document_id = fields.Many2one(
        comodel_name='company.document',
        string='Document',
        required=True,
        ondelete='cascade',
    )
    user_id = fields.Many2one(
        comodel_name='res.users',
        string='User',
        required=True,
        default=lambda self: self.env.user,
    )
    employee_id = fields.Many2one(
        comodel_name='hr.employee',
        string='Employee',
        compute='_compute_employee_id',
        store=True,
    )
    action = fields.Selection(
        selection=[
            ('viewed', 'Viewed'),
            ('downloaded', 'Downloaded'),
        ],
        string='Action',
        required=True,
        default='viewed',
    )
    date = fields.Datetime(
        string='Date & Time',
        default=fields.Datetime.now,
        required=True,
    )

    def _compute_employee_id(self):
        for log in self:
            employee = self.env['hr.employee'].sudo().search(
                [('user_id', '=', log.user_id.id)], limit=1
            )
            log.employee_id = employee
