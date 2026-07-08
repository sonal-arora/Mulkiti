from odoo import fields, models


class PmsRating(models.Model):
    _name = "pms.rating"
    _description = "PMS Rating Master"
    _order = "name"

    name = fields.Char(string="Rating", required=True)
    description = fields.Text(string="Description")
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("name_uniq", "unique(name)", "Rating name must be unique."),
    ]
