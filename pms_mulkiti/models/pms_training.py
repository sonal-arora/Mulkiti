from odoo import fields, models


class PmsTraining(models.Model):
    _name = "pms.training"
    _description = "Training Master"
    _order = "financial_year_id desc, name"

    name = fields.Char(string="Name", required=True)
    financial_year_id = fields.Many2one(
        "pms.financial.year",
        string="Financial Year",
        required=True,
    )
    line_ids = fields.One2many(
        "pms.training.line",
        "training_id",
        string="Projects",
    )
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
    )

    _financial_year_uniq = models.Constraint(
        "unique(financial_year_id, company_id)",
        "A Training already exists for this Financial Year and Company.",
    )


class PmsTrainingLine(models.Model):
    _name = "pms.training.line"
    _description = "Training Line - Project"
    _order = "sequence, id"

    training_id = fields.Many2one(
        "pms.training", string="Training", required=True, ondelete="cascade"
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Name", required=True)
