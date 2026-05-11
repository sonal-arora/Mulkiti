from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # ── Probation End Date ─────────────────────────────────────────────────
    probation_end_date = fields.Date(
        string='Probation End Date',
        compute='_compute_probation_end_date',
        store=True,
        readonly=False,
        copy=False,
        tracking=True,
        groups='hr.group_hr_user',
        help=(
            "End of the employee's probation period. "
            "Defaults to 6 months after the contract start date. "
            "Annual Leave cannot be taken before this date."
        ),
    )

    @api.depends('contract_date_start')
    def _compute_probation_end_date(self):
        for emp in self:
            cds = emp.contract_date_start
            if cds and not emp.probation_end_date:
                emp.probation_end_date = cds + relativedelta(months=6)

    # ── 1st Level Approver ─────────────────────────────────────────────────
    # Either this user OR the employee's direct manager (parent_id.user_id)
    # can give 1st-level leave approval.
    x_leave_approver_1_id = fields.Many2one(
        comodel_name='res.users',
        string='Leave 1st Approver',
        tracking=True,
        groups='hr_holidays.group_hr_holidays_user',
        domain="[('share', '=', False), ('company_ids', 'in', company_id)]",
        help=(
            "Custom first-level approver for this employee's leave requests. "
            "The employee's direct manager can also approve at this level."
        ),
    )

    # ── 2nd Level Approver ─────────────────────────────────────────────────
    # Only this person (or an HR Manager) can approve the 2nd level.
    # If left empty the 2nd-level step is skipped automatically.
    x_leave_approver_2_id = fields.Many2one(
        comodel_name='res.users',
        string='Leave 2nd Approver',
        tracking=True,
        groups='hr_holidays.group_hr_holidays_user',
        domain="[('share', '=', False), ('company_ids', 'in', company_id)]",
        help=(
            "Second-level approver for this employee's leave requests. "
            "If not set, the 2nd approval step is skipped and the request "
            "goes directly to the Time Off Manager."
        ),
    )


class EmployeePublic(models.Model):
    _inherit = 'hr.employee.public'

    probation_end_date = fields.Date(
        string='Probation End Date',
        groups='hr.group_hr_user',
    )

    x_leave_approver_1_id = fields.Many2one(
        comodel_name='res.users',
        string='Leave 1st Approver',
        tracking=True,
        groups='hr_holidays.group_hr_holidays_user',
        domain="[('share', '=', False), ('company_ids', 'in', company_id)]",
        help=(
            "Custom first-level approver for this employee's leave requests. "
            "The employee's direct manager can also approve at this level."
        ),
    )

    # ── 2nd Level Approver ─────────────────────────────────────────────────
    # Only this person (or an HR Manager) can approve the 2nd level.
    # If left empty the 2nd-level step is skipped automatically.
    x_leave_approver_2_id = fields.Many2one(
        comodel_name='res.users',
        string='Leave 2nd Approver',
        tracking=True,
        groups='hr_holidays.group_hr_holidays_user',
        domain="[('share', '=', False), ('company_ids', 'in', company_id)]",
        help=(
            "Second-level approver for this employee's leave requests. "
            "If not set, the 2nd approval step is skipped and the request "
            "goes directly to the Time Off Manager."
        ),
    )


