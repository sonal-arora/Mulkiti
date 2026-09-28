from odoo import fields, models


class PmsRating(models.Model):
    _name = "pms.rating"
    _description = "PMS Rating Master"
    _order = "name"

    name = fields.Char(string="Rating", required=True)
    description = fields.Text(string="Description")
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
    )

    _name_uniq = models.Constraint(
        "unique(name, company_id)",
        "Rating name must be unique per company.",
    )
