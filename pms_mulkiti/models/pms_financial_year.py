from odoo import fields, models


class PmsFinancialYear(models.Model):
    _name = "pms.financial.year"
    _description = "PMS Financial Year"
    _order = "date_start desc"

    name = fields.Char(string="Financial Year", required=True, help="e.g. 2025-26")
    date_start = fields.Date(string="Start Date", required=True)
    date_end = fields.Date(string="End Date", required=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("name_uniq", "unique(name)", "Financial Year name must be unique."),
    ]
