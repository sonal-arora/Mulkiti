import hashlib
import hmac as _hmac
import logging

from markupsafe import Markup

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.misc import clean_context

_logger = logging.getLogger(__name__)


class HrLeave(models.Model):
    _inherit = 'hr.leave'

    # ── Extended state: inserts "2nd Approval" between validate1 and validate ─
    # ('validate2', '2nd Approval') is the new state
    # ('validate',) is an anchor — tells Odoo to insert validate2 BEFORE validate
    state = fields.Selection(
        selection_add=[('validate2', 'HR Approval'), ('validate',)],
        ondelete={'validate2': 'cascade'},
    )

    # ── Approver mirror fields (read-only, pulled from employee) ───────────
    # NOTE: We intentionally use an explicit compute (NOT related=) here.
    # hr.employee.x_leave_approver_*_id has groups='hr_holidays.group_hr_holidays_user'.
    # Odoo automatically inherits that groups restriction on any related field,
    # which blocks regular employees from reading their own leave's approver.
    # Using an explicit compute + sudo() copies the value without carrying
    # over the field-level groups restriction, so every employee can see
    # who will approve their own request.
    x_leave_approver_1_id = fields.Many2one(
        comodel_name='res.users',
        string='1st Approver',
        compute='_compute_leave_approvers',
        store=True,
        readonly=True,
        # No groups= here — field is intentionally visible to all users
    )
    x_leave_approver_2_id = fields.Many2one(
        comodel_name='res.users',
        string='2nd Approver',
        compute='_compute_leave_approvers',
        store=True,
        readonly=True,
        # No groups= here — field is intentionally visible to all users
    )

    # ── Button-visibility computed field for the 2nd-level approval ────────
    can_validate2 = fields.Boolean(
        compute='_compute_can_validate2',
        export_string_translation=False,
    )

    # ── Refusal reason ────────────────────────────────────────────────────
    refuse_reason = fields.Text(
        string='Reason for Refusal',
        readonly=True,
        copy=False,
    )

    # ─────────────────────────────────────────────────────────────────────
    # Compute: copy approvers from employee using sudo so no group error
    # ─────────────────────────────────────────────────────────────────────

    @api.depends(
        'employee_id.x_leave_approver_1_id',
        'employee_id.x_leave_approver_2_id',
    )
    def _compute_leave_approvers(self):
        """Read the restricted employee fields via sudo and store them on
        hr.leave WITHOUT the groups restriction so every employee can see
        who will approve their own leave request."""
        for leave in self:
            emp = leave.employee_id.sudo()
            leave.x_leave_approver_1_id = emp.x_leave_approver_1_id
            leave.x_leave_approver_2_id = emp.x_leave_approver_2_id

    # ─────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────────

    def _get_first_approvers(self):
        """Return the set of users allowed to give 1st-level approval.
        = employee's direct manager (parent_id.user_id) UNION custom 1st approver."""
        self.ensure_one()
        # Use sudo() to traverse private employee fields regardless of the caller's group.
        employee = self.employee_id.sudo()
        users = self.env['res.users']
        if employee.parent_id.user_id:
            users |= employee.parent_id.user_id
        # x_leave_approver_1_id stored on hr.leave has no group restriction
        if self.x_leave_approver_1_id:
            users |= self.x_leave_approver_1_id
        return users

    def _get_second_approver(self):
        """Return the 2nd approver user, or empty recordset if not configured."""
        self.ensure_one()
        # x_leave_approver_2_id stored on hr.leave has no group restriction
        return self.x_leave_approver_2_id

    def _is_first_approver(self):
        self.ensure_one()
        return self.env.user in self._get_first_approvers()

    def _is_second_approver(self):
        """2nd approver OR HR Manager can approve the 2nd level."""
        self.ensure_one()
        second = self._get_second_approver()
        if not second:
            return False
        is_hr_mgr = self.env.user.has_group('hr_holidays.group_hr_holidays_manager')
        return self.env.user == second or is_hr_mgr

    def _is_time_off_manager(self):
        self.ensure_one()
        return self.employee_id.sudo().leave_manager_id == self.env.user

    def _use_custom_flow(self):
        """True when the employee has at least one 1st-level approver configured
        (manager or custom field).  Falls back to standard Odoo flow otherwise."""
        self.ensure_one()
        return bool(self._get_first_approvers())

    def _has_second_level(self):
        """True when the employee has a 2nd approver set → validate2 state is used."""
        self.ensure_one()
        return bool(self._get_second_approver())

    # ─────────────────────────────────────────────────────────────────────
    # Computed button-visibility fields
    # ─────────────────────────────────────────────────────────────────────

    @api.depends(
        'state', 'employee_id', 'department_id',
        'employee_id.parent_id', 'employee_id.parent_id.user_id',
        'employee_id.x_leave_approver_1_id',
        'employee_id.x_leave_approver_2_id',
    )
    def _compute_can_approve(self):
        """Approve button: 1st approver sees it when state = confirm."""
        custom = self.filtered(lambda h: h._use_custom_flow())
        for h in custom:
            is_officer = self.env.user.has_group('hr_holidays.group_hr_holidays_user')
            h.can_approve = h.state == 'confirm' and (h._is_first_approver() or is_officer)
        others = self - custom
        if others:
            super(HrLeave, others)._compute_can_approve()

    @api.depends(
        'state', 'employee_id', 'department_id',
        'employee_id.parent_id', 'employee_id.parent_id.user_id',
        'employee_id.x_leave_approver_1_id',
        'employee_id.x_leave_approver_2_id',
    )
    def _compute_can_validate2(self):
        """Second Approve button: 2nd approver sees it when state = validate1."""
        for h in self:
            if not h._use_custom_flow() or not h._has_second_level():
                h.can_validate2 = False
                continue
            is_officer = self.env.user.has_group('hr_holidays.group_hr_holidays_user')
            h.can_validate2 = h.state == 'validate1' and (h._is_second_approver() or is_officer)

    @api.depends(
        'state', 'employee_id', 'department_id',
        'employee_id.parent_id', 'employee_id.parent_id.user_id',
        'employee_id.x_leave_approver_1_id',
        'employee_id.x_leave_approver_2_id',
    )
    def _compute_can_validate(self):
        """Validate button: Time Off Manager (final step).
        - No 2nd approver: state must be validate1
        - 2nd approver set: state must be validate2
        """
        custom = self.filtered(lambda h: h._use_custom_flow())
        for h in custom:
            is_officer = self.env.user.has_group('hr_holidays.group_hr_holidays_user')
            is_time_off_mgr = h._is_time_off_manager()
            expected_prev = 'validate2' if h._has_second_level() else 'validate1'
            h.can_validate = h.state == expected_prev and (is_time_off_mgr or is_officer)
        others = self - custom
        if others:
            super(HrLeave, others)._compute_can_validate()

    @api.depends(
        'state', 'employee_id', 'department_id',
        'employee_id.parent_id', 'employee_id.parent_id.user_id',
        'employee_id.x_leave_approver_1_id',
        'employee_id.x_leave_approver_2_id',
    )
    def _compute_can_refuse(self):
        pending = ('confirm', 'validate1', 'validate2')
        custom = self.filtered(lambda h: h._use_custom_flow() and h.state in pending)
        for h in custom:
            is_officer = self.env.user.has_group('hr_holidays.group_hr_holidays_user')
            h.can_refuse = (
                h._is_first_approver()
                or h._is_second_approver()
                or h._is_time_off_manager()
                or is_officer
            )
        others = self - custom
        if others:
            super(HrLeave, others)._compute_can_refuse()

    # ─────────────────────────────────────────────────────────────────────
    # State-transition graph (used by activity panel)
    # ─────────────────────────────────────────────────────────────────────

    def _get_next_states_by_state(self):
        self.ensure_one()
        result = super()._get_next_states_by_state()

        if not self._use_custom_flow():
            return result

        is_officer = self.env.user.has_group('hr_holidays.group_hr_holidays_user')
        is_first = self._is_first_approver()
        is_second = self._is_second_approver()
        is_time_off_mgr = self._is_time_off_manager()
        has_second = self._has_second_level()
        is_own = self.employee_id in self.env.user.employee_ids

        # Always initialise validate2 key so the graph is complete
        result.setdefault('validate2', set())

        # ── 1st approver (confirm → validate1) ───────────────────────────
        if is_first or is_officer:
            result.setdefault('confirm', set()).update({'validate1', 'refuse'})
            result.setdefault('validate1', set()).add('refuse')

        # ── 2nd approver (validate1 → validate2), only when 2nd is set ──
        if has_second and (is_second or is_officer):
            result.setdefault('validate1', set()).update({'validate2', 'refuse'})
            result.setdefault('validate2', set()).add('refuse')

        # ── Time Off Manager (final → validate) ───────────────────────────
        if is_time_off_mgr or is_officer:
            expected_prev = 'validate2' if has_second else 'validate1'
            result.setdefault(expected_prev, set()).add('validate')

        # ── Employee can always cancel a pending leave ─────────────────────
        if is_own:
            result.setdefault('validate1', set()).add('cancel')
            result.setdefault('validate2', set()).add('cancel')

        return result

    # ─────────────────────────────────────────────────────────────────────
    # Permission gate — called by write() and action_* methods
    # ─────────────────────────────────────────────────────────────────────

    def _check_approval_update(self, state, raise_if_not_possible=True):
        if self.env.is_superuser():
            return True

        is_officer = self.env.user.has_group('hr_holidays.group_hr_holidays_user')
        remaining = self.env['hr.leave']

        for holiday in self:
            if not holiday._use_custom_flow():
                remaining += holiday
                continue

            is_first = holiday._is_first_approver()
            is_second = holiday._is_second_approver()
            is_time_off_mgr = holiday._is_time_off_manager()
            has_second = holiday._has_second_level()

            # Duplicate check
            if holiday.state == state:
                if raise_if_not_possible:
                    raise UserError(_("You can't perform the same action twice."))
                return False

            # ── validate1: 1st approval (confirm → validate1) ─────────────
            if state == 'validate1':
                if holiday.state != 'confirm':
                    if raise_if_not_possible:
                        raise UserError(_("1st approval is only possible from the 'To Approve' state."))
                    return False
                if is_first or is_officer:
                    continue
                if raise_if_not_possible:
                    names = ' / '.join(u.name for u in holiday._get_first_approvers()) \
                        or _('the assigned 1st Approver')
                    raise UserError(_(
                        "Only %(names)s (1st Level Approver) or a Time Off Officer "
                        "can approve at the first level.",
                        names=names,
                    ))
                return False

            # ── validate2: 2nd approval (validate1 → validate2) ───────────
            if state == 'validate2':
                if not has_second:
                    if raise_if_not_possible:
                        raise UserError(_("No 2nd Approver is configured for this employee."))
                    return False
                if holiday.state != 'validate1':
                    if raise_if_not_possible:
                        raise UserError(_("2nd approval requires the leave to be at the '1st Approved' stage."))
                    return False
                if is_second or is_officer:
                    continue
                if raise_if_not_possible:
                    second = holiday._get_second_approver()
                    raise UserError(_(
                        "Only %(name)s (2nd Level Approver) or an HR Manager "
                        "can approve at the second level.",
                        name=second.name,
                    ))
                return False

            # ── validate: final approval ───────────────────────────────────
            if state == 'validate':
                expected_prev = 'validate2' if has_second else 'validate1'
                if holiday.state != expected_prev:
                    if raise_if_not_possible:
                        raise UserError(_("Final approval is not possible from the current state."))
                    return False
                if is_time_off_mgr or is_officer:
                    continue
                if raise_if_not_possible:
                    mgr = holiday.employee_id.sudo().leave_manager_id
                    raise UserError(_(
                        "Only %(name)s (Time Off Manager) or a Time Off Officer "
                        "can give the final approval.",
                        name=mgr.name if mgr else _('the Time Off Manager'),
                    ))
                return False

            # ── refuse ─────────────────────────────────────────────────────
            if state == 'refuse':
                if holiday.state in ('confirm', 'validate1', 'validate2'):
                    if is_first or is_second or is_time_off_mgr or is_officer:
                        continue
                    if raise_if_not_possible:
                        raise UserError(_("Only a leave approver or Time Off Officer can refuse this leave."))
                    return False
                remaining += holiday
                continue

            remaining += holiday

        if remaining:
            return super(HrLeave, remaining)._check_approval_update(
                state, raise_if_not_possible=raise_if_not_possible,
            )
        return True

    # ─────────────────────────────────────────────────────────────────────
    # Override _check_validity
    # ─────────────────────────────────────────────────────────────────────

    def _validate_leave_request(self):
        """
        Override: suppress the standard Odoo 'Your leave has been accepted' email
        for custom-flow leaves because _send_employee_status_email() already sends
        a single branded HTML email to the employee.
        Standard flow leaves still get the default Odoo notification.
        """
        custom = self.filtered(lambda l: l._use_custom_flow())
        standard = self - custom

        if standard:
            super(HrLeave, standard)._validate_leave_request()

        if custom:
            # Run everything in _validate_leave_request EXCEPT the message_post
            # that sends "Your leave has been accepted" to the employee.
            custom._create_resource_leave()
            meeting_holidays = custom.filtered(
                lambda l: l.holiday_status_id.create_calendar_meeting
            )
            if meeting_holidays:
                Meeting = self.env['calendar.event']
                Meeting.check_access('create')
                meeting_values_for_user_id = meeting_holidays._prepare_holidays_meeting_values()
                meetings = self.env['calendar.event']
                for user_id, meeting_values in meeting_values_for_user_id.items():
                    meetings += Meeting.with_user(user_id or self.env.uid).sudo().with_context(
                        clean_context({
                            **self.env.context,
                            'allowed_company_ids': [],
                            'no_mail_to_attendees': True,
                            'calendar_no_videocall': True,
                            'active_model': self._name,
                        })
                    ).create(meeting_values)
                Holiday = self.env['hr.leave']
                for meeting in meetings:
                    Holiday.browse(meeting.res_id).meeting_id = meeting
            # NOTE: message_post("Your leave has been accepted") intentionally skipped —
            # _send_employee_status_email(status='fully_approved') handles the email.

    def _check_validity(self):
        """
        Odoo calls _check_validity() after every write() that touches 'state'.
        For our custom multi-level approval flow, the allocation check already
        ran when the employee submitted the leave (confirm state).

        Re-running it at intermediate approval steps (validate1, validate2)
        causes false "no allocation" errors because:
          • The allocation IS there (it passed at submission time)
          • The approver user might not be the Time Off Officer, so the
            context user check produces wrong results

        Fix: skip the allocation re-check for custom-flow leaves that are
        already in an intermediate approval state.  The check still runs
        normally for the final validate, refuse, cancel transitions.
        """
        # Leaves in intermediate approval stages that use the custom flow
        # have already been validated at submission time — skip re-check.
        intermediate = ('validate1', 'validate2')
        to_skip = self.filtered(
            lambda l: l._use_custom_flow() and l.state in intermediate
        )
        to_check = self - to_skip

        if to_check:
            super(HrLeave, to_check)._check_validity()

    # ─────────────────────────────────────────────────────────────────────
    # Override _check_double_validation_rules
    # ─────────────────────────────────────────────────────────────────────

    def _check_double_validation_rules(self, employees, state):
        """
        Standard Odoo raises AccessError in write() when state → validate1
        and the current user is not the employee's leave_manager_id or an Officer.

        We skip that restriction for:
          • Users who are the custom 1st level approver (x_leave_approver_1_id)
          • Users who are the custom 2nd level approver (x_leave_approver_2_id)
          • Users who are the direct manager (parent_id.user_id)

        All other cases fall through to the standard check.
        """
        # HR Manager → no restriction
        if self.env.user.has_group('hr_holidays.group_hr_holidays_manager'):
            return

        # Time Off Officer → no restriction
        if self.env.user.has_group('hr_holidays.group_hr_holidays_user'):
            return

        # Normalise employees argument — can be int (from create) or recordset (from write)
        if isinstance(employees, int):
            employees = self.env['hr.employee'].browse(employees)

        if not employees:
            return

        current_user = self.env.user

        # Check if user is a custom approver for ALL employees in the set.
        # If even one employee has this user as their custom approver, allow it.
        is_custom_approver = any(
            emp.sudo().x_leave_approver_1_id == current_user
            or emp.sudo().x_leave_approver_2_id == current_user
            or emp.sudo().parent_id.user_id == current_user
            for emp in employees
        )

        if is_custom_approver:
            return  # Custom approver — skip standard leave_manager_id check

        # Not a custom approver → run standard check
        super()._check_double_validation_rules(employees, state)

    # ─────────────────────────────────────────────────────────────────────
    # Create override — send employee confirmation same time as activity mail
    # ─────────────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        leaves = super().create(vals_list)
        for leave in leaves:
            if leave.state == 'confirm' and leave.employee_id:
                leave._send_employee_submission_email()
        return leaves

    # ─────────────────────────────────────────────────────────────────────
    # Action buttons
    # ─────────────────────────────────────────────────────────────────────

    @api.constrains('holiday_status_id', 'date_from', 'employee_id')
    def _check_probation_period(self):
        """Block Annual Leave if employee is still in probation period.
        Leave Officers / HR Managers are exempt from this check."""
        # Skip check for Time Off Officers and HR Managers
        is_officer = self.env.user.has_group('hr_holidays.group_hr_holidays_user')
        is_hr_mgr  = self.env.user.has_group('hr_holidays.group_hr_holidays_manager')
        if is_officer or is_hr_mgr:
            return

        for leave in self:
            emp = leave.employee_id
            if not emp:
                continue
            probation_end = emp.sudo().probation_end_date
            if probation_end and leave.date_from and leave.date_from.date() < probation_end:
                raise ValidationError(_(
                    "%(employee)s is still in the probation period (ends %(date)s). "
                    "Leave cannot be taken before the probation period ends.",
                    employee=emp.name,
                    date=probation_end.strftime('%d %b %Y'),
                ))

    def action_confirm(self):
        """Override: after confirming, send email to 1st level approver."""
        result = super().action_confirm()
        for leave in self:
            if leave._use_custom_flow():
                first_approvers = leave._get_first_approvers()
                if first_approvers:
                    leave._send_leave_approval_email(first_approvers, '1st Approval')
        return result

    def action_approve(self, check_state=True):
        """Handles both 'Approve' (confirm→validate1) and 'Validate' (final step)."""
        current_employee = self.env.user.employee_id
        to_validate1 = self.env['hr.leave']
        to_validate_final = self.env['hr.leave']
        remaining = self.env['hr.leave']

        for leave in self:
            if not leave._use_custom_flow():
                remaining += leave
                continue

            if leave.state == 'confirm' and (not check_state or leave.can_approve):
                # 1st approval
                leave._check_approval_update('validate1')
                to_validate1 += leave
            elif leave.state in ('validate1', 'validate2') and (not check_state or leave.can_validate):
                # Final approval
                leave._check_approval_update('validate')
                to_validate_final += leave
            else:
                remaining += leave

        if to_validate1:
            to_validate1.with_context(leave_fast_create=True).write(
                {'state': 'validate1', 'first_approver_id': current_employee.id}
            )
            if not self.env.context.get('leave_fast_create'):
                to_validate1.activity_update()
            for leave in to_validate1:
                # Notify employee: chatter note + HTML email
                leave._notify_employee_leave_status(
                    approved_by=self.env.user,
                    status='approved_1st',
                )
                leave._send_employee_status_email(
                    approved_by=self.env.user,
                    status='approved_1st',
                )
                # Notify next approver: 2nd approver if set, else Time Off Manager
                emp_sudo = leave.employee_id.sudo()
                next_approver = leave._get_second_approver() or emp_sudo.leave_manager_id
                if next_approver:
                    stage = '2nd Approval' if leave._has_second_level() else 'Final Approval'
                    leave._send_leave_approval_email(next_approver, stage)

        if to_validate_final:
            to_validate_final._action_validate(check_state)

        if remaining:
            super(HrLeave, remaining).action_approve(check_state=check_state)

        return True

    def action_second_approve(self):
        """2nd-level approval: validate1 → validate2."""
        for leave in self:
            leave._check_approval_update('validate2')
        # Use leave_fast_create=True to skip the redundant _check_double_validation_rules
        # call inside write() — we already validated the user in _check_approval_update above.
        self.with_context(leave_fast_create=True).write({'state': 'validate2'})
        if not self.env.context.get('leave_fast_create'):
            self.activity_update()
        for leave in self:
            if leave._use_custom_flow():
                # Notify employee: chatter note + HTML email
                leave._notify_employee_leave_status(
                    approved_by=self.env.user,
                    status='approved_2nd',
                )
                leave._send_employee_status_email(
                    approved_by=self.env.user,
                    status='approved_2nd',
                )
                # Notify Time Off Manager (final approver) for final validation
                final_approver = leave.employee_id.sudo().leave_manager_id
                if final_approver:
                    leave._send_leave_approval_email(final_approver, 'Final Approval')
        return True

    def _action_validate(self, check_state=True):
        """Override: after final validation, notify employee fully approved."""
        result = super()._action_validate(check_state)
        for leave in self:
            # Notify employee: chatter + inbox + email
            leave._notify_employee_leave_status(
                approved_by=self.env.user,
                status='fully_approved',
            )
            leave._send_employee_status_email(
                approved_by=self.env.user,
                status='fully_approved',
            )
        return result

    def action_open_refuse_wizard(self):
        """Open a wizard to collect refusal reason before refusing the leave."""
        wizard = self.env['hr.leave.refuse.wizard'].create({
            'leave_ids': [(6, 0, self.ids)],
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Refuse Leave'),
            'res_model': 'hr.leave.refuse.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_refuse(self):
        # Open wizard to collect reason — unless already called from wizard
        if not self.env.context.get('skip_refuse_wizard'):
            return self.action_open_refuse_wizard()

        pending = ('confirm', 'validate1', 'validate2')
        custom = self.filtered(lambda l: l._use_custom_flow() and l.state in pending)
        remaining = self - custom

        if custom:
            current_employee = self.env.user.employee_id
            for leave in custom:
                leave._check_approval_update('refuse')
            # Use leave_fast_create=True to skip redundant checks inside write()
            custom.with_context(leave_fast_create=True).write(
                {'state': 'refuse', 'first_approver_id': current_employee.id}
            )
            custom.mapped('meeting_id').write({'active': False})
            for holiday in custom:
                employee_sudo = holiday.employee_id.sudo()
                reason = holiday.refuse_reason or ''

                # Format date nicely
                date_str = (
                    holiday.date_from.strftime('%d %b %Y')
                    if holiday.date_from else ''
                )

                # Build HTML body using Markup so tags render properly
                body_msg = Markup(
                    'Your <strong>%(leave_type)s</strong> planned on '
                    '<strong>%(date)s</strong> has been refused.'
                ) % {
                    'leave_type': holiday.holiday_status_id.display_name,
                    'date': date_str,
                }
                if reason:
                    body_msg += Markup(
                        '<br/><br/><strong>Reason:</strong> %(reason)s'
                    ) % {'reason': reason}

                if employee_sudo.user_id:
                    holiday.message_post(
                        body=body_msg,
                        partner_ids=employee_sudo.user_id.partner_id.ids,
                        message_type='comment',
                        subtype_xmlid='mail.mt_comment',
                    )
            custom.activity_update()

        if remaining:
            return super(HrLeave, remaining).action_refuse()
        return True

    # ─────────────────────────────────────────────────────────────────────
    # Activity routing — notify correct person at each stage
    # ─────────────────────────────────────────────────────────────────────

    def _get_responsible_for_approval(self):
        self.ensure_one()

        if not self._use_custom_flow():
            return super()._get_responsible_for_approval()

        employee = self.employee_id.sudo()
        if self.state == 'confirm':
            # Notify 1st approvers (prefer custom; fall back to manager)
            if self.x_leave_approver_1_id:
                return self.x_leave_approver_1_id
            if employee.parent_id.user_id:
                return employee.parent_id.user_id

        elif self.state == 'validate1':
            # Notify 2nd approver if set, else Time Off Manager
            second = self._get_second_approver()
            if second:
                return second
            if employee.leave_manager_id:
                return employee.leave_manager_id

        elif self.state == 'validate2':
            # Notify Time Off Manager for final approval
            if employee.leave_manager_id:
                return employee.leave_manager_id

        return super()._get_responsible_for_approval()

    # ─────────────────────────────────────────────────────────────────────
    # Email notification helpers
    # ─────────────────────────────────────────────────────────────────────

    def _get_email_approval_token(self, action, approver_id):
        """
        Generate a secure HMAC-SHA256 token tied to this leave record,
        the requested action, and the intended approver.
        """
        self.ensure_one()
        secret = self.env['ir.config_parameter'].sudo().get_param(
            'database.secret', 'odoo-default-secret'
        )
        msg = f'{self.id}:{action}:{approver_id}'
        return _hmac.new(
            secret.encode('utf-8'),
            msg.encode('utf-8'),
            hashlib.sha256,
        ).hexdigest()[:32]

    def _send_leave_approval_email(self, approvers, stage_label):
        """
        Send an approval-request email to each user in *approvers* with
        direct Approve / Refuse hyperlinks pointing at the controller.

        :param approvers: res.users recordset
        :param stage_label: e.g. '1st Approval', '2nd Approval', 'Final Approval'
        """
        self.ensure_one()
        if not approvers:
            return

        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        emp = self.employee_id
        leave_type = self.holiday_status_id.name or ''
        date_from_str = self.date_from.strftime('%d %b %Y') if self.date_from else ''
        date_to_str = self.date_to.strftime('%d %b %Y') if self.date_to else ''
        duration = self.number_of_days

        for approver in approvers:
            if not approver or not approver.email:
                continue

            approve_token = self._get_email_approval_token('approve', approver.id)
            refuse_token = self._get_email_approval_token('refuse', approver.id)
            approve_url = (
                f'{base_url}/leave/action/approve/{self.id}/{approver.id}/{approve_token}'
            )
            refuse_url = (
                f'{base_url}/leave/action/refuse/{self.id}/{approver.id}/{refuse_token}'
            )

            subject = (
                f'[Action Required] Leave — {emp.name}'
                f' ({leave_type}: {date_from_str} → {date_to_str})'
            )

            body_html = f"""
<div style="font-family:Arial,sans-serif;max-width:620px;margin:0 auto;color:#333;">
  <div style="background:#875A7B;padding:22px 28px;border-radius:6px 6px 0 0;">
    <h2 style="color:#fff;margin:0;font-size:17px;font-weight:600;">
      Leave Approval Required &mdash; {stage_label}
    </h2>
  </div>
  <div style="border:1px solid #ddd;border-top:none;border-radius:0 0 6px 6px;padding:28px 28px 24px;">
    <p style="margin:0 0 16px;">Dear <strong>{approver.name}</strong>,</p>
    <p style="margin:0 0 20px;color:#555;">
      The following leave request requires your approval:
    </p>
    <table style="width:100%;border-collapse:collapse;font-size:14px;margin-bottom:28px;">
      <tr style="background:#f7f3f6;">
        <td style="padding:10px 14px;border:1px solid #e5e5e5;font-weight:bold;width:36%;">Employee</td>
        <td style="padding:10px 14px;border:1px solid #e5e5e5;">{emp.name}</td>
      </tr>
      <tr>
        <td style="padding:10px 14px;border:1px solid #e5e5e5;font-weight:bold;">Department</td>
        <td style="padding:10px 14px;border:1px solid #e5e5e5;">{emp.department_id.name or '&mdash;'}</td>
      </tr>
      <tr style="background:#f7f3f6;">
        <td style="padding:10px 14px;border:1px solid #e5e5e5;font-weight:bold;">Leave Type</td>
        <td style="padding:10px 14px;border:1px solid #e5e5e5;">{leave_type}</td>
      </tr>
      <tr>
        <td style="padding:10px 14px;border:1px solid #e5e5e5;font-weight:bold;">From</td>
        <td style="padding:10px 14px;border:1px solid #e5e5e5;">{date_from_str}</td>
      </tr>
      <tr style="background:#f7f3f6;">
        <td style="padding:10px 14px;border:1px solid #e5e5e5;font-weight:bold;">To</td>
        <td style="padding:10px 14px;border:1px solid #e5e5e5;">{date_to_str}</td>
      </tr>
      <tr>
        <td style="padding:10px 14px;border:1px solid #e5e5e5;font-weight:bold;">Duration</td>
        <td style="padding:10px 14px;border:1px solid #e5e5e5;">{duration:.1f} day(s)</td>
      </tr>
    </table>
    <div style="text-align:center;margin:8px 0 24px;">
      <a href="{approve_url}"
         style="display:inline-block;padding:13px 38px;background:#28a745;color:#fff;
                text-decoration:none;border-radius:4px;font-size:15px;font-weight:bold;
                margin-right:14px;">
        &#10003;&nbsp; Approve
      </a>
      <a href="{refuse_url}"
         style="display:inline-block;padding:13px 38px;background:#dc3545;color:#fff;
                text-decoration:none;border-radius:4px;font-size:15px;font-weight:bold;">
        &#10007;&nbsp; Refuse
      </a>
    </div>
    <p style="font-size:12px;color:#aaa;text-align:center;margin:0;">
      You will be asked to log in if you are not already signed in.&nbsp;
      <a href="{base_url}/odoo/time-off" style="color:#875A7B;">Open Time Off in Odoo</a>
    </p>
  </div>
</div>
"""

            self.env['mail.mail'].sudo().create({
                'subject': subject,
                'body_html': body_html,
                'email_to': approver.email_formatted,
                'author_id': self.env.company.partner_id.id,
                'reply_to': False,
                'auto_delete': True,
            }).send()

    def _send_employee_submission_email(self):
        """Send a confirmation email to the employee when they submit a leave request."""
        self.ensure_one()
        emp = self.employee_id
        if not emp:
            return

        # Try all possible email sources
        email = (
            emp.sudo().work_email
            or (emp.sudo().user_id and emp.sudo().user_id.email)
            or (emp.sudo().user_id and emp.sudo().user_id.partner_id
                and emp.sudo().user_id.partner_id.email)
            or self.env.user.email
        )

        _logger.info(
            'Leave submission email: employee=%s email=%s leave_id=%s',
            emp.name, email, self.id
        )

        if not email:
            _logger.warning('No email found for employee %s, skipping submission email.', emp.name)
            return

        leave_type    = self.holiday_status_id.name or ''
        date_from_str = self.date_from.strftime('%d/%m/%Y') if self.date_from else ''
        date_to_str   = self.date_to.strftime('%d/%m/%Y') if self.date_to else ''
        duration      = self.number_of_days
        description   = self.name or ''
        base_url      = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        leave_url     = f'{base_url}/web#model=hr.leave&id={self.id}&view_type=form'
        desc_row      = (
            f'<tr style="background:#f7f3f6;">'
            f'<td style="padding:10px 14px;border:1px solid #e5e5e5;font-weight:bold;">Description</td>'
            f'<td style="padding:10px 14px;border:1px solid #e5e5e5;">{description}</td></tr>'
            if description else ''
        )

        subject = f'Leave Request Submitted — {leave_type} ({date_from_str})'

        body_html = f"""
<div style="font-family:Arial,sans-serif;max-width:620px;margin:0 auto;color:#333;">
  <div style="background:#875A7B;padding:22px 28px;border-radius:6px 6px 0 0;">
    <h2 style="color:#fff;margin:0;font-size:17px;font-weight:600;">
      Leave Request Submitted Successfully
    </h2>
  </div>
  <div style="border:1px solid #ddd;border-top:none;border-radius:0 0 6px 6px;padding:28px 28px 24px;">
    <p style="margin:0 0 16px;">Dear <strong>{emp.name}</strong>,</p>
    <p style="margin:0 0 20px;color:#555;">
      Your leave request has been submitted and is pending approval. Below are the details:
    </p>
    <table style="width:100%;border-collapse:collapse;font-size:14px;margin-bottom:24px;">
      <tr style="background:#f7f3f6;">
        <td style="padding:10px 14px;border:1px solid #e5e5e5;font-weight:bold;width:36%;">Leave Type</td>
        <td style="padding:10px 14px;border:1px solid #e5e5e5;">{leave_type}</td>
      </tr>
      <tr>
        <td style="padding:10px 14px;border:1px solid #e5e5e5;font-weight:bold;">From</td>
        <td style="padding:10px 14px;border:1px solid #e5e5e5;">{date_from_str}</td>
      </tr>
      <tr style="background:#f7f3f6;">
        <td style="padding:10px 14px;border:1px solid #e5e5e5;font-weight:bold;">To</td>
        <td style="padding:10px 14px;border:1px solid #e5e5e5;">{date_to_str}</td>
      </tr>
      <tr>
        <td style="padding:10px 14px;border:1px solid #e5e5e5;font-weight:bold;">Duration</td>
        <td style="padding:10px 14px;border:1px solid #e5e5e5;">{duration:.1f} day(s)</td>
      </tr>
      {desc_row}
      <tr style="background:#f7f3f6;">
        <td style="padding:10px 14px;border:1px solid #e5e5e5;font-weight:bold;">Status</td>
        <td style="padding:10px 14px;border:1px solid #e5e5e5;">
          <span style="background:#fff3cd;color:#856404;padding:3px 10px;
                       border-radius:10px;font-size:13px;font-weight:bold;">
            Pending Approval
          </span>
        </td>
      </tr>
    </table>
    <p style="color:#555;font-size:13px;">
      You will receive another email once your request is approved or refused.
    </p>
    <div style="text-align:center;margin-top:20px;">
      <a href="{leave_url}"
         style="display:inline-block;padding:11px 30px;background:#875A7B;color:#fff;
                text-decoration:none;border-radius:4px;font-size:14px;font-weight:bold;">
        View Leave Request
      </a>
    </div>
  </div>
  <p style="text-align:center;font-size:11px;color:#aaa;margin-top:12px;">
    This is an automated message from {self.env.company.name}.
  </p>
</div>"""

        try:
            mail = self.env['mail.mail'].sudo().create({
                'subject': subject,
                'body_html': body_html,
                'email_to': email,
                'email_from': (
                    f"{self.env.company.name} <{self.env.company.email}>"
                    if self.env.company.email else self.env.company.name
                ),
                'author_id': self.env.company.partner_id.id,
                'reply_to': False,
                'auto_delete': True,
            })
            mail.send(raise_exception=False)
            _logger.info('Leave submission email sent to %s (mail.mail id=%s)', email, mail.id)
        except Exception as e:
            _logger.error('Failed to send leave submission email to %s: %s', email, str(e))

    def _send_employee_status_email(self, approved_by, status):
        """
        Send email to employee about leave status change.
        status: 'approved_1st' | 'approved_2nd' | 'fully_approved' | 'refused'
        """
        self.ensure_one()
        emp = self.employee_id
        if not emp:
            return
        email = (
            emp.sudo().work_email
            or (emp.sudo().user_id and emp.sudo().user_id.email)
        )
        if not email:
            return

        leave_type    = self.holiday_status_id.name or ''
        date_from_str = self.date_from.strftime('%d/%m/%Y') if self.date_from else ''
        date_to_str   = self.date_to.strftime('%d/%m/%Y') if self.date_to else ''
        duration      = self.number_of_days
        approver_name = approved_by.name if approved_by else 'HR'
        base_url      = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        leave_url     = f'{base_url}/web#model=hr.leave&id={self.id}&view_type=form'
        refuse_reason = self.refuse_reason or ''

        # Status-specific content
        if status == 'approved_1st':
            header_color = '#1976D2'
            header_title = '✅ Leave — 1st Approval Done'
            status_badge = '<span style="background:#d1ecf1;color:#0c5460;padding:4px 12px;border-radius:10px;font-weight:bold;">1st Approval Completed</span>'
            status_msg   = f'Your leave request has been approved by <strong>{approver_name}</strong>. It is now pending the next level of approval.'
            subject      = f'Leave Update: 1st Approval Done — {leave_type} ({date_from_str})'

        elif status == 'approved_2nd':
            header_color = '#388E3C'
            header_title = '✅ Leave — 2nd Approval Done'
            status_badge = '<span style="background:#d4edda;color:#155724;padding:4px 12px;border-radius:10px;font-weight:bold;">2nd Approval Completed</span>'
            status_msg   = f'Your leave request has been approved by <strong>{approver_name}</strong>. It is now pending final approval from HR.'
            subject      = f'Leave Update: 2nd Approval Done — {leave_type} ({date_from_str})'

        elif status == 'fully_approved':
            header_color = '#2E7D32'
            header_title = '🎉 Leave Fully Approved!'
            status_badge = '<span style="background:#d4edda;color:#155724;padding:4px 12px;border-radius:10px;font-weight:bold;">Fully Approved</span>'
            status_msg   = f'Your leave request has been <strong>fully approved</strong> by <strong>{approver_name}</strong>. Enjoy your time off!'
            subject      = f'Leave Approved — {leave_type} ({date_from_str})'

        elif status == 'refused':
            header_color = '#C62828'
            header_title = '❌ Leave Request Refused'
            status_badge = '<span style="background:#f8d7da;color:#721c24;padding:4px 12px;border-radius:10px;font-weight:bold;">Refused</span>'
            status_msg   = f'Your leave request has been <strong>refused</strong> by <strong>{approver_name}</strong>.'
            subject      = f'Leave Refused — {leave_type} ({date_from_str})'
        else:
            return

        reason_row = (
            f'<tr style="background:#fff3cd;">'
            f'<td style="padding:10px 14px;border:1px solid #e5e5e5;font-weight:bold;color:#856404;">Reason</td>'
            f'<td style="padding:10px 14px;border:1px solid #e5e5e5;color:#856404;">{refuse_reason}</td></tr>'
            if status == 'refused' and refuse_reason else ''
        )

        body_html = f"""
<div style="font-family:Arial,sans-serif;max-width:620px;margin:0 auto;color:#333;">
  <div style="background:{header_color};padding:22px 28px;border-radius:6px 6px 0 0;">
    <h2 style="color:#fff;margin:0;font-size:17px;font-weight:600;">{header_title}</h2>
  </div>
  <div style="border:1px solid #ddd;border-top:none;border-radius:0 0 6px 6px;padding:28px 28px 24px;">
    <p style="margin:0 0 16px;">Dear <strong>{emp.name}</strong>,</p>
    <p style="margin:0 0 20px;color:#555;">{status_msg}</p>
    <table style="width:100%;border-collapse:collapse;font-size:14px;margin-bottom:24px;">
      <tr style="background:#f7f3f6;">
        <td style="padding:10px 14px;border:1px solid #e5e5e5;font-weight:bold;width:36%;">Leave Type</td>
        <td style="padding:10px 14px;border:1px solid #e5e5e5;">{leave_type}</td>
      </tr>
      <tr>
        <td style="padding:10px 14px;border:1px solid #e5e5e5;font-weight:bold;">From</td>
        <td style="padding:10px 14px;border:1px solid #e5e5e5;">{date_from_str}</td>
      </tr>
      <tr style="background:#f7f3f6;">
        <td style="padding:10px 14px;border:1px solid #e5e5e5;font-weight:bold;">To</td>
        <td style="padding:10px 14px;border:1px solid #e5e5e5;">{date_to_str}</td>
      </tr>
      <tr>
        <td style="padding:10px 14px;border:1px solid #e5e5e5;font-weight:bold;">Duration</td>
        <td style="padding:10px 14px;border:1px solid #e5e5e5;">{duration:.1f} day(s)</td>
      </tr>
      <tr style="background:#f7f3f6;">
        <td style="padding:10px 14px;border:1px solid #e5e5e5;font-weight:bold;">Approved By</td>
        <td style="padding:10px 14px;border:1px solid #e5e5e5;">{approver_name}</td>
      </tr>
      <tr>
        <td style="padding:10px 14px;border:1px solid #e5e5e5;font-weight:bold;">Status</td>
        <td style="padding:10px 14px;border:1px solid #e5e5e5;">{status_badge}</td>
      </tr>
      {reason_row}
    </table>
    <div style="text-align:center;margin-top:20px;">
      <a href="{leave_url}"
         style="display:inline-block;padding:11px 30px;background:{header_color};color:#fff;
                text-decoration:none;border-radius:4px;font-size:14px;font-weight:bold;">
        View Leave Request
      </a>
    </div>
  </div>
  <p style="text-align:center;font-size:11px;color:#aaa;margin-top:12px;">
    This is an automated message from {self.env.company.name}.
  </p>
</div>"""

        # email_from = Company Name — outgoing server email will be used anyway,
        # so name and email must match to avoid "Name <wrong@email.com>" mismatch.
        company = self.env.company
        from_email = f"{company.name} <{company.email}>" if company.email else company.name

        try:
            mail = self.env['mail.mail'].sudo().create({
                'subject': subject,
                'body_html': body_html,
                'email_to': email,
                'email_from': from_email,
                'author_id': company.partner_id.id,
                'reply_to': False,
                'auto_delete': True,
            })
            mail.send(raise_exception=False)
            _logger.info('Leave status email [%s] sent to %s', status, email)
        except Exception as e:
            _logger.error('Failed to send leave status email to %s: %s', email, str(e))

    def _notify_employee_leave_status(self, approved_by, status):
        """
        Notify employee about leave status change via:
          1. Odoo chatter message (visible on the leave form)
          2. Odoo inbox notification (bell icon)
          3. Email (via message_post auto-send)

        status: 'approved_1st' | 'approved_2nd' | 'fully_approved' | 'refused'
        """
        self.ensure_one()
        emp = self.employee_id
        if not emp or not emp.sudo().user_id:
            # Fallback to raw email if no Odoo user linked
            self._send_employee_status_email(approved_by=approved_by, status=status)
            return

        partner = emp.sudo().user_id.partner_id
        approver_name = approved_by.name if approved_by else 'HR'
        leave_type = self.holiday_status_id.name or ''
        date_from_str = self.date_from.strftime('%d/%m/%Y') if self.date_from else ''
        date_to_str = self.date_to.strftime('%d/%m/%Y') if self.date_to else ''

        if status == 'approved_1st':
            icon = '🕐'
            subject = f'Leave Update: 1st Approval Done — {leave_type} ({date_from_str})'
            msg = Markup(
                '<b>%(icon)s 1st Approval Completed</b><br/>'
                'Your <b>%(leave_type)s</b> request (%(from)s → %(to)s) has been '
                'approved by <b>%(approver)s</b>.<br/>'
                'It is now pending the next level of approval.'
            ) % {
                'icon': icon, 'leave_type': leave_type,
                'from': date_from_str, 'to': date_to_str,
                'approver': approver_name,
            }
        elif status == 'approved_2nd':
            icon = '🕑'
            subject = f'Leave Update: 2nd Approval Done — {leave_type} ({date_from_str})'
            msg = Markup(
                '<b>%(icon)s 2nd Approval Completed</b><br/>'
                'Your <b>%(leave_type)s</b> request (%(from)s → %(to)s) has been '
                'approved by <b>%(approver)s</b>.<br/>'
                'It is now pending final approval from HR.'
            ) % {
                'icon': icon, 'leave_type': leave_type,
                'from': date_from_str, 'to': date_to_str,
                'approver': approver_name,
            }
        elif status == 'fully_approved':
            icon = '✅'
            subject = f'Leave Approved — {leave_type} ({date_from_str})'
            msg = Markup(
                '<b>%(icon)s Leave Fully Approved!</b><br/>'
                'Your <b>%(leave_type)s</b> request (%(from)s → %(to)s) has been '
                '<b>fully approved</b> by <b>%(approver)s</b>.<br/>'
                'Enjoy your time off!'
            ) % {
                'icon': icon, 'leave_type': leave_type,
                'from': date_from_str, 'to': date_to_str,
                'approver': approver_name,
            }
        elif status == 'refused':
            reason = self.refuse_reason or ''
            subject = f'Leave Refused — {leave_type} ({date_from_str})'
            msg = Markup(
                '<b>❌ Leave Request Refused</b><br/>'
                'Your <b>%(leave_type)s</b> request (%(from)s → %(to)s) has been '
                '<b>refused</b> by <b>%(approver)s</b>.'
            ) % {
                'leave_type': leave_type,
                'from': date_from_str, 'to': date_to_str,
                'approver': approver_name,
            }
            if reason:
                msg += Markup('<br/><b>Reason:</b> %(reason)s') % {'reason': reason}
        else:
            return

        try:
            # Use 'mail.mt_note' (internal note) so Odoo does NOT send its own
            # notification email. The single branded HTML email is sent exclusively
            # by _send_employee_status_email() called right after this.
            self.message_post(
                subject=subject,
                body=msg,
                message_type='comment',
                subtype_xmlid='mail.mt_note',
            )
        except Exception as e:
            _logger.error('Failed to post chatter note for employee %s on leave %s: %s', emp.name, self.id, str(e))
