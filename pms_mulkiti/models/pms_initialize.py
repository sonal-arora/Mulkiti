from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PmsInitialize(models.Model):
    _name = "pms.initialize"
    _description = "PMS Initialization"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "financial_year_id desc, id desc"

    name = fields.Char(
        string="Reference",
        readonly=True,
        default="New",
        copy=False,
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
    )
    employee_ids = fields.Many2many(
        "hr.employee",
        "pms_initialize_employee_rel",
        "initialize_id",
        "employee_id",
        string="Employees",
        domain="[('active','=',True)]",
    )
    company_id = fields.Many2one(
        "res.company",
        default=lambda self: self.env.company,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("initialized", "Initialized"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        tracking=True,
    )
    cancel_reason = fields.Text(string="Cancellation Reason", readonly=True)
    appraisal_ids = fields.One2many(
        "pms.appraisal",
        "initialize_id",
        string="PMS Records",
    )
    appraisal_count = fields.Integer(
        compute="_compute_appraisal_count",
        string="PMS Count",
    )
    preview_line_ids = fields.One2many(
        "pms.initialize.preview",
        "initialize_id",
        string="Preview",
        compute="_compute_preview",
    )

    @api.depends("appraisal_ids")
    def _compute_appraisal_count(self):
        for rec in self:
            rec.appraisal_count = len(rec.appraisal_ids)

    @api.depends("employee_ids", "financial_year_id")
    def _compute_preview(self):
        for rec in self:
            self.env["pms.initialize.preview"].search(
                [("initialize_id", "=", rec.id)]
            ).unlink()
            if not rec.financial_year_id or not rec.employee_ids:
                rec.preview_line_ids = []
                continue
            lines = []
            for emp in rec.employee_ids:
                kra = self.env["pms.kra"].search([
                    ("job_id", "=", emp.job_id.id),
                    ("financial_year_id", "=", rec.financial_year_id.id),
                    ("company_id", "=", rec.company_id.id),
                ], limit=1) if emp.job_id else False

                attitude = self.env["pms.attitude"].search([
                    ("financial_year_id", "=", rec.financial_year_id.id),
                ], limit=1)

                lines.append(self.env["pms.initialize.preview"].create({
                    "initialize_id": rec.id,
                    "employee_id": emp.id,
                    "job_id": emp.job_id.id if emp.job_id else False,
                    "kra_id": kra.id if kra else False,
                    "kra_found": bool(kra),
                    "attitude_id": attitude.id if attitude else False,
                    "attitude_found": bool(attitude),
                }).id)
            rec.preview_line_ids = lines

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = (
                    self.env["ir.sequence"].next_by_code("pms.initialize") or "New"
                )
        return super().create(vals_list)

    def action_initialize(self):
        self.ensure_one()
        if self.state == "initialized":
            raise UserError(_("PMS is already initialized."))
        if not self.employee_ids:
            raise UserError(_("Please select at least one employee."))
        if not self.financial_year_id:
            raise UserError(_("Please select a Financial Year."))

        created = 0
        skipped = 0
        no_kra = []
        no_attitude = []

        for employee in self.employee_ids:
            # Check across ALL initializations for same employee + financial year
            # (cancelled PMS records don't count — a new one can be created)
            existing = self.env["pms.appraisal"].search([
                ("employee_id", "=", employee.id),
                ("financial_year_id", "=", self.financial_year_id.id),
                ("state", "!=", "cancelled"),
            ], limit=1)
            if existing:
                skipped += 1
                continue

            kra = False
            if employee.job_id:
                kra = self.env["pms.kra"].search([
                    ("job_id", "=", employee.job_id.id),
                    ("financial_year_id", "=", self.financial_year_id.id),
                    ("company_id", "=", self.company_id.id),
                ], limit=1)

            if not kra:
                no_kra.append(employee.name)
                continue

            attitude = self.env["pms.attitude"].search([
                ("financial_year_id", "=", self.financial_year_id.id),
            ], limit=1)

            if not attitude:
                no_attitude.append(employee.name)
                continue

            appraisal = self.env["pms.appraisal"].create({
                "employee_id": employee.id,
                "initialize_id": self.id,
                "financial_year_id": self.financial_year_id.id,
                "kra_id": kra.id,
                "attitude_id": attitude.id,
            })
            appraisal._populate_kra_lines()
            appraisal._populate_attitude_lines()
            created += 1

            if appraisal.employee_user_id:
                appraisal._send_pms_email(
                    to_user=appraisal.employee_user_id,
                    subject=f"[PMS] Your PMS Initialized — {self.financial_year_name}",
                    body=appraisal._email_body("initialized"),
                )

        self.write({"state": "initialized"})

        msg = _("%d PMS record(s) created.") % created
        if skipped:
            msg += _(" ⚠️ %d employee(s) skipped — PMS already exists for this Financial Year.") % skipped
        if no_kra:
            msg += _(" ⚠️ No KRA found for: %s") % ", ".join(no_kra)
        if no_attitude:
            msg += _(" ⚠️ No Work Attitude and Behavior found for: %s") % ", ".join(no_attitude)

        notif_type = "warning" if (no_kra or no_attitude) else "success"
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("PMS Initialized"),
                "message": msg,
                "type": notif_type,
                "sticky": bool(no_kra),
                "next": {"type": "ir.actions.client", "tag": "soft_reload"},
            },
        }

    def action_cancel(self):
        """Open wizard to enter cancel reason."""
        self.ensure_one()
        if self.state == "cancelled":
            raise UserError(_("Already cancelled."))
        non_draft = self.appraisal_ids.filtered(lambda a: a.state != "draft")
        if non_draft:
            raise UserError(
                _(
                    "Cannot cancel this PMS Initialization — the following employee(s) "
                    "have already moved past Draft: %s. A PMS Initialization can only be "
                    "cancelled while all its PMS records are still in Draft."
                ) % ", ".join(non_draft.mapped("employee_id.name"))
            )
        return {
            "name": _("Cancel PMS Initialization"),
            "type": "ir.actions.act_window",
            "res_model": "pms.initialize.cancel.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_initialize_id": self.id},
        }

    def action_reset_draft(self):
        """Head only — reset a cancelled initialization back to Draft."""
        self.ensure_one()
        if self.state != "cancelled":
            raise UserError(_("Only Cancelled PMS Initialization can be reset to Draft."))
        self.write({"state": "draft", "cancel_reason": False})
        self.message_post(
            body=Markup("<b>PMS Initialization reset to Draft</b> by <b>%(usr)s</b>.")
            % {"usr": self.env.user.name},
            subtype_xmlid="mail.mt_comment",
        )

    def _do_cancel(self, cancel_reason):
        """Cancel initialization and all linked draft appraisals."""
        self.ensure_one()
        self.write({"state": "cancelled", "cancel_reason": cancel_reason})
        # Cancel all draft appraisals linked to this initialization
        draft_appraisals = self.appraisal_ids.filtered(lambda a: a.state == "draft")
        for appraisal in draft_appraisals:
            appraisal._do_cancel(cancel_reason)
        self.message_post(
            body=Markup(
                "<b>PMS Initialization Cancelled</b> by <b>%(usr)s</b>.<br/>"
                "<b>Reason:</b> %(reason)s"
            ) % {"usr": self.env.user.name, "reason": cancel_reason or "-"},
            subtype_xmlid="mail.mt_comment",
        )

    def unlink(self):
        for rec in self:
            if rec.appraisal_ids:
                raise UserError(
                    _(
                        "Cannot delete PMS Initialization '%s' because it has %d PMS record(s) linked to it. "
                        "Please delete the PMS records first."
                    ) % (rec.name, len(rec.appraisal_ids))
                )
        return super().unlink()

    def action_view_appraisals(self):
        return {
            "name": _("PMS Records"),
            "type": "ir.actions.act_window",
            "res_model": "pms.appraisal",
            "view_mode": "list,form",
            "domain": [("initialize_id", "=", self.id)],
            "context": {"default_initialize_id": self.id},
        }


class PmsInitializePreview(models.TransientModel):
    _name = "pms.initialize.preview"
    _description = "PMS Initialize Preview"

    initialize_id = fields.Many2one("pms.initialize", ondelete="cascade")
    employee_id = fields.Many2one("hr.employee", string="Employee", readonly=True)
    job_id = fields.Many2one("hr.job", string="Job Position", readonly=True)
    kra_id = fields.Many2one("pms.kra", string="KRA Assigned", readonly=True)
    kra_found = fields.Boolean(string="KRA Found", readonly=True)
    attitude_id = fields.Many2one(
        "pms.attitude", string="Work Attitude and Behavior Assigned", readonly=True
    )
    attitude_found = fields.Boolean(string="Work Attitude and Behavior Found", readonly=True)
