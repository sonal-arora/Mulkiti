import calendar
from datetime import datetime, time, timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

# UAE annual-leave accrual: 30 calendar days / 12 months of the leave year,
# expressed as "days per standard 22 working-day month".
LEAVE_ACCRUAL_RATE_STANDARD = 1.84
# Reduced rate used while the employee has completed less than 1 year of service.
LEAVE_ACCRUAL_RATE_UNDER_ONE_YEAR = 1.47
STANDARD_MONTH_WORKING_DAYS = 22.0


class HrEos(models.Model):
    _name = 'hr.eos'
    _description = 'End of Service'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'

    # ── Identification ──────────────────────────────────────────────────────
    name = fields.Char(
        string='EOS No', readonly=True, default='New', copy=False, tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('waiting_approval', 'Waiting Approval'),
        ('done', 'Done'),
    ], string='Status', default='draft', tracking=True, copy=False)
    company_id = fields.Many2one(
        'res.company', string='Company', default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')

    # ── Header ───────────────────────────────────────────────────────────────
    application_date = fields.Date(
        string='Application Date', default=fields.Date.today, required=True, tracking=True)
    employee_id = fields.Many2one(
        'hr.employee', string='Employee Name', required=True, tracking=True,
        domain="[('company_id', '=', company_id)]")
    joining_date = fields.Date(
        string='Date of Joining', compute='_compute_employee_details', store=True)
    resignation_date = fields.Date(string='Resignation Date', tracking=True)
    notice_period_days = fields.Integer(
        string='Notice Period (Calendar Days)', tracking=True)
    last_working_date = fields.Date(
        string='Last Working Date', compute='_compute_last_working_date',
        store=True, tracking=True, readonly=False)
    exit_type = fields.Selection([
        ('resignation', 'Resignation'),
        ('termination', 'Termination'),
    ], string='Exit Type', required=True, tracking=True)
    termination_reason = fields.Text(string='Termination Reason', tracking=True)

    # ── Employee Details (auto-filled) ───────────────────────────────────────
    department_id = fields.Many2one(
        'hr.department', string='Department', compute='_compute_employee_details', store=True)
    job_title = fields.Char(
        string='Job Title', compute='_compute_employee_details', store=True)

    # ── Final Settlement Details — Salary ────────────────────────────────────
    basic_salary = fields.Monetary(
        string='Basic Salary', compute='_compute_salary_details', store=True)
    housing_allowance = fields.Monetary(
        string='Housing', compute='_compute_salary_details', store=True)
    transportation_allowance = fields.Monetary(
        string='Transportation', compute='_compute_salary_details', store=True)
    other_salary_allowances = fields.Monetary(
        string='Others', compute='_compute_salary_details', store=True)
    total_salary = fields.Monetary(
        string='Total Salary', compute='_compute_salary_details', store=True)

    # ── Duration of Employment ────────────────────────────────────────────────
    total_calendar_days = fields.Integer(
        string='Duration of Employment (Total Calendar Days)',
        compute='_compute_duration', store=True)
    years_of_service = fields.Integer(
        string='No. of Years', compute='_compute_duration', store=True)
    months_of_service = fields.Integer(
        string='No. of Months', compute='_compute_duration', store=True)
    days_of_service = fields.Integer(
        string='No. of Days', compute='_compute_duration', store=True)

    # ── Annual Leave ──────────────────────────────────────────────────────────
    total_leave_allocated = fields.Float(
        string='Total Annual Leave Allocated', compute='_compute_leave_details', store=True,
        digits=(16, 2),
        help='Theoretical leave entitlement for the whole tenure, by formula: '
             'full months worked (before the resignation month) × the '
             'applicable Monthly Leave Accrual Rate, plus the resignation '
             'month\'s own Pro-rated Leave Accrual (B). Not the raw sum of '
             'hr.leave.allocation records, which can include manual/one-off '
             'allocations unrelated to the accrual formula.')
    leave_availed = fields.Float(
        string='Annual Leave Availed', compute='_compute_leave_details', store=True)

    # Leave balance as of the 1st day of the resignation/LWD month (A) — NOT
    # today's system date. See _get_leave_taken_before().
    leave_balance_month_start = fields.Float(
        string='Leave Balance as of Month Start', compute='_compute_leave_details',
        store=True, digits=(16, 2),
        help='Formula-based leave entitlement as of the first day of the '
             'Last Working Date\'s month: full months worked before that '
             'month × the Monthly Leave Accrual Rate, minus annual leave '
             'already taken on or before that day. Not based on raw '
             'hr.leave.allocation records (which can include manual/one-off '
             'allocations unrelated to the accrual formula).')
    leave_accrual_rate = fields.Float(
        string='Monthly Leave Accrual Rate', compute='_compute_leave_details',
        store=True, digits=(16, 2),
        help='1.84 days/month once the employee has completed 1 year of '
             'service, otherwise 1.47 days/month.')
    working_days_resignation_month = fields.Integer(
        string='Working Days (Resignation Month)', compute='_compute_leave_details',
        store=True,
        help='Working days from the 1st of the resignation month up to and '
             'including the Last Working Date, per the employee\'s working '
             'schedule.')
    pro_rated_leave_accrual = fields.Float(
        string='Pro-rated Leave Accrual (B)', compute='_compute_leave_details',
        store=True, digits=(16, 2),
        help='(Monthly Leave Accrual Rate ÷ 22) × Working Days in the '
             'resignation month up to the Last Working Date.')

    leave_pay = fields.Monetary(
        string='Leave Pay', compute='_compute_leave_pay', store=True)

    # ── Gratuity ──────────────────────────────────────────────────────────────
    gratuity_eligible = fields.Boolean(
        string='Gratuity Eligible', compute='_compute_gratuity', store=True)
    gratuity_days = fields.Float(
        string='Gratuity Days', compute='_compute_gratuity', store=True, digits=(16, 2))
    gratuity_pay = fields.Monetary(
        string='Gratuity Pay', compute='_compute_gratuity', store=True)

    # ── Allowances (Total A) ──────────────────────────────────────────────────
    ticket_reimbursement = fields.Monetary(string='Ticket Reimbursement', tracking=True)
    notice_period_salary = fields.Monetary(
        string='Notice Period Salary', compute='_compute_notice_period_salary', store=True)
    other_income = fields.Monetary(string='Others (Income)', tracking=True)
    total_a = fields.Monetary(string='Total (A)', compute='_compute_total_a', store=True)

    # ── Deductions (Total B) ──────────────────────────────────────────────────
    loan_advance = fields.Monetary(
        string='Loan / Salary Advance')
    #compute='_compute_loan_advance', store=True)
    notice_period_shortfall = fields.Monetary(string='Notice Period Shortfall', tracking=True)
    other_deductions = fields.Monetary(string='Others (Deductions)', tracking=True)
    total_b = fields.Monetary(string='Deductions Total (B)', compute='_compute_total_b', store=True)

    # ── Net ───────────────────────────────────────────────────────────────────
    net_payable = fields.Monetary(
        string='Net Payable Amount (AED)', compute='_compute_net_payable', store=True)

    # ── Approval ──────────────────────────────────────────────────────────────
    approval_date = fields.Date(string='Approval Date', readonly=True)
    approved_by = fields.Many2one('res.users', string='Approved By', readonly=True)

    # ── FnF Payslip ───────────────────────────────────────────────────────────
    payslip_id = fields.Many2one('hr.payslip', string='FnF Payslip', readonly=True, copy=False)

    # ─────────────────────────────────────────────────────────────────────────
    # ORM overrides
    # ─────────────────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('hr.eos.seq') or 'New'
        return super().create(vals_list)

    def unlink(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only Draft EOS records can be deleted.'))
        return super().unlink()

    # ─────────────────────────────────────────────────────────────────────────
    # Computed fields
    # ─────────────────────────────────────────────────────────────────────────

    @api.depends('employee_id')
    def _compute_employee_details(self):
        for rec in self:
            emp = rec.employee_id
            if emp:
                rec.department_id = emp.department_id
                rec.job_title = emp.job_title or emp.job_id.name or ''
                rec.joining_date = emp._get_first_contract_date(no_gap=False)
            else:
                rec.department_id = False
                rec.job_title = False
                rec.joining_date = False

    @api.depends('resignation_date', 'notice_period_days')
    def _compute_last_working_date(self):
        for rec in self:
            if rec.resignation_date and rec.notice_period_days:
                rec.last_working_date = rec.resignation_date + timedelta(days=rec.notice_period_days)
            elif rec.resignation_date:
                rec.last_working_date = rec.resignation_date
            else:
                rec.last_working_date = False

    @api.depends('employee_id')
    def _compute_salary_details(self):
        for rec in self:
            ver = rec.employee_id.sudo().version_id if rec.employee_id else False
            if ver:
                rec.basic_salary = ver.wage
                rec.housing_allowance = ver.l10n_ae_housing_allowance
                rec.transportation_allowance = ver.l10n_ae_transportation_allowance
                rec.other_salary_allowances = ver.l10n_ae_other_allowances
                rec.total_salary = (
                    ver.wage
                    + ver.l10n_ae_housing_allowance
                    + ver.l10n_ae_transportation_allowance
                    + ver.l10n_ae_other_allowances
                )
            else:
                rec.basic_salary = 0.0
                rec.housing_allowance = 0.0
                rec.transportation_allowance = 0.0
                rec.other_salary_allowances = 0.0
                rec.total_salary = 0.0

    @api.depends('joining_date', 'last_working_date')
    def _compute_duration(self):
        for rec in self:
            jd = rec.joining_date
            lwd = rec.last_working_date
            if jd and lwd and lwd >= jd:
                rec.total_calendar_days = (lwd - jd).days + 1
                rd = relativedelta(lwd, jd)
                rec.years_of_service = rd.years
                rec.months_of_service = rd.months
                rec.days_of_service = rd.days
            else:
                rec.total_calendar_days = 0
                rec.years_of_service = 0
                rec.months_of_service = 0
                rec.days_of_service = 0

    @api.depends('employee_id', 'last_working_date', 'joining_date', 'years_of_service')
    def _compute_leave_details(self):
        # Collect all employee IDs needing computation
        emp_ids = self.filtered('employee_id').mapped('employee_id.id')

        if not emp_ids:
            for rec in self:
                rec.leave_availed = 0.0
                rec._reset_leave_balance_fields()
            return

        # Find annual leave type(s) once — not per record
        leave_types = self.env['hr.leave.type'].search([
            ('requires_allocation', '=', True),
            ('time_type', '=', 'leave'),
        ])
        annual_types = leave_types.filtered(
            lambda lt: 'annual' in lt.name.lower()
        ) or leave_types[:1]

        if not annual_types:
            for rec in self:
                rec.leave_availed = 0.0
                rec._reset_leave_balance_fields()
            return

        annual_type_ids = annual_types.ids

        # Single aggregated query for taken leaves across all employees
        leave_rows = self.env['hr.leave'].read_group(
            domain=[
                ('employee_id', 'in', emp_ids),
                ('holiday_status_id', 'in', annual_type_ids),
                ('state', '=', 'validate'),
            ],
            fields=['employee_id', 'number_of_days:sum'],
            groupby=['employee_id'],
        )
        taken_by_emp = {
            row['employee_id'][0]: row['number_of_days']
            for row in leave_rows
        }

        for rec in self:
            emp = rec.employee_id
            if not emp:
                rec.leave_availed = 0.0
                rec._reset_leave_balance_fields()
                continue

            rec.leave_availed = taken_by_emp.get(emp.id, 0.0)

            lwd = rec.last_working_date
            jd = rec.joining_date
            if not lwd or not jd:
                rec._reset_leave_balance_fields()
                continue

            month_start = lwd.replace(day=1)

            # Accrual rate depends on completed service as of the LWD — one
            # flat rate for the whole tenure (not blended even if the
            # employee crossed the 1-year mark partway through).
            completed_years = relativedelta(lwd, jd).years
            rec.leave_accrual_rate = (
                LEAVE_ACCRUAL_RATE_UNDER_ONE_YEAR if completed_years < 1
                else LEAVE_ACCRUAL_RATE_STANDARD
            )

            # Full months worked strictly before the resignation month.
            full_months = max(0, (
                relativedelta(month_start, jd).years * 12
                + relativedelta(month_start, jd).months
            ))

            # (A) Formula-based entitlement for those full months (full_months
            # × rate), minus leave already taken before the resignation month
            # — NOT the raw hr.leave.allocation sum, which can include
            # manual/one-off/test allocations unrelated to the accrual
            # formula and would make the balance inconsistent with Total
            # Annual Leave Allocated below.
            taken_before_month_start = rec._get_leave_taken_before(
                emp, annual_type_ids, month_start)
            rec.leave_balance_month_start = (
                full_months * rec.leave_accrual_rate - taken_before_month_start
            )

            # (B) Pro-rated accrual for the resignation month, up to the LWD.
            rec.working_days_resignation_month = rec._count_working_days(
                emp, month_start, lwd)
            rec.pro_rated_leave_accrual = (
                rec.leave_accrual_rate / STANDARD_MONTH_WORKING_DAYS
            ) * rec.working_days_resignation_month

            # Total Annual Leave Allocated = theoretical entitlement over the
            # whole tenure = full months × rate + this month's pro-rated
            # accrual (B).
            rec.total_leave_allocated = (
                full_months * rec.leave_accrual_rate + rec.pro_rated_leave_accrual
            )

    def _reset_leave_balance_fields(self):
        self.total_leave_allocated = 0.0
        self.leave_balance_month_start = 0.0
        self.leave_accrual_rate = 0.0
        self.working_days_resignation_month = 0
        self.pro_rated_leave_accrual = 0.0

    def _get_leave_taken_before(self, employee, annual_type_ids, as_of_date):
        """Validated annual leave days taken by `employee` on or before
        `as_of_date` (the resignation month's 1st day) — used so the EOS
        leave balance reflects the Last Working Date's month, not today's
        date. Anything taken on as_of_date itself counts as "before" since
        pro_rated_leave_accrual (B) doesn't separately net against leave
        taken during its own window (month_start..LWD)."""
        as_of_dt = datetime.combine(as_of_date, time.max)
        return sum(self.env['hr.leave'].search([
            ('employee_id', '=', employee.id),
            ('holiday_status_id', 'in', annual_type_ids),
            ('state', '=', 'validate'),
            ('date_from', '<=', as_of_dt),
        ]).mapped('number_of_days'))

    def _count_working_days(self, employee, date_from, date_to):
        """Count working days (inclusive) between two dates, per the
        employee's working schedule (falls back to the company calendar,
        then a plain Mon-Fri week)."""
        if not date_from or not date_to or date_to < date_from:
            return 0

        calendar_id = employee.resource_calendar_id or employee.company_id.resource_calendar_id

        count = 0
        current = date_from
        while current <= date_to:
            if calendar_id:
                works = calendar_id._works_on_date(current)
            else:
                works = current.weekday() < 5  # Mon-Fri fallback
            if works:
                count += 1
            current += timedelta(days=1)
        return count

    @api.depends('basic_salary', 'leave_balance_month_start')
    def _compute_leave_pay(self):
        for rec in self:
            rec.leave_pay = (
                (rec.basic_salary / 22.0) * rec.leave_balance_month_start
                if rec.basic_salary else 0.0
            )

    @api.depends('joining_date', 'last_working_date', 'total_calendar_days', 'basic_salary')
    def _compute_gratuity(self):
        for rec in self:
            jd = rec.joining_date
            lwd = rec.last_working_date
            if not jd or not lwd or lwd < jd:
                rec.gratuity_eligible = False
                rec.gratuity_days = 0.0
                rec.gratuity_pay = 0.0
                continue

            rd = relativedelta(lwd, jd)
            total_years = rd.years + rd.months / 12.0 + rd.days / 365.0

            if total_years < 1.0:
                # Less than 1 year → not eligible
                rec.gratuity_eligible = False
                rec.gratuity_days = 0.0
                rec.gratuity_pay = 0.0
            elif total_years <= 5.0:
                # 1 year to 5 years (including exactly 5 years) → Total Calendar Days × 21/365
                rec.gratuity_eligible = True
                rec.gratuity_days = rec.total_calendar_days * 21.0 / 365.0
                rec.gratuity_pay = (rec.basic_salary / 30.0) * rec.gratuity_days
            else:
                # More than 5 years → split calculation:
                #   First 5 years portion  → days × 21/365
                #   Remaining days beyond 5 years → days × 30/365
                rec.gratuity_eligible = True
                five_year_date = jd + relativedelta(years=5)
                days_first_5 = (five_year_date - jd).days + 1
                days_beyond_5 = (lwd - five_year_date).days
                rec.gratuity_days = (
                    (days_first_5 * 21.0 / 365.0)
                    + (days_beyond_5 * 30.0 / 365.0)
                )
                rec.gratuity_pay = (rec.basic_salary / 30.0) * rec.gratuity_days

    @api.depends('total_salary', 'last_working_date')
    def _compute_notice_period_salary(self):
        # Full salary for calendar days of the month up to and including last working day
        for rec in self:
            if not rec.total_salary or not rec.last_working_date:
                rec.notice_period_salary = 0.0
                continue
            lwd = rec.last_working_date
            days_in_month = calendar.monthrange(lwd.year, lwd.month)[1]
            rec.notice_period_salary = (rec.total_salary / days_in_month) * lwd.day

    @api.depends('leave_pay', 'gratuity_pay', 'ticket_reimbursement', 'notice_period_salary', 'other_income')
    def _compute_total_a(self):
        for rec in self:
            rec.total_a = (
                rec.leave_pay
                + rec.gratuity_pay
                + rec.ticket_reimbursement
                + rec.notice_period_salary
                + rec.other_income
            )

    @api.depends('loan_advance', 'notice_period_shortfall', 'other_deductions')
    def _compute_total_b(self):
        for rec in self:
            rec.total_b = rec.loan_advance + rec.notice_period_shortfall + rec.other_deductions

    @api.depends('total_a', 'total_b')
    def _compute_net_payable(self):
        for rec in self:
            rec.net_payable = rec.total_a - rec.total_b

    # ─────────────────────────────────────────────────────────────────────────
    # Workflow actions
    # ─────────────────────────────────────────────────────────────────────────

    def action_submit(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only Draft EOS can be submitted for approval.'))
            rec.state = 'waiting_approval'
            # Cancel future leaves first
            rec._cancel_future_leaves()
            # Recompute leave balance after cancellation
            rec._compute_leave_details()
            rec._compute_leave_pay()
            # Employee enters the notice period as soon as the resignation
            # is formally submitted for approval.
            if rec.employee_id:
                rec.employee_id.sudo().employment_status = 'notice_period'

    def _cancel_future_leaves(self):
        """
        Refuse/cancel all future leave requests for the employee on EOS submission.
        Odoo automatically restores leave balance when a leave is refused.
        """
        self.ensure_one()
        if not self.employee_id:
            return

        # Find all future leaves (today onwards) in any active state
        future_leaves = self.env['hr.leave'].sudo().search([
            ('employee_id', '=', self.employee_id.id),
            ('state', 'in', ('draft', 'confirm', 'validate1', 'validate2', 'validate')),
            ('date_from', '>=', fields.Datetime.today()),
        ])

        if not future_leaves:
            return

        refused = self.env['hr.leave']
        for leave in future_leaves:
            try:
                if leave.state in ('confirm', 'validate1', 'validate2', 'validate'):
                    # Refuse → Odoo auto-restores balance
                    leave.with_context(
                        skip_refuse_wizard=True,
                        leave_fast_create=True,
                    ).action_refuse()
                    leave.message_post(
                        body=_(
                            'Automatically refused: <strong>%(emp)s</strong> has '
                            'submitted resignation (EOS: %(eos)s). '
                            'Leave balance has been restored.',
                            emp=self.employee_id.name,
                            eos=self.name,
                        )
                    )
                elif leave.state == 'draft':
                    leave.action_cancel()
                    leave.message_post(
                        body=_(
                            'Automatically cancelled: <strong>%(emp)s</strong> has '
                            'submitted resignation (EOS: %(eos)s).',
                            emp=self.employee_id.name,
                            eos=self.name,
                        )
                    )
                refused |= leave
            except Exception as e:
                leave.message_post(
                    body=_('Could not cancel this leave automatically: %(err)s', err=str(e))
                )

        if refused:
            self.message_post(
                body=_(
                    '%(count)d future leave(s) automatically cancelled/refused. '
                    'Leave balances have been restored.',
                    count=len(refused),
                )
            )

    def action_approve(self):
        if not self.env.user.has_group('EOS.group_hr_eos_head'):
            raise UserError(_('Only EOS Head can approve End of Service records.'))
        for rec in self:
            if rec.state != 'waiting_approval':
                raise UserError(_('Only EOS records waiting for approval can be approved.'))
            rec.approval_date = fields.Date.today()
            rec.approved_by = self.env.user
            rec.state = 'done'
            rec._create_fnf_payslip()
            rec._close_employee_service()

    def _close_employee_service(self):
        """On final EOS approval: move the employee to 'End of Service',
        archive the employee record, and deactivate their user login."""
        self.ensure_one()
        emp = self.employee_id
        if not emp:
            return

        emp_sudo = emp.sudo()
        emp_sudo.employment_status = 'end_of_service'
        emp_sudo.active = False
        if emp_sudo.user_id:
            emp_sudo.user_id.sudo().active = False

        leaves = self.env['hr.leave'].sudo().search([('employee_id', '=', emp.id)])
        leaves.write({'active': False})

        self.message_post(
            body=_(
                'End of Service completed for <strong>%(emp)s</strong>: employee '
                'archived, user login deactivated, and %(count)d time off '
                'record(s) archived.',
                emp=emp.name,
                count=len(leaves),
            )
        )

    def action_reset_draft(self):
        if not self.env.user.has_group('EOS.group_hr_eos_head'):
            raise UserError(_('Only EOS Head can reset End of Service records to Draft.'))
        for rec in self:
            # if rec.state not in ('waiting_approval',):
            #     raise UserError(_('Only EOS records waiting for approval can be reset to Draft.'))
            rec.state = 'draft'
            # Resignation is no longer in process — take the employee back
            # out of the notice period.
            if rec.employee_id and rec.employee_id.employment_status == 'notice_period':
                rec.employee_id.sudo().employment_status = 'confirmed'

    def action_view_payslip(self):
        self.ensure_one()
        if not self.payslip_id:
            raise UserError(_('No FnF payslip has been generated yet.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('FnF Payslip'),
            'res_model': 'hr.payslip',
            'res_id': self.payslip_id.id,
            'view_mode': 'form',
        }

    # ─────────────────────────────────────────────────────────────────────────
    # FnF Payslip creation
    # ─────────────────────────────────────────────────────────────────────────

    def _create_fnf_payslip(self):
        self.ensure_one()
        if not self.employee_id or not self.last_working_date:
            return

        lwd = self.last_working_date
        date_from = lwd.replace(day=1)

        # Always use dedicated EOS structure — works for ALL employees
        # regardless of their regular salary structure (UAE Regular, Generic, etc.)
        eos_struct = self.env.ref('EOS.hr_payroll_structure_eos_fnf', raise_if_not_found=False)
        if not eos_struct:
            raise UserError(_(
                'EOS Final Settlement salary structure not found. '
                'Please reinstall the EOS module.'
            ))

        payslip = self.env['hr.payslip'].create({
            'name': f'Final Settlement - {self.employee_id.name} - {lwd.strftime("%m/%Y")}',
            'employee_id': self.employee_id.id,
            'date_from': date_from,
            'date_to': lwd,
            'struct_id': eos_struct.id,
            'company_id': self.company_id.id,
            'eos_id': self.id,  # Link EOS → Payslip (salary rules read from here)
        })

        # Compute payslip lines from EOS salary rules
        payslip.compute_sheet()

        self.payslip_id = payslip.id
