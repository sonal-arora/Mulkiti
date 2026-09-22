from odoo import fields, models


class ProjectErrorType(models.Model):
    _name = 'project.error.type'
    _description = 'Project Error Type'
    _order = 'name'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint(
        'unique(name)',
        'This error type already exists.',
    )
