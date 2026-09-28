from odoo import fields, models


class PmsFinancialYear(models.Model):
    _name = "pms.financial.year"
    _description = "PMS Financial Year"
    _order = "date_start desc"

    name = fields.Char(string="Financial Year", required=True, help="e.g. 2025-26")
    date_start = fields.Date(string="Start Date", required=True)
    date_end = fields.Date(string="End Date", required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
    )

    _name_uniq = models.Constraint(
        "unique(name, company_id)",
        "Financial Year name must be unique per company.",
    )
