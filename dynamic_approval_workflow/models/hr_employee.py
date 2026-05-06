from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

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


