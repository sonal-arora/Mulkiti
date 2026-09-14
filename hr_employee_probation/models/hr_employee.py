# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from datetime import timedelta


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # ─── Probation Workflow Fields ─────────────────────────────────────
    probation_end_date = fields.Date(
        string='Probation End Date',
        tracking=True,
        help="Date on which the employee's probation period is due to end. "
             "Drives the Employment Status and the daily HR reminders.",
    )
    employment_status = fields.Selection([
        ('probation', 'Probation'),
        ('confirmed', 'Confirmed'),
    ], string='Employment Status', default='probation', tracking=True, copy=False)
    confirmation_date = fields.Date(
        string='Confirmation Date',
        readonly=True,
        copy=False,
        help="Date on which the employee was confirmed as Regular.",
    )
    probation_completed = fields.Boolean(
        string='Probation Completed',
        compute='_compute_probation_completed',
        help="True once the probation end date has passed and the employee "
             "has not yet been confirmed as Regular.",
    )

    @api.depends('probation_end_date', 'employment_status')
    def _compute_probation_completed(self):
        today = fields.Date.today()
        for employee in self:
            employee.probation_completed = bool(
                employee.employment_status == 'probation'
                and employee.probation_end_date
                and employee.probation_end_date <= today
            )

    # ─── Workflow Action ────────────────────────────────────────────────
    def action_confirm_employee(self):
        """Confirm the employee as Regular, ending their probation period."""
        today = fields.Date.context_today(self)
        for employee in self:
            if employee.employment_status != 'probation':
                # Already confirmed, or past the probation stage entirely
                # (e.g. Under Notice Period / End of Service) — nothing to do.
                continue
            employee.write({
                'employment_status': 'confirmed',
                'confirmation_date': today,
            })
            employee.message_post(
                body=_("Employee confirmed as Regular (probation completed) on %s.") % today
            )

    # ─── Daily Reminder Cron ────────────────────────────────────────────
    def cron_probation_reminder(self):
        """Notify HR of employees whose probation is ending soon or overdue."""
        today = fields.Date.today()
        hr_group = self.env.ref('hr.group_hr_user')
        hr_users = self.env['res.users'].sudo().search([
            ('group_ids', 'in', [hr_group.id]),
            ('active', '=', True),
        ])
        email_list = hr_users.filtered(lambda u: u.partner_id.email).mapped('partner_id.email')

        base_domain = [
            ('employment_status', '=', 'probation'),
            ('probation_end_date', '!=', False),
            ('active', '=', True),
        ]

        # 14 / 7 / 1 days before the end date, and 0 = the day it becomes due.
        for days_before in (14, 7, 1, 0):
            target_date = today + timedelta(days=days_before)
            employees = self.search(base_domain + [('probation_end_date', '=', target_date)])

            for employee in employees:
                if days_before:
                    message = _(
                        "Reminder: %(name)s's probation period ends on %(date)s "
                        "(%(days)s day(s) remaining)."
                    ) % {
                        'name': employee.name,
                        'date': employee.probation_end_date,
                        'days': days_before,
                    }
                    subject = (
                        f'Probation Ending Soon - {employee.name} '
                        f'({days_before} day(s) remaining)'
                    )
                else:
                    message = _(
                        "%(name)s's probation period ends today. Please confirm "
                        "as Regular or update the probation end date."
                    ) % {'name': employee.name}
                    subject = f'Probation Ending Today - {employee.name}'

                employee.message_post(body=message)

                if email_list:
                    self.env['mail.mail'].create({
                        'subject': subject,
                        'body_html': f"<p>{message}</p>",
                        'email_to': ','.join(email_list),
                    }).send()
