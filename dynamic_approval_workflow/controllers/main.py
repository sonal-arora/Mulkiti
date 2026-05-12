import hmac as _hmac

from werkzeug.utils import redirect

from odoo.http import Controller, request, route


class LeaveApprovalController(Controller):

    @route(
        '/leave/action/<string:action>/<int:leave_id>/<int:approver_id>/<string:token>',
        type='http',
        auth='public',
        methods=['GET'],
        csrf=False,
    )
    def leave_email_action(self, action, leave_id, approver_id, token, **kwargs):
        """
        Handle Approve / Refuse links from approval emails.

        Flow:
          - Not logged in            → warning page (do NOT redirect to login)
          - Logged in, wrong user    → warning page
          - Logged in, correct user  → redirect to leave form in Odoo UI
        """
        leave = request.env['hr.leave'].sudo().browse(leave_id)

        if not leave.exists():
            return request.not_found()

        # ── Token validation ─────────────────────────────────────────────────
        expected = leave._get_email_approval_token(action, approver_id)
        if not _hmac.compare_digest(token, expected):
            return request.not_found()

        # ── Must be logged in ────────────────────────────────────────────────
        if request.env.user._is_public():
            approver_name = request.env['res.users'].sudo().browse(approver_id).name
            return self._render_page(
                title='Login Required',
                message=(
                    f'This approval link was sent to <strong>{approver_name}</strong>.<br/><br/>'
                    f'Please open Odoo and log in with that account to approve or refuse this request.'
                ),
                success=False,
                leave_id=None,
            )

        # ── Caller must be the intended approver ─────────────────────────────
        if request.env.user.id != approver_id:
            expected_name = request.env['res.users'].sudo().browse(approver_id).name
            return self._render_page(
                title='Wrong Account',
                message=(
                    f'This approval link was sent to <strong>{expected_name}</strong>.<br/>'
                    f'Please log in with the correct account and try again.'
                ),
                success=False,
                leave_id=None,
            )

        # ── Logged in as the correct approver → open the leave form ─────────
        return redirect(f'/odoo/time-off-approval/{leave_id}')

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _render_page(self, title, message, success=True, leave_id=None):
        """Return a minimal self-contained HTML warning/confirmation page."""
        color = '#28a745' if success else '#dc3545'
        icon = '&#10003;' if success else '&#9888;'
        btn_href = f'/odoo/time-off-approval/{leave_id}' if leave_id else '/odoo/time-off'
        btn_label = 'Go to Leave Request' if leave_id else 'Go to Time Off'
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{title}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: Arial, sans-serif;
      background: #f4f4f4;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
    }}
    .card {{
      background: #fff;
      border-radius: 8px;
      padding: 48px 40px;
      max-width: 480px;
      width: 90%;
      text-align: center;
      box-shadow: 0 4px 20px rgba(0,0,0,.10);
    }}
    .icon {{
      width: 64px; height: 64px;
      border-radius: 50%;
      background: {color};
      color: #fff;
      font-size: 32px;
      line-height: 64px;
      margin: 0 auto 20px;
    }}
    h2 {{ color: {color}; margin-bottom: 14px; font-size: 22px; }}
    p  {{ color: #555; font-size: 15px; line-height: 1.7; }}
    a.btn {{
      display: inline-block;
      margin-top: 28px;
      padding: 10px 30px;
      background: #875A7B;
      color: #fff;
      text-decoration: none;
      border-radius: 4px;
      font-size: 14px;
    }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">{icon}</div>
    <h2>{title}</h2>
    <p>{message}</p>
    <a class="btn" href="{btn_href}">{btn_label}</a>
  </div>
</body>
</html>"""
        return request.make_response(
            html,
            headers=[('Content-Type', 'text/html; charset=utf-8')],
        )
