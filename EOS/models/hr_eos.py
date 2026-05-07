import calendar
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


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
        string='Total Annual Leave Allocated', compute='_compute_leave_details', store=True)
    leave_availed = fields.Float(
        string='Annual Leave Availed', compute='_compute_leave_details', store=True)
    leave_balance = fields.Float(
        string='Annual Leave Balance', compute='_compute_leave_details', store=True)
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
            ver = rec.employee_id.version_id if rec.employee_id else False
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

    @api.depends('employee_id')
    def _compute_leave_details(self):
        for rec in self:
            if not rec.employee_id:
                rec.total_leave_allocated = 0.0
                rec.leave_availed = 0.0
                rec.leave_balance = 0.0
                continue

            # Find annual leave type(s)
            leave_types = self.env['hr.leave.type'].search([
                ('requires_allocation', '=', True),
                ('time_type', '=', 'leave'),
            ])
            annual_types = leave_types.filtered(
                lambda lt: 'annual' in lt.name.lower()
            ) or leave_types[:1]

            allocated = 0.0
            taken = 0.0
            for lt in annual_types:
                allocs = self.env['hr.leave.allocation'].search([
                    ('employee_id', '=', rec.employee_id.id),
                    ('holiday_status_id', '=', lt.id),
                    ('state', '=', 'validate'),
                ])
                allocated += sum(allocs.mapped('number_of_days'))

                leaves = self.env['hr.leave'].search([
                    ('employee_id', '=', rec.employee_id.id),
                    ('holiday_status_id', '=', lt.id),
                    ('state', '=', 'validate'),
                ])
                taken += sum(leaves.mapped('number_of_days'))

            rec.total_leave_allocated = allocated
            rec.leave_availed = taken
            rec.leave_balance = allocated - taken

    @api.depends('basic_salary', 'leave_balance')
    def _compute_leave_pay(self):
        for rec in self:
            rec.leave_pay = (rec.basic_salary / 22.0) * rec.leave_balance if rec.basic_salary else 0.0

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

    @api.depends('employee_id')
    def _compute_loan_advance(self):
        for rec in self:
            if not rec.employee_id:
                rec.loan_advance = 0.0
                continue
            loans = self.env['hr.loan'].search([
                ('employee_id', '=', rec.employee_id.id),
                ('state', '=', 'approve'),
            ])
            rec.loan_advance = sum(loans.mapped('balance_amount'))

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

    def action_reset_draft(self):
        if not self.env.user.has_group('EOS.group_hr_eos_head'):
            raise UserError(_('Only EOS Head can reset End of Service records to Draft.'))
        for rec in self:
            if rec.state not in ('waiting_approval',):
                raise UserError(_('Only EOS records waiting for approval can be reset to Draft.'))
            rec.state = 'draft'

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

        # Prefer UAE regular pay structure; fall back to any available structure
        struct = self.env['hr.payroll.structure'].search([
            ('code', 'like', 'UAE'),
            ('type_id.country_id.code', '=', 'AE'),
        ], limit=1)
        if not struct:
            struct = self.env['hr.payroll.structure'].search([
                ('type_id', '=', self.employee_id.structure_type_id.id),
            ], limit=1)

        payslip_vals = {
            'name': f'Final Settlement - {self.employee_id.name} - {lwd.strftime("%m/%Y")}',
            'employee_id': self.employee_id.id,
            'date_from': date_from,
            'date_to': lwd,
            'company_id': self.company_id.id,
        }
        if struct:
            payslip_vals['struct_id'] = struct.id

        payslip = self.env['hr.payslip'].create(payslip_vals)
        self.payslip_id = payslip.id
