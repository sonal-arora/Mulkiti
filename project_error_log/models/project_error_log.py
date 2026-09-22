from odoo import api, fields, models


class ProjectErrorLog(models.Model):
    _name = 'project.error.log'
    _description = 'Project Error Log'
    _order = 'date desc, id desc'
    _rec_name = 'name'

    name = fields.Char(string='Sno', required=True, copy=False, readonly=True, default='New')
    date = fields.Date(required=True, default=fields.Date.context_today)
    reported_by_id = fields.Many2one('hr.employee', string='Error Reported By', required=True)
    made_by_id = fields.Many2one('hr.employee', string='Error Made By', required=True)
    error_type_id = fields.Many2one('project.error.type', string='Type of Error', required=True)
    project_id = fields.Many2one('project.project', string='Project', required=True)
    unit_no = fields.Char(string='Unit #')
    description = fields.Text(string='Error Description', required=True)
    screenshot_ids = fields.Many2many('ir.attachment', string='Error Screenshots')
    repeat_status = fields.Selection([
        ('new', 'New'),
        ('repeated', 'Repeated'),
    ], string='Repeated / New Error', required=True, default='new')
    remarks = fields.Text(string='Additional Remarks')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('project.error.log') or 'New'
        return super().create(vals_list)
