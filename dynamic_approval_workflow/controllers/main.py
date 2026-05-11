import hmac as _hmac

from odoo.exceptions import AccessError, UserError
from odoo.http import Controller, request, route


class LeaveApprovalController(Controller):

    @route(
        '/leave/action/<string:action>/<int:leave_id>/<int:approver_id>/<string:token>',
        type='http',
        auth='user',
        methods=['GET'],
        csrf=False,
    )
    def leave_email_action(self, action, leave_id, approver_id, token, **kwargs):
        """
        Handle direct Approve / Refuse actions from email hyperlinks.

        Flow:
          1.  Odoo redirects unauthenticated users to /web/login, then back here.
          2.  Token is validated (HMAC, specific to leave + action + approver).
          3.  The logged-in user must match the intended approver_id.
          4.  The matching leave action is called.
          5.  A minimal HTML confirmation page is returned.
        """
        leave = request.env['hr.leave'].sudo().browse(leave_id)

        if not leave.exists():
            return request.not_found()

        # ── Token validation ─────────────────────────────────────────────────
        expected = leave._get_email_approval_token(action, approver_id)
        if not _hmac.compare_digest(token, expected):
            return request.not_found()

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
            )

        leave_as_user = leave.with_user(request.env.user)

        try:
            if action == 'approve':
                if leave.state == 'confirm':
                    leave_as_user.action_approve()
                elif leave.state == 'validate1':
                    leave_as_user.action_second_approve()
                elif leave.state == 'validate2':
                    leave_as_user.action_approve()
                else:
                    return self._render_page(
                        title='Already Processed',
                        message='This leave request has already been processed.',
                        success=False,
                    )

            elif action == 'refuse':
                if leave.state in ('confirm', 'validate1', 'validate2'):
                    leave_as_user.action_refuse()
                else:
                    return self._render_page(
                        title='Already Processed',
                        message='This leave request has already been processed.',
                        success=False,
                    )

            else:
                return request.not_found()

        except (UserError, AccessError) as exc:
            return self._render_page(
                title='Action Failed',
                message=str(exc),
                success=False,
            )

        action_label = 'approved' if action == 'approve' else 'refused'
        emp_name = leave.employee_id.name
        return self._render_page(
            title='Done!',
            message=f'Leave request for <strong>{emp_name}</strong> has been <strong>{action_label}</strong> successfully.',
            success=True,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _render_page(self, title, message, success=True):
        """Return a minimal self-contained HTML confirmation page."""
        color = '#28a745' if success else '#dc3545'
        icon = '&#10003;' if success else '&#10005;'
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
    <a class="btn" href="/odoo/time-off">Go to Time Off</a>
  </div>
</body>
</html>"""
        return request.make_response(
            html,
            headers=[('Content-Type', 'text/html; charset=utf-8')],
        )
