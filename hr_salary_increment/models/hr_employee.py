from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    salary_increment_ids = fields.One2many(
        comodel_name='hr.salary.increment',
        inverse_name='employee_id',
        string='Salary Increments',
        groups='hr_payroll.group_hr_payroll_user',
    )
    salary_increment_count = fields.Integer(
        compute='_compute_salary_increment_count',
        groups='hr_payroll.group_hr_payroll_user',
    )

    def _compute_salary_increment_count(self):
        for employee in self:
            employee.salary_increment_count = len(employee.salary_increment_ids)

    def action_view_salary_increments(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Salary Increments'),
            'res_model': 'hr.salary.increment',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }
