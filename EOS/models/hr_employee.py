# -*- coding: utf-8 -*-
from odoo import models, fields


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # Extend the lifecycle status introduced by hr_employee_probation
    # (Probation -> Confirmed) with the two exit-process states driven by
    # the EOS module.
    employment_status = fields.Selection(selection_add=[
        ('notice_period', 'Under Notice Period'),
        ('end_of_service', 'End of Service'),
    ], ondelete={
        'notice_period': 'set default',
        'end_of_service': 'set default',
    })
