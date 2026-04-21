from datetime import datetime, timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class HikvisionSyncWizard(models.TransientModel):
    _name = 'hikvision.sync.wizard'
    _description = 'Hikvision Manual Attendance Sync'

    device_ids = fields.Many2many(
        'hikvision.device',
        string='Devices',
        required=True,
        default=lambda self: self.env['hikvision.device'].search([('active', '=', True)]),
    )
    date_from = fields.Datetime(
        string='From',
        required=True,
        default=lambda self: datetime.utcnow() - timedelta(days=1),
    )
    date_to = fields.Datetime(
        string='To',
        required=True,
        default=fields.Datetime.now,
    )
    override_last_sync = fields.Boolean(
        string='Override Last Sync Time',
        default=False,
        help='If checked, sync from the date range above instead of the device last sync time.',
    )

    # Result fields (displayed after sync)
    result_html = fields.Html(string='Result', readonly=True)
    state = fields.Selection(
        [('config', 'Configure'), ('done', 'Done')],
        default='config',
    )

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_from >= rec.date_to:
                raise UserError(_('Start date must be before end date.'))

    def action_sync(self):
        self.ensure_one()
        lines = []

        for device in self.device_ids:
            # Temporarily override last_sync if requested
            if self.override_last_sync:
                original_last_sync = device.last_sync
                device.last_sync = self.date_from
            else:
                original_last_sync = None

            try:
                start_dt = self.date_from if self.override_last_sync else (
                    device.last_sync or self.date_from
                )
                end_dt = self.date_to

                events = device._fetch_events(start_dt, end_dt)
                created, skipped = device._sync_events(events)

                device.write({
                    'last_sync': self.date_to,
                    'state': 'ok',
                    'last_error': False,
                })

                lines.append(
                    f'<tr>'
                    f'<td><b>{device.name}</b></td>'
                    f'<td class="text-success">{len(events)} events fetched</td>'
                    f'<td class="text-success">{created} records created/updated</td>'
                    f'<td class="text-muted">{skipped} skipped</td>'
                    f'</tr>'
                )
            except UserError as e:
                device.write({'state': 'error', 'last_error': str(e)})
                if original_last_sync is not None:
                    device.last_sync = original_last_sync
                lines.append(
                    f'<tr>'
                    f'<td><b>{device.name}</b></td>'
                    f'<td colspan="3" class="text-danger">Error: {e}</td>'
                    f'</tr>'
                )

        table = (
            '<table class="table table-sm">'
            '<thead><tr><th>Device</th><th>Events</th><th>Created</th><th>Skipped</th></tr></thead>'
            '<tbody>' + ''.join(lines) + '</tbody>'
            '</table>'
        )
        self.write({'result_html': table, 'state': 'done'})

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_close(self):
        return {'type': 'ir.actions.act_window_close'}
