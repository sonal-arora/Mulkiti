# Copyright 2026 Mulkiti
from odoo import api, fields, models


class HrLeaveReportCalendar(models.Model):
    _inherit = 'hr.leave.report.calendar'

    # ─────────────────────────────────────────────────────────────────────
    # Core Odoo hides "Time Off Type" in the company-wide Overview /
    # "All Time Off" calendar behind groups='hr_holidays.group_hr_holidays_user'
    # (Time Off Officer only) — see hr_holidays/report/hr_leave_report_calendar.py.
    # That's all-or-nothing: non-officers get NO field at all (not even the
    # label), for every leave in the calendar, including their own.
    #
    # We want it visible, but scoped — not a company-wide reveal of
    # everyone's leave type (e.g. Sick Leave), only for:
    #   • the employee's own leave
    #   • their direct manager (parent_id) or configured leave_manager_id
    #   • their custom 1st / 2nd approver (dynamic_approval_workflow)
    #   • Time Off Officers (unchanged, as before)
    # Everyone else still sees just the dates, no type — same as today.
    #
    # `groups=False` clears the field-level restriction so the field can be
    # loaded at all; actual visibility per-record is then handled by
    # `can_see_leave_type` below and applied in the form view.
    # ─────────────────────────────────────────────────────────────────────
    holiday_status_id = fields.Many2one(
        'hr.leave.type', readonly=True, string="Time Off Type", groups=False,
    )

    can_see_leave_type = fields.Boolean(compute='_compute_can_see_leave_type')

    @api.depends('employee_id', 'leave_manager_id')
    def _compute_can_see_leave_type(self):
        user = self.env.user
        is_officer = user.has_group('hr_holidays.group_hr_holidays_user')
        for rec in self:
            if is_officer:
                rec.can_see_leave_type = True
                continue
            emp = rec.employee_id.sudo()
            rec.can_see_leave_type = bool(
                emp.user_id == user
                or rec.leave_manager_id == user
                or emp.parent_id.user_id == user
                or emp.x_leave_approver_1_id == user
                or emp.x_leave_approver_2_id == user
            )
