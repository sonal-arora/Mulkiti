import json
import logging
from datetime import datetime, timedelta

import requests
from requests.auth import HTTPDigestAuth

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# Hikvision ISAPI AcsEvent minor codes for attendance
# These are the most common values; actual codes may vary by device firmware
CHECKIN_MINOR_CODES = {75, 196}   # Card reader: work start / check-in
CHECKOUT_MINOR_CODES = {76, 197}  # Card reader: work end / check-out

# attendanceType values returned in event data (newer firmware)
ATTENDANCE_TYPE_CHECKIN = {'checkIn', 'normal', 'breakIn', 'overtimeIn'}
ATTENDANCE_TYPE_CHECKOUT = {'checkOut', 'breakOut', 'overtimeOut'}


class HikvisionDevice(models.Model):
    _name = 'hikvision.device'
    _description = 'Hikvision Attendance Device'
    _order = 'name'

    name = fields.Char(string='Device Name', required=True)
    host = fields.Char(
        string='IP Address / Hostname',
        required=True,
        help='IP address or hostname of the Hikvision device or iVMS-4200 server.',
    )
    port = fields.Integer(string='Port', default=80)
    use_https = fields.Boolean(string='Use HTTPS', default=False)
    username = fields.Char(string='Username', default='admin')
    password = fields.Char(string='Password')
    active = fields.Boolean(default=True)
    last_sync = fields.Datetime(string='Last Sync', readonly=True)
    sync_days_back = fields.Integer(
        string='Days Back on First Sync',
        default=1,
        help='How many days back to fetch attendance records when no previous sync time exists.',
    )
    state = fields.Selection(
        selection=[('draft', 'Not Tested'), ('ok', 'Connected'), ('error', 'Error')],
        default='draft',
        string='Connection Status',
        readonly=True,
    )
    last_error = fields.Char(string='Last Error', readonly=True)
    attendance_count = fields.Integer(
        string='Records Synced',
        compute='_compute_attendance_count',
    )

    def _compute_attendance_count(self):
        for device in self:
            device.attendance_count = self.env['hr.attendance'].search_count(
                [('hikvision_device_id', '=', device.id)]
            )

    # ------------------------------------------------------------------
    # ISAPI helpers
    # ------------------------------------------------------------------

    def _base_url(self):
        self.ensure_one()
        scheme = 'https' if self.use_https else 'http'
        return f'{scheme}://{self.host}:{self.port}'

    def _get_session(self):
        """Return a requests.Session pre-configured with Digest auth."""
        session = requests.Session()
        session.auth = HTTPDigestAuth(self.username or '', self.password or '')
        session.verify = False  # skip SSL verify for self-signed certs
        return session

    def _isapi_post(self, path, payload, timeout=30):
        """POST to an ISAPI endpoint; return parsed JSON response."""
        url = self._base_url() + path
        session = self._get_session()
        try:
            resp = session.post(url, json=payload, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.ConnectionError as e:
            raise UserError(_('Cannot connect to device %s: %s') % (self.name, e))
        except requests.exceptions.Timeout:
            raise UserError(_('Connection to device %s timed out.') % self.name)
        except requests.exceptions.HTTPError as e:
            raise UserError(_('HTTP error from device %s: %s') % (self.name, e))
        except json.JSONDecodeError:
            raise UserError(_('Device %s returned non-JSON response.') % self.name)

    def _isapi_get(self, path, timeout=10):
        """GET an ISAPI endpoint; return parsed JSON response."""
        url = self._base_url() + path
        session = self._get_session()
        try:
            resp = session.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.ConnectionError as e:
            raise UserError(_('Cannot connect to device %s: %s') % (self.name, e))
        except requests.exceptions.Timeout:
            raise UserError(_('Connection to device %s timed out.') % self.name)
        except requests.exceptions.HTTPError as e:
            raise UserError(_('HTTP error from device %s: %s') % (self.name, e))
        except json.JSONDecodeError:
            raise UserError(_('Device %s returned non-JSON response.') % self.name)

    # ------------------------------------------------------------------
    # Connection test
    # ------------------------------------------------------------------

    def action_test_connection(self):
        self.ensure_one()
        try:
            data = self._isapi_get('/ISAPI/System/deviceInfo')
            model_name = (
                data.get('DeviceInfo', {}).get('model')
                or data.get('model')
                or 'Unknown model'
            )
            self.write({'state': 'ok', 'last_error': False})
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection Successful'),
                    'message': _('Connected to device: %s') % model_name,
                    'type': 'success',
                    'sticky': False,
                },
            }
        except UserError as e:
            self.write({'state': 'error', 'last_error': str(e)})
            raise

    # ------------------------------------------------------------------
    # Fetch events from ISAPI
    # ------------------------------------------------------------------

    def _fetch_events(self, start_dt, end_dt):
        """
        Query AcsEvent endpoint for access/attendance events between
        start_dt and end_dt (naive UTC datetimes).

        Returns a list of event dicts.
        """
        self.ensure_one()
        all_events = []
        search_position = 0
        max_results = 100  # fetch in pages of 100

        start_str = start_dt.strftime('%Y-%m-%dT%H:%M:%S+00:00')
        end_str = end_dt.strftime('%Y-%m-%dT%H:%M:%S+00:00')

        while True:
            payload = {
                'AcsEventCond': {
                    'searchID': '1',
                    'searchResultPosition': search_position,
                    'maxResults': max_results,
                    'startTime': start_str,
                    'endTime': end_str,
                    'major': 5,  # Access Control
                }
            }
            data = self._isapi_post('/ISAPI/AccessControl/AcsEvent?format=json', payload)
            acs_event = data.get('AcsEvent', {})
            info_list = acs_event.get('InfoList', [])
            all_events.extend(info_list)

            total = acs_event.get('totalMatches', len(info_list))
            search_position += len(info_list)

            if search_position >= total or not info_list:
                break

        _logger.info(
            'Hikvision device %s: fetched %d events from %s to %s',
            self.name, len(all_events), start_str, end_str,
        )
        return all_events

    # ------------------------------------------------------------------
    # Determine event direction (check-in vs check-out)
    # ------------------------------------------------------------------

    @staticmethod
    def _is_checkin_event(event):
        """
        Return True if the event represents a check-in, False for check-out,
        None if the event is irrelevant.

        Priority:
          1. attendanceType field (newer firmware)
          2. minor event code
        """
        att_type = event.get('attendanceType', '')
        if att_type in ATTENDANCE_TYPE_CHECKIN:
            return True
        if att_type in ATTENDANCE_TYPE_CHECKOUT:
            return False

        minor = event.get('minor', 0)
        if minor in CHECKIN_MINOR_CODES:
            return True
        if minor in CHECKOUT_MINOR_CODES:
            return False

        # For devices that don't distinguish, treat every event as a toggle
        # (same logic Odoo kiosk uses — check current state)
        return None  # caller will toggle based on current attendance state

    # ------------------------------------------------------------------
    # Core sync
    # ------------------------------------------------------------------

    def _parse_event_time(self, time_str):
        """
        Parse ISAPI time string to naive UTC datetime.
        Format examples: '2026-03-16T08:50:26+04:00', '2026-03-16T08:50:26Z'
        """
        if not time_str:
            return None
        # normalise timezone offset
        if time_str.endswith('Z'):
            time_str = time_str[:-1] + '+00:00'
        try:
            dt_aware = datetime.fromisoformat(time_str)
            return dt_aware.astimezone(tz=None).replace(tzinfo=None)  # naive UTC
        except ValueError:
            _logger.warning('Cannot parse event time: %s', time_str)
            return None

    def _sync_events(self, events):
        """
        Process a list of ISAPI events and create/update hr.attendance records.
        Returns (created, skipped) counts.
        """
        Attendance = self.env['hr.attendance']
        Employee = self.env['hr.employee']

        created = skipped = 0

        # Build employee lookup: badge number → employee
        employee_cache = {}

        for event in events:
            badge_no = (
                event.get('employeeNoString')
                or str(event.get('employeeNo', ''))
            ).strip()
            if not badge_no:
                skipped += 1
                continue

            event_time = self._parse_event_time(event.get('time'))
            if not event_time:
                skipped += 1
                continue

            # Lookup employee (cached)
            if badge_no not in employee_cache:
                employee_cache[badge_no] = Employee.search(
                    [('barcode', '=', badge_no)], limit=1
                )
            employee = employee_cache[badge_no]

            if not employee:
                _logger.debug(
                    'No employee with barcode %s — skipping event', badge_no
                )
                skipped += 1
                continue

            is_checkin = self._is_checkin_event(event)

            if is_checkin is True:
                # --- Check-in: create a new attendance record ---
                # Prevent duplicates within a 1-minute window
                duplicate = Attendance.search([
                    ('employee_id', '=', employee.id),
                    ('check_in', '>=', event_time - timedelta(minutes=1)),
                    ('check_in', '<=', event_time + timedelta(minutes=1)),
                ], limit=1)
                if duplicate:
                    skipped += 1
                    continue
                Attendance.create({
                    'employee_id': employee.id,
                    'check_in': event_time,
                    'in_mode': 'manual',
                    'hikvision_device_id': self.id,
                })
                created += 1

            elif is_checkin is False:
                # --- Check-out: close the latest open attendance ---
                open_att = Attendance.search([
                    ('employee_id', '=', employee.id),
                    ('check_out', '=', False),
                    ('check_in', '<=', event_time),
                ], order='check_in desc', limit=1)
                if open_att:
                    open_att.write({'check_out': event_time})
                    created += 1
                else:
                    # No open record; create a standalone check-out record
                    # with check_in set 1 second before (Odoo requires check_in)
                    Attendance.create({
                        'employee_id': employee.id,
                        'check_in': event_time - timedelta(seconds=1),
                        'check_out': event_time,
                        'in_mode': 'manual',
                        'hikvision_device_id': self.id,
                    })
                    created += 1

            else:
                # --- Toggle mode: mirror Odoo kiosk behaviour ---
                last_att = Attendance.search([
                    ('employee_id', '=', employee.id),
                ], order='check_in desc', limit=1)

                if last_att and not last_att.check_out:
                    # Currently checked in → check out
                    last_att.write({'check_out': event_time})
                else:
                    # Currently checked out → check in
                    Attendance.create({
                        'employee_id': employee.id,
                        'check_in': event_time,
                        'in_mode': 'manual',
                        'hikvision_device_id': self.id,
                    })
                created += 1

        return created, skipped

    def sync_attendance(self):
        """
        Pull attendance events from the device and create Odoo attendance records.
        Called by the scheduled cron and by the manual sync wizard.
        Returns a summary dict.
        """
        results = {}
        for device in self:
            start_dt = device.last_sync or (
                datetime.utcnow() - timedelta(days=device.sync_days_back)
            )
            end_dt = datetime.utcnow()

            try:
                events = device._fetch_events(start_dt, end_dt)
                created, skipped = device._sync_events(events)
                device.write({
                    'last_sync': fields.Datetime.now(),
                    'state': 'ok',
                    'last_error': False,
                })
                results[device.id] = {
                    'total': len(events),
                    'created': created,
                    'skipped': skipped,
                }
                _logger.info(
                    'Hikvision sync [%s]: %d events → %d created, %d skipped',
                    device.name, len(events), created, skipped,
                )
            except UserError as e:
                device.write({'state': 'error', 'last_error': str(e)})
                _logger.error('Hikvision sync error [%s]: %s', device.name, e)
                results[device.id] = {'error': str(e)}

        return results

    def action_view_attendances(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Attendance Records — %s') % self.name,
            'res_model': 'hr.attendance',
            'view_mode': 'list,form',
            'domain': [('hikvision_device_id', '=', self.id)],
            'context': {'create': False},
        }


class HrAttendance(models.Model):
    """Extend hr.attendance to track which Hikvision device created the record."""
    _inherit = 'hr.attendance'

    hikvision_device_id = fields.Many2one(
        'hikvision.device',
        string='Hikvision Device',
        ondelete='set null',
        readonly=True,
        index=True,
    )
