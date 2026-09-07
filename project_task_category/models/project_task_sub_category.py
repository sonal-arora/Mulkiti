# Copyright 2026 Mulkiti
from odoo import fields, models


class ProjectTaskSubCategory(models.Model):
    """Task sub-category master (Configuration > Sub Categories).

    Belongs to a Main Category and carries a Default Priority, so tasks
    filed under it can be pre-classified and given an SLA/deadline
    automatically.
    """
    _name = 'project.task.sub.category'
    _description = 'Task Sub Category'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(help="Technical code used to identify this sub category.")
    main_category_id = fields.Many2one(
        'project.task.main.category', string='Main Category', required=True, ondelete='restrict',
    )
    description = fields.Text()
    sequence = fields.Integer(default=10)
    default_priority_id = fields.Many2one(
        'project.task.priority', string='Default Priority',
        help="Priority automatically applied to tasks created under this sub category.",
    )
    working_hours = fields.Float(
        string='Working Hours', digits=(16, 2),
        help="Manually entered — total working hours per day for tasks "
             "under this sub category. Applied automatically to a task's "
             "own Working Hours field when this Sub Category is selected "
             "on it (purely informational, not tied to any calendar).",
    )
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint(
        'unique (code)',
        'A sub category with this code already exists.',
    )
