# Copyright 2026 Mulkiti
from odoo import api, fields, models


class ProjectTaskPriority(models.Model):
    """Configurable task priority master (Configuration > Priorities).

    Replaces a hardcoded priority selection with a master table so new
    priority levels and their SLA/deadline rules can be added without
    touching code.
    """
    _name = 'project.task.priority'
    _description = 'Task Priority'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, help="Technical code used to identify this priority (e.g. 'critical').")
    sequence = fields.Integer(default=10)
    deadline_type = fields.Selection([
        ('fixed', 'Fixed Hours'),
        ('manual', 'Manual'),
    ], string='Deadline Type', default='fixed', required=True,
        help="Fixed Hours: the deadline is auto-computed from Deadline Hours.\n"
             "Manual: no automatic deadline is set.")
    deadline_hours = fields.Float(
        string='Deadline Hours',
        help="Number of hours after creation by which a task at this priority is due. "
             "Ignored when Deadline Type is Manual.",
    )
    sub_category_ids = fields.One2many(
        'project.task.sub.category', 'default_priority_id', string='Sub Category Lines',
    )
    sub_category_count = fields.Integer(string='Sub Cat', compute='_compute_sub_category_count')
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint(
        'unique (code)',
        'A priority with this code already exists.',
    )

    @api.depends('sub_category_ids')
    def _compute_sub_category_count(self):
        for priority in self:
            priority.sub_category_count = len(priority.sub_category_ids)
