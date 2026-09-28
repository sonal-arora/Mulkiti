from odoo import _, api, fields, models
from odoo.exceptions import AccessError


class ProjectErrorLog(models.Model):
    _name = 'project.error.log'
    _description = 'Project Error Log'
    _order = 'date desc, id desc'
    _rec_name = 'name'

    name = fields.Char(string='Sno', required=True, copy=False, readonly=True, default='New')
    date = fields.Date(required=True, default=fields.Date.context_today)
    reported_by_id = fields.Many2one('res.users', string='Error Reported By', required=True)
    made_by_id = fields.Many2one('res.users', string='Error Made By', required=True)
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

    def _check_access(self, operation):
        """The 'Error Log - View Only' group is a hard read-only lock: anyone
        holding it cannot create/edit/delete Error Log entries, no matter
        what other (more permissive) groups they also have.

        Overriding this (instead of create/write/unlink) also makes the
        New/Edit/Delete buttons disappear from the list/form views for these
        users, since the web client's button visibility is driven by this
        same access check (see ir_ui_view.py's postprocessing, which calls
        model.has_access(operation) - itself backed by _check_access).
        """
        if operation in ('create', 'write', 'unlink') and self.env.user.has_group(
            'project_error_log.group_project_error_log_viewer'
        ):
            return self, lambda: AccessError(_(
                "Your Error Log access is read-only, so you cannot create, "
                "edit, or delete entries."
            ))
        return super()._check_access(operation)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('project.error.log') or 'New'
        return super().create(vals_list)
