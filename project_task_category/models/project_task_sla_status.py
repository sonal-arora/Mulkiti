# Copyright 2026 Mulkiti
from odoo import fields, models


class ProjectTaskSlaStatus(models.Model):
    """Configurable SLA Status master (Configuration > SLA Statuses).

    Lets the business define/rename the SLA status labels shown on tasks
    (e.g. "Not Started", "Running", "Breached", "Completed") instead of a
    fixed selection list. `code` is the technical key the system uses to
    know which record represents which built-in state — it must stay one
    of: not_started, running, breached, done.
    """
    _name = 'project.task.sla.status'
    _description = 'Task SLA Status'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    code = fields.Selection([
        ('not_started', 'Not Started'),
        ('running', 'Running'),
        ('breached', 'Breached'),
        ('done', 'Completed'),
    ], required=True, help="Technical key the system uses to assign this status automatically.")
    sequence = fields.Integer(default=10)
    color = fields.Integer(string='Color', default=0)
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint(
        'unique (code)',
        'An SLA Status for this technical key already exists.',
    )
