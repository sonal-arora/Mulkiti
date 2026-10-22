from odoo import fields, models
from odoo.fields import Domain


class HrLeave(models.Model):
    _inherit = 'hr.leave'

    # Non-HR users cannot search hr.employee by tags (hr.employee.public has
    # no category_ids), so the menu domain filters on this field instead.
    is_brickwork_employee = fields.Boolean(
        string="Brickwork Employee",
        compute='_compute_is_brickwork_employee',
        search='_search_is_brickwork_employee',
    )

    def _compute_is_brickwork_employee(self):
        for leave in self:
            leave.is_brickwork_employee = any(leave.employee_id.sudo().category_ids.mapped('is_brickwork'))

    def _search_is_brickwork_employee(self, operator, value):
        if operator not in ('in', 'not in'):
            return NotImplemented
        employees = self.env['hr.employee'].sudo().with_context(active_test=False).search(
            [('category_ids.is_brickwork', '=', True)]
        )
        domain = Domain('employee_id', 'in', employees.ids)
        return domain if (operator == 'in') == (True in value) else ~domain
