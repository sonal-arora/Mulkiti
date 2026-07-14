import logging

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PmsAppraisal(models.Model):
    _name = "pms.appraisal"
    _description = "PMS Appraisal"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "financial_year_id desc, employee_id"

    name = fields.Char(
        string="Reference",
        readonly=True,
        default="New",
        copy=False,
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="Employee",
        required=True,
        tracking=True,
    )
    department_id = fields.Many2one(
        "hr.department",
        related="employee_id.department_id",
        string="Department",
        store=True,
    )
    job_id = fields.Many2one(
        "hr.job",
        related="employee_id.job_id",
        string="Job Position",
        store=True,
    )
    employee_user_id = fields.Many2one(
        "res.users",
        related="employee_id.user_id",
        string="Employee User",
        store=True,
    )
    # ── Approvers ───────────────────────────────────────────────────────────
    manager_id = fields.Many2one(
        "hr.employee",
        string="1st Approver (Manager)",
        compute="_compute_approvers",
        store=True,
    )
    manager_user_id = fields.Many2one(
        "res.users",
        related="manager_id.user_id",
        string="Manager User",
        store=True,
    )
    second_manager_id = fields.Many2one(
        "hr.employee",
        string="2nd Approver",
        compute="_compute_approvers",
        store=True,
    )
    second_manager_user_id = fields.Many2one(
        "res.users",
        related="second_manager_id.user_id",
        string="2nd Approver User",
        store=True,
    )
    # ── KRA / Initialize ────────────────────────────────────────────────────
    initialize_id = fields.Many2one(
        "pms.initialize",
        string="PMS Initialization",
        required=True,
        ondelete="restrict",
    )
    financial_year_id = fields.Many2one(
        "pms.financial.year",
        string="Financial Year",
        required=True,
        tracking=True,
    )
    financial_year_name = fields.Char(
        related="financial_year_id.name",
        store=True,
        string="Financial Year",
    )
    kra_id = fields.Many2one(
        "pms.kra",
        string="KRA",
        required=True,
    )
    # ── State ───────────────────────────────────────────────────────────────
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("manager_review", "Manager Review"),
            ("second_review", "2nd Review"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        string="Status",
        tracking=True,
    )
    cancel_reason = fields.Text(string="Cancellation Reason", readonly=True)
    # ── Lines ───────────────────────────────────────────────────────────────
    line_ids = fields.One2many(
        "pms.appraisal.line",
        "appraisal_id",
        string="KRA Lines",
    )
    # ── Overall comments ─────────────────────────────────────────────────────
    overall_self_comments = fields.Text(string="Overall Self Comments")
    overall_manager_comments = fields.Text(string="Overall Manager Comments")
    overall_second_comments = fields.Text(string="Overall 2nd Approver Comments")
    # ── Dates ───────────────────────────────────────────────────────────────
    submit_date = fields.Date(string="Submitted On", readonly=True)
    manager_review_date = fields.Date(string="Manager Reviewed On", readonly=True)
    second_review_date = fields.Date(string="2nd Reviewed On", readonly=True)
    approval_date = fields.Date(string="Approved On", readonly=True)
    # ── Visibility flags ────────────────────────────────────────────────────
    can_submit = fields.Boolean(compute="_compute_visibility")
    can_manager_approve = fields.Boolean(compute="_compute_visibility")
    can_second_approve = fields.Boolean(compute="_compute_visibility")
    can_reject = fields.Boolean(compute="_compute_visibility")
    is_own_record = fields.Boolean(compute="_compute_visibility")

    # ── Compute approvers from employee ─────────────────────────────────────

    @api.depends(
        "employee_id",
        "employee_id.parent_id",
        "employee_id.parent_id.user_id",
        "employee_id.x_leave_approver_2_id",
        "employee_id.leave_manager_id",
    )
    def _compute_approvers(self):
        for rec in self:
            emp = rec.employee_id.sudo()
            rec.manager_id = emp.parent_id or False
            # Use custom 2nd approver if set (from dynamic_approval_workflow)
            second = emp.x_leave_approver_2_id.employee_id if hasattr(emp, 'x_leave_approver_2_id') and emp.x_leave_approver_2_id else False
            if not second:
                second = emp.leave_manager_id.employee_ids[:1] if emp.leave_manager_id else False
            rec.second_manager_id = second or False

    @api.depends_context("uid")
    @api.depends("state", "employee_user_id", "manager_user_id", "second_manager_user_id")
    def _compute_visibility(self):
        user = self.env.user
        is_head = user.has_group("pms_mulkiti.group_pms_head")
        is_manager = user.has_group("pms_mulkiti.group_pms_manager")
        for rec in self:
            is_own = rec.employee_user_id == user
            is_rec_manager = rec.manager_user_id == user
            is_rec_second = rec.second_manager_user_id == user

            rec.is_own_record = is_own
            rec.can_submit = rec.state == "draft" and is_own
            rec.can_manager_approve = (
                rec.state == "submitted"
                and (is_rec_manager or is_manager or is_head)
            )
            rec.can_second_approve = (
                rec.state == "manager_review"
                and (is_rec_second or is_head)
            )
            rec.can_reject = rec.state in ("submitted", "manager_review", "second_review") and (
                is_rec_manager or is_rec_second or is_head
            )

    # ── Create ───────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = (
                    self.env["ir.sequence"].next_by_code("pms.appraisal") or "New"
                )
        return super().create(vals_list)

    def _populate_kra_lines(self):
        """Auto-create appraisal lines from KRA lines."""
        self.ensure_one()
        lines = []
        for kra_line in self.kra_id.line_ids:
            lines.append({
                "appraisal_id": self.id,
                "kra_line_id": kra_line.id,
                "job_responsibility": kra_line.job_responsibility,
                "deliverable": kra_line.deliverable,
            })
        if lines:
            self.env["pms.appraisal.line"].create(lines)

    # ── Workflow actions ──────────────────────────────────────────────────────

    def action_submit(self):
        """Employee submits self-assessment."""
        self.ensure_one()
        if self.state != "draft":
            raise UserError(_("Only draft PMS can be submitted."))
        if not self.line_ids:
            raise UserError(_("No KRA lines found. Please contact PMS Head."))
        # Check all self ratings filled
        unfilled = self.line_ids.filtered(lambda l: not l.self_rating_id)
        if unfilled:
            raise UserError(_("Please fill self-rating for all KRA lines before submitting."))

        self.write({
            "state": "submitted",
            "submit_date": fields.Date.today(),
        })
        # Notify 1st level manager
        if self.manager_user_id:
            self._send_pms_email(
                to_user=self.manager_user_id,
                subject=f"[PMS] Self-Assessment Submitted by {self.employee_id.name}",
                body=self._email_body("submitted"),
            )
        self.message_post(
            body=Markup(
                "<b>Self-assessment submitted</b> by <b>%(emp)s</b>. "
                "Awaiting 1st level manager review."
            ) % {"emp": self.employee_id.name},
            subtype_xmlid="mail.mt_comment",
        )

    def action_manager_approve(self):
        """1st level manager approves → goes to 2nd review."""
        self.ensure_one()
        if self.state != "submitted":
            raise UserError(_("PMS must be in 'Submitted' state for manager approval."))
        unfilled = self.line_ids.filtered(lambda l: not l.manager_rating_id)
        if unfilled:
            raise UserError(_("Please fill manager-rating for all KRA lines."))

        self.write({
            "state": "manager_review",
            "manager_review_date": fields.Date.today(),
        })
        # Notify 2nd approver
        to_user = self.second_manager_user_id or self._get_pms_head_user()
        if to_user:
            self._send_pms_email(
                to_user=to_user,
                subject=f"[PMS] Manager Review Done — {self.employee_id.name}",
                body=self._email_body("manager_review"),
            )
        self.message_post(
            body=Markup(
                "<b>Manager review completed</b> by <b>%(mgr)s</b>. "
                "Awaiting 2nd level approval."
            ) % {"mgr": self.env.user.name},
            subtype_xmlid="mail.mt_comment",
        )

    def action_second_approve(self):
        """2nd level approves → PMS approved."""
        self.ensure_one()
        if self.state != "manager_review":
            raise UserError(_("PMS must be in 'Manager Review' state for 2nd approval."))

        self.write({
            "state": "approved",
            "second_review_date": fields.Date.today(),
            "approval_date": fields.Date.today(),
        })
        # Notify employee
        if self.employee_user_id:
            self._send_pms_email(
                to_user=self.employee_user_id,
                subject=f"[PMS] Your Appraisal Approved — {self.financial_year_name}",
                body=self._email_body("approved"),
            )
        self.message_post(
            body=Markup(
                "<b>PMS Fully Approved</b> by <b>%(usr)s</b>."
            ) % {
                "usr": self.env.user.name,
            },
            subtype_xmlid="mail.mt_comment",
        )

    def action_reject(self):
        """Open wizard to enter cancel reason, then reject."""
        self.ensure_one()
        if self.state not in ("submitted", "manager_review", "second_review"):
            raise UserError(_("Cannot reject in current state."))
        return {
            "name": _("Reject PMS"),
            "type": "ir.actions.act_window",
            "res_model": "pms.reject.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_appraisal_id": self.id},
        }

    def _do_reject(self, cancel_reason):
        """Called from wizard to actually reject with reason."""
        self.ensure_one()
        prev_state = dict(self._fields["state"].selection).get(self.state)
        self.write({"state": "rejected", "cancel_reason": cancel_reason})
        if self.employee_user_id:
            self._send_pms_email(
                to_user=self.employee_user_id,
                subject=f"[PMS] Your Appraisal was Rejected",
                body=self._email_body("rejected"),
            )
        self.message_post(
            body=Markup(
                "<b>PMS Rejected</b> by <b>%(usr)s</b> from state <b>%(state)s</b>.<br/>"
                "<b>Reason:</b> %(reason)s"
            ) % {"usr": self.env.user.name, "state": prev_state, "reason": cancel_reason or "-"},
            subtype_xmlid="mail.mt_comment",
        )

    def action_reset_draft(self):
        """Head only — reset without reason (from rejected/approved)."""
        self.ensure_one()
        self.write({"state": "draft", "cancel_reason": False})

    def action_reset_to_draft_with_reason(self):
        """Manager button — reset submitted PMS back to draft with reason."""
        self.ensure_one()
        if self.state != "submitted":
            raise UserError(_("Only Submitted PMS can be sent back to draft."))
        return {
            "name": _("Send Back to Draft"),
            "type": "ir.actions.act_window",
            "res_model": "pms.reject.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_appraisal_id": self.id,
                "default_is_reset_draft": True,
            },
        }

    def _do_reset_draft(self, reason):
        """Reset submitted PMS to draft with reason logged in chatter."""
        self.ensure_one()
        self.write({"state": "draft"})
        self.message_post(
            body=Markup(
                "<b>Sent back to Draft</b> by <b>%(usr)s</b>.<br/>"
                "<b>Reason:</b> %(reason)s"
            ) % {"usr": self.env.user.name, "reason": reason},
            subtype_xmlid="mail.mt_comment",
        )
        # Notify employee
        if self.employee_user_id:
            self._send_pms_email(
                to_user=self.employee_user_id,
                subject=f"[PMS] Your Self-Assessment Sent Back for Revision",
                body=self._email_body_reset_draft(reason),
            )

    def _email_body_reset_draft(self, reason):
        emp = self.employee_id.name
        fy = self.financial_year_name or self.financial_year_id.name or ""
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url", "")
        link = f"{base_url}/odoo/pms/{self.id}"
        return f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
  <div style="background:#875A7B;padding:20px 28px;border-radius:6px 6px 0 0;">
    <h2 style="color:#fff;margin:0;font-size:16px;">Performance Management System</h2>
  </div>
  <div style="border:1px solid #ddd;border-top:none;border-radius:0 0 6px 6px;padding:24px;">
    <p>Your PMS self-assessment for <b>{fy}</b> has been sent back to <b>Draft</b> by your manager for revision.</p>
    <p><b>Reason:</b> {reason}</p>
    <div style="text-align:center;margin-top:20px;">
      <a href="{link}" style="background:#875A7B;color:#fff;padding:10px 28px;
         text-decoration:none;border-radius:4px;font-size:14px;">View &amp; Revise PMS</a>
    </div>
  </div>
  <p style="text-align:center;font-size:11px;color:#aaa;margin-top:10px;">
    {self.env.company.name}
  </p>
</div>"""

    def action_cancel(self):
        """Cancel a draft PMS — opens wizard to enter reason."""
        self.ensure_one()
        if self.state != "draft":
            raise UserError(_("Only Draft PMS can be cancelled."))
        return {
            "name": _("Cancel PMS"),
            "type": "ir.actions.act_window",
            "res_model": "pms.reject.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_appraisal_id": self.id,
                "default_is_cancel": True,
            },
        }

    def _do_cancel(self, cancel_reason):
        """Called from wizard to cancel a draft PMS."""
        self.ensure_one()
        self.write({"state": "cancelled", "cancel_reason": cancel_reason})
        self.message_post(
            body=Markup(
                "<b>PMS Cancelled</b> by <b>%(usr)s</b>.<br/><b>Reason:</b> %(reason)s"
            ) % {"usr": self.env.user.name, "reason": cancel_reason or "-"},
            subtype_xmlid="mail.mt_comment",
        )

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _get_pms_head_user(self):
        group = self.env.ref("pms_mulkiti.group_pms_head", raise_if_not_found=False)
        if group and group.users:
            return group.users[:1]
        return False

    def _email_body(self, status):
        emp = self.employee_id.name
        fy = self.financial_year_name or self.financial_year_id.name or ""
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url", "")
        link = f"{base_url}/odoo/pms/{self.id}"

        status_map = {
            "initialized": f"Your PMS appraisal for <b>{fy}</b> has been <b>initialized</b>. Please fill in your self-assessment once you're ready.",
            "submitted": f"<b>{emp}</b> has submitted their self-assessment for <b>{fy}</b>. Please review and provide your ratings.",
            "manager_review": f"Manager review is complete for <b>{emp}</b> ({fy}). Please provide 2nd level approval.",
            "approved": f"Your PMS appraisal for <b>{fy}</b> has been <b style='color:green'>Fully Approved</b>.",
            "rejected": f"Your PMS appraisal for <b>{fy}</b> has been <b style='color:red'>Rejected</b>. Please contact HR.",
        }
        msg = status_map.get(status, "")
        return f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
  <div style="background:#875A7B;padding:20px 28px;border-radius:6px 6px 0 0;">
    <h2 style="color:#fff;margin:0;font-size:16px;">Performance Management System</h2>
  </div>
  <div style="border:1px solid #ddd;border-top:none;border-radius:0 0 6px 6px;padding:24px;">
    <p>{msg}</p>
    <div style="text-align:center;margin-top:20px;">
      <a href="{link}" style="background:#875A7B;color:#fff;padding:10px 28px;
         text-decoration:none;border-radius:4px;font-size:14px;">View PMS</a>
    </div>
  </div>
  <p style="text-align:center;font-size:11px;color:#aaa;margin-top:10px;">
    {self.env.company.name}
  </p>
</div>"""

    def _send_pms_email(self, to_user, subject, body):
        if not to_user or not to_user.email:
            return
        company = self.env.company
        # Use company's outgoing email (catchall or email)
        company_email = (
            self.env["ir.config_parameter"].sudo().get_param("mail.catchall.email")
            or company.email
        )
        company_name = company.name
        email_from = (
            f"{company_name} <{company_email}>" if company_email else company_name
        )
        try:
            self.env["mail.mail"].sudo().create({
                "subject": subject,
                "body_html": body,
                "email_to": to_user.email_formatted,
                "email_from": email_from,
                "author_id": company.partner_id.id,
                "auto_delete": True,
            }).send()
        except Exception as e:
            _logger.error("PMS email failed: %s", e)


class PmsAppraisalLine(models.Model):
    _name = "pms.appraisal.line"
    _description = "PMS Appraisal Line"
    _order = "sequence, id"

    appraisal_id = fields.Many2one(
        "pms.appraisal", required=True, ondelete="cascade"
    )
    kra_line_id = fields.Many2one("pms.kra.line", string="KRA Line")
    sequence = fields.Integer(related="kra_line_id.sequence", store=True)

    # ── Readonly fields from KRA ──────────────────────────────────────────
    job_responsibility = fields.Char(
        string="Job Responsibility / KRA",
        readonly=True,
    )
    deliverable = fields.Text(string="Key Deliverable / Target", readonly=True)

    # ── Employee self-assessment ──────────────────────────────────────────
    self_rating_id = fields.Many2one("pms.rating", string="Self Rating")
    self_rating_description = fields.Text(
        related="self_rating_id.description", string="Self Rating Description", readonly=True
    )
    self_comments = fields.Text(string="Self Comments")

    # ── Manager rating ────────────────────────────────────────────────────
    manager_rating_id = fields.Many2one("pms.rating", string="Manager Rating")
    manager_rating_description = fields.Text(
        related="manager_rating_id.description", string="Manager Rating Description", readonly=True
    )
    manager_comments = fields.Text(string="Manager Comments")

    # ── 2nd Approver rating ───────────────────────────────────────────────
    second_rating_id = fields.Many2one("pms.rating", string="2nd Approver Rating")
    second_rating_description = fields.Text(
        related="second_rating_id.description", string="2nd Approver Rating Description", readonly=True
    )
    second_comments = fields.Text(string="2nd Approver Comments")
