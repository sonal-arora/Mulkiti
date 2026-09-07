# Copyright 2026 Mulkiti
import logging
from datetime import timedelta

from pytz import timezone, utc

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# How long before Ageing End the "about to breach" reminder email goes out.
TAT_REMINDER_LEAD_MINUTES = 15

# Stage names that (re)start the ageing clock / mark the Overdue stage,
# matched case- and punctuation-insensitively (e.g. "To Do" == "To-Do").
# Task stages are per-project records (no single global xmlid), so matching
# is done by normalized name rather than by external id.
TAT_AGEING_START_STAGE_NAMES = {'todo'}
TAT_OVERDUE_STAGE_NAMES = {'overdue'}
TAT_SLA_START_STAGE_NAMES = {'inprogress'}
SLA_CARRY_FORWARD_STAGE_NAMES = {'carryforward'}


def _tat_normalize_stage_name(name):
    return ''.join(c for c in (name or '').lower() if c.isalnum())


class ProjectTask(models.Model):
    _inherit = 'project.task'

    # ── Classification (reuses project_task_category's masters) ───────────
    main_category_id = fields.Many2one(
        'project.task.main.category', string='Main Category',
        help="Pick this first — it narrows down the Sub Category choices below.",
    )
    sub_category_id = fields.Many2one(
        'project.task.sub.category', string='Sub Category',
        help="Options are limited to the selected Main Category. Its "
             "Working Hours is applied automatically to Working Hours below.",
    )
    priority_id = fields.Many2one(
        'project.task.priority', string='TAT Priority',
        help="Drives this ticket's TAT/SLA deadline. Defaults from the Sub "
             "Category's Default Priority when a Sub Category is set.",
    )
    tag_id = fields.Many2one(
        'hr.employee.category', string='Ticket Tag',
        help="Employees carrying this tag are notified about this ticket's "
             "status changes, the pre-expiry reminder, and the overdue alert.",
    )
    resource_calendar_id = fields.Many2one(
        'resource.calendar', string='Working Hours Calendar',
        default=lambda self: self.env.company.resource_calendar_id,
        help="Working-hours calendar used to decide which days count as "
             "working days for this ticket's ageing. Defaults from the "
             "company's calendar — change it here to use a different one "
             "just for this ticket.",
    )
    working_hours = fields.Float(
        string='Working Hours (Hrs/Day)', digits=(16, 2),
        help="Manually entered total working hours per day — filled in "
             "automatically from the Sub Category when one is selected, "
             "and editable afterwards. Purely informational: it doesn't "
             "drive any calculation (see Working Hours Calendar above for "
             "the field that actually does).",
    )

    # ── Ageing ────────────────────────────────────────────────────────
    ageing_start_date = fields.Datetime(
        string='Ageing Start', readonly=True, copy=False,
        help="When ticket ageing started counting: ticket creation, or "
             "(re-)entry into a 'To Do' stage.",
    )
    ageing_end_date = fields.Datetime(
        string='Ageing End', compute='_compute_ageing_end_date', store=True, readonly=True,
        help="When this ticket becomes overdue: Ageing Start + the TAT "
             "Priority's Deadline Hours, business-day-aware — a full 24h "
             "counts per working day, but weekends and company holidays "
             "don't count at all (not restricted to office hours).",
    )
    is_overdue = fields.Boolean(
        string='Overdue', copy=False, default=False, readonly=True, tracking=True,
        help="Set by the periodic check once Ageing End has passed.",
    )
    ageing_duration = fields.Float(
        string='Ageing Duration', compute='_compute_ageing_duration', digits=(16, 2),
        help="Live elapsed working time since Ageing Start: a full 24h "
             "counts per working day, but weekends and company holidays "
             "don't count at all. Keeps counting with no cap — even past "
             "the normal Ageing End — so you can see how much a ticket has "
             "overrun. Freezes once the ticket closes (at its Ending Date).",
    )
    reminder_2h_sent = fields.Boolean(
        string='TAT Reminder Sent', default=False, copy=False,
        help="Technical flag so the ~15-min-before-expiry reminder email is sent only once.",
    )

    # ── SLA (shift-hours aware — separate from the 24h/day Ageing above) ──
    # "In Progress" <-> "Carry Forward" is fully automatic (see
    # _cron_check_sla): the ticket pauses in Carry Forward once today's
    # shift ends (or on a weekend/holiday) and resumes to In Progress the
    # moment the next working shift starts, without losing consumed time.
    # NOT yet built: "On Hold" pausing, and behavior for a ticket first
    # created/assigned outside shift hours.
    sla_start_date = fields.Datetime(
        string='Task SLA', readonly=True, copy=False,
        help="When the SLA timer started: (re-)entry into 'In Progress'. "
             "Unlike Ageing, SLA time only counts within shift hours (this "
             "ticket's Working Hours calendar attendance windows) — time "
             "outside shift, weekends, and holidays doesn't count at all.",
    )
    sla_duration = fields.Float(
        string='SLA Duration', compute='_compute_sla_duration', digits=(16, 2),
        help="Live elapsed shift-hours since Task SLA started. Freezes once "
             "the ticket closes (at its Ending Date).",
    )
    sla_status_id = fields.Many2one(
        'project.task.sla.status', string='SLA Status',
        compute='_compute_sla_status_id', store=True, tracking=True,
        help="Looked up from the SLA Status master (Configuration > SLA "
             "Statuses) by matching technical code — the labels/colors "
             "there are configurable, this field just tracks which one "
             "currently applies.",
    )

    @api.onchange('main_category_id')
    def _onchange_main_category_id(self):
        for task in self:
            # Sub Category no longer valid under the newly picked Main
            # Category -> clear it (its onchange below then clears Priority
            # too, since it was following the old Sub Category's default).
            if task.sub_category_id.main_category_id != task.main_category_id:
                task.sub_category_id = False

    @api.onchange('sub_category_id')
    def _onchange_sub_category_id(self):
        for task in self:
            if task.sub_category_id:
                # Keep Main Category in sync in case Sub Category was set
                # directly (e.g. via default_sub_category_id context).
                task.main_category_id = task.sub_category_id.main_category_id
                task.working_hours = task.sub_category_id.working_hours
                # NOTE: Priority (and its Deadline Hours) is no longer
                # auto-applied from the Sub Category's Default Priority —
                # only Working Hours flows through now. Priority is set
                # independently (manually, or however else you wire it in).

    @api.depends(
        'ageing_start_date', 'priority_id.deadline_type', 'priority_id.deadline_hours',
        'resource_calendar_id',
    )
    def _compute_ageing_end_date(self):
        for task in self:
            priority = task.priority_id
            if task.ageing_start_date and priority and priority.deadline_type == 'fixed':
                # deadline_hours=0 is a valid "due immediately" SLA, not "unset".
                task.ageing_end_date = task._tat_add_working_hours(
                    task.ageing_start_date, priority.deadline_hours,
                )
            else:
                task.ageing_end_date = False

    def _compute_ageing_duration(self):
        now = fields.Datetime.now()
        for task in self:
            if not task.ageing_start_date:
                task.ageing_duration = 0.0
                continue
            # Freeze at the ticket's Ending Date once it's closed; otherwise
            # keep counting live up to right now.
            end = task.date_end if (task.is_closed and task.date_end) else now
            task.ageing_duration = task._tat_working_hours_between(task.ageing_start_date, end)

    def _compute_sla_duration(self):
        now = fields.Datetime.now()
        for task in self:
            if not task.sla_start_date:
                task.sla_duration = 0.0
                continue
            end = task.date_end if (task.is_closed and task.date_end) else now
            task.sla_duration = task._sla_hours_between(task.sla_start_date, end)

    @api.depends('sla_start_date', 'sla_duration', 'working_hours', 'is_closed')
    def _compute_sla_status_id(self):
        Status = self.env['project.task.sla.status']
        # One query for all 4 possible codes, reused across every task in self.
        status_by_code = {s.code: s for s in Status.search([('code', '!=', False)])}
        for task in self:
            if not task.sla_start_date:
                code = 'not_started'
            elif task.is_closed:
                code = 'done'
            elif task.working_hours and task.sla_duration >= task.working_hours:
                code = 'breached'
            else:
                code = 'running'
            task.sla_status_id = status_by_code.get(code, Status)

    # ── Shift-hours-aware SLA math (separate from the 24h/day Ageing) ───
    def _sla_calendar(self):
        self.ensure_one()
        return self.resource_calendar_id or self._tat_company().resource_calendar_id

    def _sla_tz(self):
        calendar = self._sla_calendar()
        return timezone(calendar.tz) if calendar and calendar.tz else utc

    def _sla_windows_for_weekday(self, weekday):
        """Sorted (hour_from, hour_to) shift windows for weekday (0=Mon..
        6=Sun) from this ticket's Working Hours calendar. Multiple windows
        per day (e.g. morning/afternoon around a lunch break) are fully
        supported — the gap between them is simply not covered by any
        window, so it doesn't count as SLA time."""
        calendar = self._sla_calendar()
        if not calendar:
            return []
        lines = calendar.attendance_ids.filtered(lambda a: int(a.dayofweek) == weekday)
        return sorted((a.hour_from, a.hour_to) for a in lines)

    def _sla_hours_between(self, start_dt, end_dt):
        """Elapsed time between start_dt/end_dt (naive UTC datetimes)
        counted only within this ticket's shift/attendance windows —
        weekends, holidays, and any time outside a window (including a
        lunch-break gap) don't count at all."""
        self.ensure_one()
        if end_dt <= start_dt:
            return 0.0
        tz = self._sla_tz()
        holiday_dates = self._tat_holiday_dates(start_dt, end_dt)
        start_local = utc.localize(start_dt).astimezone(tz)
        end_local = utc.localize(end_dt).astimezone(tz)

        elapsed = timedelta()
        day_start = start_local.replace(hour=0, minute=0, second=0, microsecond=0)
        for _i in range(10000):  # safety cap against bad data / infinite loop
            if day_start.date() > end_local.date():
                break
            if day_start.date() not in holiday_dates:
                for hour_from, hour_to in self._sla_windows_for_weekday(day_start.weekday()):
                    window_start = day_start + timedelta(hours=hour_from)
                    window_end = day_start + timedelta(hours=hour_to)
                    seg_start = max(window_start, start_local)
                    seg_end = min(window_end, end_local)
                    if seg_end > seg_start:
                        elapsed += seg_end - seg_start
            day_start += timedelta(days=1)
        return elapsed.total_seconds() / 3600.0

    def _sla_is_within_shift_now(self):
        """True if right now falls inside one of today's shift windows for
        this ticket (and today isn't a holiday) — i.e. the SLA clock should
        be actively ticking / a paused ticket should resume."""
        self.ensure_one()
        now = fields.Datetime.now()
        tz = self._sla_tz()
        now_local = utc.localize(now).astimezone(tz)
        if now_local.date() in self._tat_holiday_dates(now, now):
            return False
        hour_now = now_local.hour + now_local.minute / 60.0 + now_local.second / 3600.0
        windows = self._sla_windows_for_weekday(now_local.weekday())
        return any(hour_from <= hour_now < hour_to for hour_from, hour_to in windows)

    def _sla_has_shift_ended_today(self):
        """True if, for today (this ticket's calendar/tz), every shift
        window has already ended by now, or today isn't a working day at
        all (weekend or holiday) — i.e. an actively-ticking ticket should
        pause until the next working shift."""
        self.ensure_one()
        now = fields.Datetime.now()
        tz = self._sla_tz()
        now_local = utc.localize(now).astimezone(tz)
        if now_local.date() in self._tat_holiday_dates(now, now):
            return True
        windows = self._sla_windows_for_weekday(now_local.weekday())
        if not windows:
            return True  # no shift configured today (e.g. weekend)
        hour_now = now_local.hour + now_local.minute / 60.0 + now_local.second / 3600.0
        return hour_now >= max(hour_to for _hour_from, hour_to in windows)

    def _sla_get_stage(self, names):
        """This task's project-specific stage matching one of `names`
        (normalized), if the project has one configured."""
        self.ensure_one()
        if not self.project_id:
            return self.env['project.task.type']
        for stage in self.project_id.type_ids:
            if _tat_normalize_stage_name(stage.name) in names:
                return stage
        return self.env['project.task.type']

    # ── Business-day-aware TAT math ─────────────────────────────────────
    def _tat_company(self):
        """This task's company, falling back to the current user's company
        when the task's own project isn't tied to one (shared/all-company
        projects have company_id = False)."""
        self.ensure_one()
        return self.company_id or self.env.company

    def _tat_working_weekdays(self):
        """Weekday indices (0=Monday..6=Sunday) treated as working days,
        taken from this ticket's Working Hours calendar (falls back to the
        company's calendar, then to Mon-Fri if nothing is configured)."""
        self.ensure_one()
        calendar = self.resource_calendar_id or self._tat_company().resource_calendar_id
        weekdays = {int(d) for d in calendar.attendance_ids.mapped('dayofweek')} if calendar else set()
        return weekdays or {0, 1, 2, 3, 4}

    def _tat_holiday_dates(self, date_from, date_to):
        """Holiday dates overlapping [date_from, date_to]: company-wide
        holidays (calendar_id not set) plus any holidays specific to this
        ticket's Working Hours calendar — never individual employee time
        off (resource_id is always excluded). Leave date_from/date_to are
        stored in UTC, so they're converted to the calendar's own timezone
        before extracting the calendar day(s) they cover — otherwise a
        holiday could be off by a day depending on the UTC offset."""
        self.ensure_one()
        company = self._tat_company()
        calendar = self.resource_calendar_id or company.resource_calendar_id
        tz = timezone(calendar.tz) if calendar and calendar.tz else utc
        leaves = self.env['resource.calendar.leaves'].sudo().search([
            ('company_id', '=', company.id),
            ('resource_id', '=', False),
            '|', ('calendar_id', '=', False), ('calendar_id', '=', calendar.id if calendar else False),
            ('date_from', '<=', fields.Datetime.to_string(date_to)),
            ('date_to', '>=', fields.Datetime.to_string(date_from)),
        ])
        holidays = set()
        for leave in leaves:
            day = utc.localize(leave.date_from).astimezone(tz).date()
            end = utc.localize(leave.date_to).astimezone(tz).date()
            while day <= end:
                holidays.add(day)
                day += timedelta(days=1)
        return holidays

    def _tat_add_working_hours(self, start_dt, hours):
        """Add `hours` of full 24h-per-day time to `start_dt`, skipping whole
        non-working days (weekends + company holidays) — those days don't
        count at all, but hours within a working day are not restricted to
        office hours. E.g. Friday 3:00 PM + 24h -> Monday 3:00 PM."""
        self.ensure_one()
        working_weekdays = self._tat_working_weekdays()
        # Generous lookahead window for holidays; re-searched if ever exceeded.
        window_end = start_dt + timedelta(days=max(int(hours // 24) + 30, 60))
        holiday_dates = self._tat_holiday_dates(start_dt, window_end)

        def is_working_day(dt):
            return dt.weekday() in working_weekdays and dt.date() not in holiday_dates

        remaining = timedelta(hours=hours)
        current = start_dt
        for _i in range(10000):  # safety cap against bad data / infinite loop
            if remaining <= timedelta(0):
                break
            next_midnight = fields.Datetime.from_string(
                fields.Date.to_string(current.date())
            ) + timedelta(days=1)
            if is_working_day(current):
                portion = min(remaining, next_midnight - current)
                current += portion
                remaining -= portion
            else:
                current = next_midnight
        return current

    def _tat_working_hours_between(self, start_dt, end_dt):
        """Elapsed working time between start_dt and end_dt: a full 24h
        counts per working day, but weekends and company holidays don't
        count at all — the reverse of _tat_add_working_hours (elapsed
        instead of projected-forward)."""
        self.ensure_one()
        if end_dt <= start_dt:
            return 0.0
        working_weekdays = self._tat_working_weekdays()
        holiday_dates = self._tat_holiday_dates(start_dt, end_dt)

        def is_working_day(dt):
            return dt.weekday() in working_weekdays and dt.date() not in holiday_dates

        elapsed = timedelta()
        current = start_dt
        for _i in range(10000):  # safety cap against bad data / infinite loop
            if current >= end_dt:
                break
            next_midnight = fields.Datetime.from_string(
                fields.Date.to_string(current.date())
            ) + timedelta(days=1)
            boundary = min(next_midnight, end_dt)
            if is_working_day(current):
                elapsed += boundary - current
            current = boundary
        return elapsed.total_seconds() / 3600.0

    # ── Ageing start / restart ──────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.setdefault('ageing_start_date', fields.Datetime.now())
        return super().create(vals_list)

    def write(self, vals):
        restart_ageing = self.browse()
        restart_sla = self.browse()
        if 'stage_id' in vals and vals['stage_id']:
            new_stage = self.env['project.task.type'].browse(vals['stage_id'])
            normalized = _tat_normalize_stage_name(new_stage.name)
            if normalized in TAT_AGEING_START_STAGE_NAMES:
                restart_ageing = self
            if normalized in TAT_SLA_START_STAGE_NAMES:
                # Only a genuine (re)start of the SLA clock — not the
                # automatic same-day/next-working-day resume out of Carry
                # Forward, which must keep accumulating from the original
                # sla_start_date instead of losing everything consumed so far.
                for task in self:
                    old_stage_name = _tat_normalize_stage_name(task.stage_id.name)
                    if old_stage_name not in SLA_CARRY_FORWARD_STAGE_NAMES:
                        restart_sla |= task

        result = super().write(vals)

        if restart_ageing:
            # avoid recursion: this write doesn't touch stage_id again
            super(ProjectTask, restart_ageing).write({
                'ageing_start_date': fields.Datetime.now(),
                'is_overdue': False,
                'reminder_2h_sent': False,
            })
        if restart_sla:
            super(ProjectTask, restart_sla).write({'sla_start_date': fields.Datetime.now()})

        if 'stage_id' in vals and not self.env.context.get('skip_tat_status_notify'):
            self._tat_notify_status_change()

        return result

    def _tat_get_overdue_stage(self):
        """This task's project-specific stage named "Overdue" (normalized
        match), if the project has one configured. Task stages are
        per-project records, so this is looked up per project_id."""
        self.ensure_one()
        return self._sla_get_stage(TAT_OVERDUE_STAGE_NAMES)

    # ── Notifications ────────────────────────────────────────────────────
    def _tat_notification_recipients(self):
        """Users linked/related to this ticket: assignees, followers, and
        (if set) everyone carrying the ticket's Tag. Used for the internal
        chatter note on every status change."""
        self.ensure_one()
        partners = self.message_partner_ids | self.user_ids.mapped('partner_id')
        if self.tag_id:
            partners |= self.tag_id.employee_ids.mapped('user_id.partner_id')
        return partners.filtered(lambda p: p.email)

    def _tat_tag_recipients(self):
        """Only the employees carrying this ticket's Tag — the audience
        for the Overdue and pre-expiry-reminder EMAILS specifically
        (narrower than _tat_notification_recipients, which also covers
        assignees/followers for the general chatter note)."""
        self.ensure_one()
        if not self.tag_id:
            return self.env['res.partner']
        return self.tag_id.employee_ids.mapped('user_id.partner_id').filtered(lambda p: p.email)

    def _tat_send_email(self, subject, body_html, partners):
        emails = ', '.join(sorted(set(partners.mapped('email'))))
        if not emails:
            return
        self.env['mail.mail'].sudo().create({
            'subject': subject,
            'body_html': body_html,
            'email_to': emails,
            'author_id': self.env.company.partner_id.id,
            'auto_delete': True,
        }).send(raise_exception=False)

    def _tat_notify_status_change(self):
        for task in self:
            partners = task._tat_notification_recipients()
            if not partners:
                continue
            task.message_post(
                body=self.env._(
                    "Ticket status changed to %(stage)s.", stage=task.stage_id.name,
                ),
                partner_ids=partners.ids,
                subtype_xmlid='mail.mt_note',
            )
            task._tat_send_email(
                subject=self.env._(
                    "[%(ref)s] Status changed to %(stage)s", ref=task.display_name, stage=task.stage_id.name,
                ),
                body_html=self.env._(
                    "<p>Ticket <strong>%(ref)s</strong> status changed to <strong>%(stage)s</strong>.</p>",
                    ref=task.display_name, stage=task.stage_id.name,
                ),
                partners=partners,
            )

    def _tat_notify_overdue(self):
        for task in self:
            # Chatter note stays visible to everyone linked to the ticket...
            partners = task._tat_notification_recipients()
            task.message_post(
                body=self.env._("Ticket is now OVERDUE — Ageing End has passed."),
                partner_ids=partners.ids,
                subtype_xmlid='mail.mt_note',
            )
            # ...but the actual email only goes to the ticket's Tag group.
            tag_partners = task._tat_tag_recipients()
            if tag_partners:
                task._tat_send_email(
                    subject=self.env._("[%(ref)s] OVERDUE — TAT expired", ref=task.display_name),
                    body_html=self.env._(
                        "<p>Ticket <strong>%(ref)s</strong> is now <strong style=\"color:#c62828\">OVERDUE</strong>. "
                        "Ageing End was %(deadline)s.</p>",
                        ref=task.display_name, deadline=task.ageing_end_date,
                    ),
                    partners=tag_partners,
                )

    def _tat_notify_reminder(self):
        for task in self:
            recipients = task._tat_tag_recipients()
            if not recipients:
                continue
            task._tat_send_email(
                subject=self.env._(
                    "[%(ref)s] TAT expiring soon (~%(minutes)s min left)",
                    ref=task.display_name, minutes=TAT_REMINDER_LEAD_MINUTES,
                ),
                body_html=self.env._(
                    "<p>Ticket <strong>%(ref)s</strong> Ageing End is approaching: "
                    "<strong>%(deadline)s</strong> (about %(minutes)s min from now).</p>",
                    ref=task.display_name, deadline=task.ageing_end_date, minutes=TAT_REMINDER_LEAD_MINUTES,
                ),
                partners=recipients,
            )

    def _sla_notify_breached(self):
        for task in self:
            partners = task._tat_notification_recipients()
            task.message_post(
                body=self.env._("SLA Status changed to Breached — SLA time ran out."),
                partner_ids=partners.ids,
                subtype_xmlid='mail.mt_note',
            )
            if partners:
                task._tat_send_email(
                    subject=self.env._("[%(ref)s] SLA BREACHED", ref=task.display_name),
                    body_html=self.env._(
                        "<p>Ticket <strong>%(ref)s</strong> SLA Status changed to "
                        "<strong style=\"color:#c62828\">Breached</strong> — its %(hours)s SLA "
                        "hours ran out.</p>",
                        ref=task.display_name, hours=task.working_hours,
                    ),
                    partners=partners,
                )

    # ── Periodic check (called by ir.cron) ──────────────────────────────
    @api.model
    def _cron_check_tat(self):
        now = fields.Datetime.now()
        active_tasks = self.search([
            ('ageing_end_date', '!=', False),
            ('is_closed', '=', False),
        ])

        overdue = active_tasks.filtered(lambda t: not t.is_overdue and t.ageing_end_date <= now)
        if overdue:
            # Move into the project's own "Overdue" stage where one exists
            # (grouped, one write per stage) — otherwise just flag the
            # boolean. Either way, skip the generic stage-change notice and
            # send the more specific overdue one below instead, so tickets
            # don't get two emails for the same event.
            by_stage = {}
            no_stage = self.browse()
            for task in overdue:
                stage = task._tat_get_overdue_stage()
                if stage:
                    by_stage.setdefault(stage.id, self.browse())
                    by_stage[stage.id] |= task
                else:
                    no_stage |= task
            for stage_id, tasks in by_stage.items():
                tasks.with_context(skip_tat_status_notify=True).write({
                    'stage_id': stage_id, 'is_overdue': True,
                })
            if no_stage:
                no_stage.write({'is_overdue': True})
            overdue._tat_notify_overdue()
            _logger.info("TAT check: %d ticket(s) marked overdue.", len(overdue))

        reminder_due = active_tasks.filtered(
            lambda t: not t.is_overdue and not t.reminder_2h_sent
            and t.ageing_end_date > now
            and (t.ageing_end_date - now) <= timedelta(minutes=TAT_REMINDER_LEAD_MINUTES)
        )
        if reminder_due:
            reminder_due._tat_notify_reminder()
            reminder_due.write({'reminder_2h_sent': True})
            _logger.info("TAT check: %d ticket(s) sent the pre-expiry reminder.", len(reminder_due))

    @api.model
    def _cron_check_sla(self):
        """Shift-hours-aware SLA pause/resume + breach check:
          - "In Progress" tickets whose shift has ended for today (or
            today is a weekend/holiday) move to "Carry Forward" — the SLA
            clock naturally stops accumulating outside shift windows.
          - "Carry Forward" tickets move back to "In Progress" the moment
            the next working shift starts (sla_start_date is preserved —
            see write() — so consumption picks up where it left off).
          - sla_status_id is refreshed for every active ticket so it stays
            accurate even for tickets nobody has opened.
        """
        active_tasks = self.search([
            ('sla_start_date', '!=', False),
            ('is_closed', '=', False),
        ])
        if not active_tasks:
            return

        to_pause = self.browse()
        to_resume = self.browse()
        for task in active_tasks:
            stage_name = _tat_normalize_stage_name(task.stage_id.name)
            if stage_name in TAT_SLA_START_STAGE_NAMES:
                if task._sla_has_shift_ended_today():
                    to_pause |= task
            elif stage_name in SLA_CARRY_FORWARD_STAGE_NAMES:
                if task._sla_is_within_shift_now():
                    to_resume |= task

        def _move_grouped_by_stage(tasks, get_stage):
            by_stage = {}
            no_stage = self.browse()
            for task in tasks:
                stage = get_stage(task)
                if stage:
                    by_stage.setdefault(stage.id, self.browse())
                    by_stage[stage.id] |= task
                else:
                    no_stage |= task
            for stage_id, group in by_stage.items():
                group.write({'stage_id': stage_id})
            return no_stage

        if to_pause:
            skipped = _move_grouped_by_stage(
                to_pause, lambda t: t._sla_get_stage(SLA_CARRY_FORWARD_STAGE_NAMES),
            )
            if skipped:
                _logger.info(
                    "SLA check: %d ticket(s) should pause but their project has no "
                    "'Carry Forward' stage — left as-is.", len(skipped),
                )
            _logger.info("SLA check: %d ticket(s) moved to Carry Forward.", len(to_pause) - len(skipped))

        if to_resume:
            skipped = _move_grouped_by_stage(
                to_resume, lambda t: t._sla_get_stage(TAT_SLA_START_STAGE_NAMES),
            )
            if skipped:
                _logger.info(
                    "SLA check: %d ticket(s) should resume but their project has no "
                    "'In Progress' stage — left as-is.", len(skipped),
                )
            _logger.info("SLA check: %d ticket(s) resumed to In Progress.", len(to_resume) - len(skipped))

        # Keep the stored SLA Status accurate even for tickets nobody opens,
        # and notify the moment one flips to Breached (time run out while
        # still not done/cancelled). sla_status_id depends on the always-
        # live sla_duration, so a plain read can already reflect the new
        # value (Odoo recomputes dirty stored fields on access) — the
        # "before" snapshot must come straight from the DB column instead.
        self.env.cr.execute(
            "SELECT id, sla_status_id FROM project_task WHERE id IN %s",
            (tuple(active_tasks.ids),),
        )
        before_status_id = dict(self.env.cr.fetchall())
        breached_status = self.env['project.task.sla.status'].search([('code', '=', 'breached')], limit=1)

        active_tasks._compute_sla_status_id()
        active_tasks.flush_recordset(['sla_status_id'])

        newly_breached = active_tasks.filtered(
            lambda t: breached_status and t.sla_status_id == breached_status
            and before_status_id.get(t.id) != breached_status.id
        )
        if newly_breached:
            newly_breached._sla_notify_breached()
            _logger.info("SLA check: %d ticket(s) newly flagged SLA Breached.", len(newly_breached))
