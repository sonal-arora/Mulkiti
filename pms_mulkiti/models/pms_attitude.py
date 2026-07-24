from odoo import fields, models


class PmsAttitude(models.Model):
    _name = "pms.attitude"
    _description = "Work Attitude and Behavior Master"
    _order = "financial_year_id desc, name"

    name = fields.Char(string="Name", required=True)
    financial_year_id = fields.Many2one(
        "pms.financial.year",
        string="Financial Year",
        required=True,
    )
    line_ids = fields.One2many(
        "pms.attitude.line",
        "attitude_id",
        string="Attitude & Behavior Criteria",
    )
    active = fields.Boolean(default=True)


class PmsAttitudeLine(models.Model):
    _name = "pms.attitude.line"
    _description = "Work Attitude and Behavior Line"
    _order = "sequence, id"

    attitude_id = fields.Many2one(
        "pms.attitude", string="Work Attitude and Behavior", required=True, ondelete="cascade"
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Name", required=True)
    description = fields.Text(string="Description")
