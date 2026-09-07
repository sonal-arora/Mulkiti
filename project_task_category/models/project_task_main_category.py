# Copyright 2026 Mulkiti
from odoo import api, fields, models


class ProjectTaskMainCategory(models.Model):
    """Top-level task category master (Configuration > Main Categories).

    Groups related Sub Categories together (e.g. "Email", "Server",
    "Access").
    """
    _name = 'project.task.main.category'
    _description = 'Task Main Category'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(help="Technical code used to identify this main category.")
    sequence = fields.Integer(default=10)
    description = fields.Text()
    sub_category_ids = fields.One2many(
        'project.task.sub.category', 'main_category_id', string='Sub Category Lines',
    )
    sub_category_count = fields.Integer(string='Sub Categories', compute='_compute_sub_category_count')
    active = fields.Boolean(default=True)

    # _name_uniq = models.Constraint(
    #     'unique (name)',
    #     'A main category with this name already exists.',
    # )

    @api.depends('sub_category_ids')
    def _compute_sub_category_count(self):
        for category in self:
            category.sub_category_count = len(category.sub_category_ids)
