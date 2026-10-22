from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# increment field suffix -> hr.version field holding that salary component
SALARY_COMPONENTS = {
    'wage': 'wage',
    'housing': 'l10n_ae_housing_allowance',
    'transport': 'l10n_ae_transportation_allowance',
    'other': 'l10n_ae_other_allowances',
}

# Fields HR fills in; they can only change while the increment is in draft.
DRAFT_ONLY_FIELDS = {
    'employee_id', 'date_effective', 'increment_type', 'reason',
    'new_wage', 'new_housing', 'new_transport', 'new_other',
}


class HrSalaryIncrement(models.Model):
    _name = 'hr.salary.increment'
    _description = 'Salary Increment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_effective desc, id desc'

    name = fields.Char(
        string='Reference', required=True, copy=False, readonly=True,
        default=lambda self: _('New'))
    employee_id = fields.Many2one(
        comodel_name='hr.employee', string='Employee', required=True,
        tracking=True, index=True,
        domain="[('company_id', 'in', allowed_company_ids)]")
    # Stored copy so employees (who cannot read hr.employee) see their own name.
    employee_name = fields.Char(
        related='employee_id.name', store=True, string='Employee Name')
    # Follows the employee: archiving the employee archives the increments.
    active = fields.Boolean(related='employee_id.active', store=True)
    company_id = fields.Many2one(
        related='employee_id.company_id', store=True, string='Company')
    currency_id = fields.Many2one(related='company_id.currency_id')
    department_id = fields.Many2one(
        related='employee_id.department_id', store=True, string='Department')
    job_id = fields.Many2one(
        related='employee_id.job_id', store=True, string='Job Position')
    joining_date = fields.Date(related='employee_id.joining_date')
    date_effective = fields.Date(
        string='Effective Date', required=True, tracking=True,
        default=fields.Date.context_today,
        help='The new salary applies from this date. A new contract version is '
             'created on this date when the increment is approved.')
    increment_type = fields.Selection(
        selection=[
            ('annual', 'Annual'),
            ('promotion', 'Promotion'),
            ('performance', 'Performance'),
            ('correction', 'Correction'),
            ('other', 'Other'),
        ],
        string='Type', required=True, default='annual', tracking=True)
    reason = fields.Text(string='Reason / Remarks')
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('approved', 'Approved'),
            ('cancel', 'Cancelled'),
        ],
        string='Status', required=True, default='draft', copy=False,
        tracking=True)

    version_id = fields.Many2one(
        comodel_name='hr.version', string='Current Contract Version',
        compute='_compute_version_id', groups='hr_payroll.group_hr_payroll_user',
        help='Contract version in force on the effective date.')
    contract_date_start = fields.Date(
        string='Contract Start Date', compute='_compute_version_id',
        groups='hr_payroll.group_hr_payroll_user')

    # Old salary is read from the contract on the effective date and kept as
    # a snapshot, so an approved increment always shows what it changed from.
    old_wage = fields.Monetary(
        string='Old Basic Salary', compute='_compute_old_salary', store=True)
    old_housing = fields.Monetary(
        string='Old Housing Allowance', compute='_compute_old_salary', store=True)
    old_transport = fields.Monetary(
        string='Old Transport Allowance', compute='_compute_old_salary', store=True)
    old_other = fields.Monetary(
        string='Old Other Allowances', compute='_compute_old_salary', store=True)
    old_total = fields.Monetary(
        string='Old Total Salary', compute='_compute_totals', store=True)

    new_wage = fields.Monetary(
        string='New Basic Salary', compute='_compute_new_salary', store=True,
        readonly=False, tracking=True)
    new_housing = fields.Monetary(
        string='New Housing Allowance', compute='_compute_new_salary', store=True,
        readonly=False, tracking=True)
    new_transport = fields.Monetary(
        string='New Transport Allowance', compute='_compute_new_salary', store=True,
        readonly=False, tracking=True)
    new_other = fields.Monetary(
        string='New Other Allowances', compute='_compute_new_salary', store=True,
        readonly=False, tracking=True)
    new_total = fields.Monetary(
        string='New Total Salary', compute='_compute_totals', store=True)

    wage_increment = fields.Monetary(
        string='Basic Increment', compute='_compute_totals', store=True)
    wage_increment_percent = fields.Float(
        string='Basic Increment %', compute='_compute_totals', store=True,
        digits=(16, 2))
    total_increment = fields.Monetary(
        string='Total Increment', compute='_compute_totals', store=True)
    total_increment_percent = fields.Float(
        string='Total Increment %', compute='_compute_totals', store=True,
        digits=(16, 2))

    approved_by_id = fields.Many2one(
        comodel_name='res.users', string='Approved By', readonly=True, copy=False)
    approved_date = fields.Datetime(string='Approved On', readonly=True, copy=False)
    new_version_id = fields.Many2one(
        comodel_name='hr.version', string='Contract Version Created',
        readonly=True, copy=False, groups='hr_payroll.group_hr_payroll_user')

    @api.depends('employee_id', 'date_effective')
    def _compute_version_id(self):
        for rec in self:
            version = rec._get_effective_version()
            rec.version_id = version
            rec.contract_date_start = version.contract_date_start

    @api.depends('employee_id', 'date_effective')
    def _compute_old_salary(self):
        for rec in self:
            version = rec._get_effective_version()
            for suffix, version_field in SALARY_COMPONENTS.items():
                rec[f'old_{suffix}'] = version[version_field] if version else 0.0

    @api.depends('employee_id')
    def _compute_new_salary(self):
        for rec in self:
            for suffix in SALARY_COMPONENTS:
                rec[f'new_{suffix}'] = rec[f'old_{suffix}']

    @api.depends('old_wage', 'old_housing', 'old_transport', 'old_other',
                 'new_wage', 'new_housing', 'new_transport', 'new_other')
    def _compute_totals(self):
        for rec in self:
            rec.old_total = sum(rec[f'old_{suffix}'] for suffix in SALARY_COMPONENTS)
            rec.new_total = sum(rec[f'new_{suffix}'] for suffix in SALARY_COMPONENTS)
            rec.wage_increment = rec.new_wage - rec.old_wage
            rec.wage_increment_percent = (
                rec.wage_increment / rec.old_wage * 100 if rec.old_wage else 0.0)
            rec.total_increment = rec.new_total - rec.old_total
            rec.total_increment_percent = (
                rec.total_increment / rec.old_total * 100 if rec.old_total else 0.0)

    def _get_effective_version(self):
        self.ensure_one()
        if not self.employee_id or not self.date_effective:
            return self.env['hr.version']
        employee = self.employee_id.sudo()
        if not employee.version_ids:
            return self.env['hr.version']
        return employee._get_version(self.date_effective)

    @api.constrains('employee_id')
    def _check_employee_active(self):
        for rec in self:
            if rec.state == 'draft' and not rec.employee_id.active:
                raise ValidationError(_(
                    'Salary increments can only be recorded for active employees (%s is archived).',
                    rec.employee_id.name))

    @api.constrains('new_wage', 'new_housing', 'new_transport', 'new_other')
    def _check_new_salary(self):
        for rec in self:
            if rec.new_wage <= 0:
                raise ValidationError(_('The new basic salary must be greater than zero.'))
            if min(rec.new_housing, rec.new_transport, rec.new_other) < 0:
                raise ValidationError(_('Allowances cannot be negative.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('hr.salary.increment') or _('New')
        return super().create(vals_list)

    def write(self, vals):
        self.check_access('write')
        if DRAFT_ONLY_FIELDS & set(vals) and any(rec.state != 'draft' for rec in self):
            raise UserError(_('Approved or cancelled increments are locked and cannot be edited.'))
        return super().write(vals)

    def unlink(self):
        self.check_access('unlink')
        if any(rec.state == 'approved' for rec in self):
            raise UserError(_('Approved increments cannot be deleted.'))
        return super().unlink()

    def action_approve(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only draft increments can be approved.'))
            if not rec.employee_id.active:
                raise UserError(_('%s is archived. Only active employees can get an increment.',
                                  rec.employee_id.name))
            if not rec.employee_id.version_ids:
                raise UserError(_('%s has no contract to update.', rec.employee_id.name))
            if all(rec[f'new_{s}'] == rec[f'old_{s}'] for s in SALARY_COMPONENTS):
                raise UserError(_('The new salary is the same as the old salary.'))
            later_versions = rec.employee_id.version_ids.filtered(
                lambda v: v.date_version > rec.date_effective)
            if later_versions:
                raise UserError(_(
                    '%(employee)s already has contract versions after %(date)s (%(dates)s). '
                    'Set the effective date after the latest version, or update those versions first.',
                    employee=rec.employee_id.name,
                    date=rec.date_effective,
                    dates=', '.join(str(d) for d in later_versions.mapped('date_version')),
                ))

            salary_vals = {
                version_field: rec[f'new_{suffix}']
                for suffix, version_field in SALARY_COMPONENTS.items()
            }
            version = rec._create_increment_contract(salary_vals)

            rec.write({
                'state': 'approved',
                'approved_by_id': self.env.uid,
                'approved_date': fields.Datetime.now(),
                'new_version_id': version.id,
            })
            rec.employee_id.message_post(body=_(
                'Salary increment %(ref)s approved: total salary %(old).2f → %(new).2f '
                '(%(pct).2f%%) effective %(date)s.',
                ref=rec.name, old=rec.old_total, new=rec.new_total,
                pct=rec.total_increment_percent, date=rec.date_effective,
            ))
        return True

    def _create_increment_contract(self, salary_vals):
        """Close the contract in force the day before the effective date and
        start a new contract on the effective date with the new salary."""
        self.ensure_one()
        employee = self.employee_id
        date_effective = self.date_effective
        old_version = employee._get_version(date_effective).sudo()
        old_start = old_version.contract_date_start
        old_end = old_version.contract_date_end

        # The contract already starts on the effective date: just update it.
        if old_start == date_effective:
            old_version.write(salary_vals)
            return old_version
        if old_version.date_version == date_effective:
            raise UserError(_(
                '%(employee)s already has a contract version starting on %(date)s that belongs '
                'to the contract started on %(start)s. Remove that version or choose another '
                'effective date.',
                employee=employee.name, date=date_effective, start=old_start))

        new_end = old_end if old_end and old_end >= date_effective else False
        # Writing the end date on one version syncs it to every version of
        # that contract.
        if old_start and (not old_end or old_end >= date_effective):
            old_version.write({'contract_date_end': date_effective - relativedelta(days=1)})

        return employee.create_version({
            'date_version': date_effective,
            'contract_date_start': date_effective,
            'contract_date_end': new_end,
            **salary_vals,
        })

    def action_cancel(self):
        if any(rec.state != 'draft' for rec in self):
            raise UserError(_('Only draft increments can be cancelled.'))
        self.write({'state': 'cancel'})

    def action_draft(self):
        if any(rec.state != 'cancel' for rec in self):
            raise UserError(_('Only cancelled increments can be reset to draft.'))
        self.write({'state': 'draft'})

    def action_open_version(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.employee',
            'res_id': self.employee_id.id,
            'view_mode': 'form',
            'context': {'version_id': self.new_version_id.id},
        }
