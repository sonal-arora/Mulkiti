from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PmsReviewCycle(models.Model):
    _name = "pms.review.cycle"
    _description = "PMS Review Cycle"
    _order = "financial_year_id desc, sequence, id"

    # Longer period = higher number. Used to validate that a cycle can only
    # roll up into a strictly longer period (Quarterly -> Half-Yearly ->
    # Annual), and to walk the hierarchy without hardcoding names elsewhere.
    _PERIOD_LEVEL = {"quarterly": 1, "half_yearly": 2, "annual": 3}

    name = fields.Char(string="Cycle Name", required=True, help="e.g. Q1 2025-26, H1 2025-26, Annual 2025-26")
    financial_year_id = fields.Many2one(
        "pms.financial.year",
        string="Financial Year",
        required=True,
    )
    period_type = fields.Selection(
        [
            ("quarterly", "Quarterly"),
            ("half_yearly", "Half-Yearly"),
            ("annual", "Annual"),
        ],
        string="Period Type",
        required=True,
        default="annual",
    )
    sequence = fields.Integer(
        default=10,
        help="Order within the same Period Type and Financial Year, e.g. Q1=1, Q2=2, Q3=3, Q4=4.",
    )
    date_start = fields.Date(string="Start Date", required=True)
    date_end = fields.Date(string="End Date", required=True)
    parent_cycle_id = fields.Many2one(
        "pms.review.cycle",
        string="Rolls Up Into",
        domain="[('financial_year_id', '=', financial_year_id), ('id', '!=', id)]",
        help="The longer period this cycle is a part of, e.g. Q1 & Q2 roll up "
             "into H1, and H1 & H2 roll up into Annual. Used to gate "
             "initialization (the parent cannot start until every child is "
             "Approved for an employee) and to roll up ratings.",
    )
    child_cycle_ids = fields.One2many(
        "pms.review.cycle", "parent_cycle_id", string="Sub-Periods",
    )
    company_id = fields.Many2one(
        "res.company",
        default=lambda self: self.env.company,
    )
    active = fields.Boolean(default=True)
    appraisal_ids = fields.One2many("pms.appraisal", "review_cycle_id", string="PMS Records")
    appraisal_count = fields.Integer(compute="_compute_appraisal_count")

    _sql_constraints = [
        (
            "name_year_uniq",
            "unique(name, financial_year_id, company_id)",
            "A Review Cycle with this name already exists for this Financial Year.",
        ),
    ]

    @api.depends("appraisal_ids")
    def _compute_appraisal_count(self):
        for rec in self:
            rec.appraisal_count = len(rec.appraisal_ids)

    @api.onchange("financial_year_id")
    def _onchange_financial_year_id(self):
        if self.financial_year_id:
            self.date_start = self.financial_year_id.date_start
            self.date_end = self.financial_year_id.date_end

    @api.constrains("parent_cycle_id", "period_type", "financial_year_id")
    def _check_parent_cycle(self):
        for rec in self:
            if not rec.parent_cycle_id:
                continue
            if rec.parent_cycle_id.financial_year_id != rec.financial_year_id:
                raise ValidationError(_(
                    "'%(child)s' and its parent cycle '%(parent)s' must belong to the same Financial Year."
                ) % {"child": rec.name, "parent": rec.parent_cycle_id.name})
            child_level = self._PERIOD_LEVEL.get(rec.period_type, 0)
            parent_level = self._PERIOD_LEVEL.get(rec.parent_cycle_id.period_type, 0)
            if parent_level <= child_level:
                period_labels = dict(rec._fields["period_type"].selection)
                raise ValidationError(_(
                    "'%(parent)s' (%(parent_type)s) cannot be the parent of '%(child)s' (%(child_type)s). "
                    "A cycle can only roll up into a strictly longer period: Quarterly → Half-Yearly → Annual."
                ) % {
                    "parent": rec.parent_cycle_id.name,
                    "parent_type": period_labels.get(rec.parent_cycle_id.period_type),
                    "child": rec.name,
                    "child_type": period_labels.get(rec.period_type),
                })

    @api.constrains("parent_cycle_id")
    def _check_no_cycle_loop(self):
        for rec in self:
            seen = set()
            current = rec.parent_cycle_id
            while current:
                if current.id in seen or current.id == rec.id:
                    raise ValidationError(_("Circular Review Cycle linkage detected — a cycle cannot roll up into itself or one of its own sub-periods."))
                seen.add(current.id)
                current = current.parent_cycle_id

    def action_view_appraisals(self):
        self.ensure_one()
        return {
            "name": _("PMS Records"),
            "type": "ir.actions.act_window",
            "res_model": "pms.appraisal",
            "view_mode": "list,form",
            "domain": [("review_cycle_id", "=", self.id)],
        }

    # ── Gating: parent cycle can't start for an employee until every child
    #    cycle has an Approved appraisal for that employee ───────────────────

    def _children_approved_for_employee(self, employee):
        """True if this cycle has no sub-periods, or every sub-period has an
        Approved PMS record for the given employee."""
        self.ensure_one()
        if not self.child_cycle_ids:
            return True
        for child in self.child_cycle_ids:
            approved = self.env["pms.appraisal"].search_count([
                ("employee_id", "=", employee.id),
                ("review_cycle_id", "=", child.id),
                ("state", "=", "approved"),
            ])
            if not approved:
                return False
        return True
