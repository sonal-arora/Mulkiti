from odoo import fields, models


class PmsKra(models.Model):
    _name = "pms.kra"
    _description = "KRA Master - Key Result Areas"
    _order = "financial_year_id desc, name"

    name = fields.Char(string="KRA Name", required=True)
    financial_year_id = fields.Many2one(
        "pms.financial.year",
        string="Financial Year",
        required=True,
    )
    financial_year_name = fields.Char(
        related="financial_year_id.name",
        store=True,
        string="Financial Year",
    )
    job_id = fields.Many2one(
        "hr.job",
        string="Job Position",
        required=True,
        help="Job position this KRA applies to",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
    )
    line_ids = fields.One2many(
        "pms.kra.line",
        "kra_id",
        string="Job Responsibilities & Deliverables",
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "job_year_uniq",
            "unique(job_id, financial_year_id, company_id)",
            "KRA already exists for this Job Position and Financial Year.",
        ),
    ]


class PmsKraLine(models.Model):
    _name = "pms.kra.line"
    _description = "KRA Line - Job Responsibility & Deliverable"
    _order = "sequence, id"

    kra_id = fields.Many2one("pms.kra", string="KRA", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    job_responsibility = fields.Char(
        string="Job Responsibility / KRA", required=True
    )
    deliverable = fields.Text(string="Key Deliverable / Target")
