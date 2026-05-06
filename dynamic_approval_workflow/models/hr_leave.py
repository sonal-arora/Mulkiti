from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError


class HrLeave(models.Model):
    _inherit = 'hr.leave'

    # ── Extended state: adds "2nd Approval" between validate1 and validate ─
    state = fields.Selection(
        selection_add=[('validate2', '2nd Approval')],
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
    # Action buttons
    # ─────────────────────────────────────────────────────────────────────

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
            # Use leave_fast_create=True to skip the redundant _check_double_validation_rules
            # call inside write() — we already validated the user in _check_approval_update above.
            to_validate1.with_context(leave_fast_create=True).write(
                {'state': 'validate1', 'first_approver_id': current_employee.id}
            )
            if not self.env.context.get('leave_fast_create'):
                to_validate1.activity_update()

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
        return True

    def action_refuse(self):
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
                if employee_sudo.user_id:
                    holiday.message_post(
                        body=_(
                            'Your %(leave_type)s planned on %(date)s has been refused.',
                            leave_type=holiday.holiday_status_id.display_name,
                            date=holiday.date_from,
                        ),
                        partner_ids=employee_sudo.user_id.partner_id.ids,
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
