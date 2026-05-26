# -*- coding: utf-8 -*-
from odoo import fields, models


class HrPayslipEos(models.Model):
    _inherit = 'hr.payslip'

    eos_id = fields.Many2one(
        'hr.eos',
        string='EOS Record',
        readonly=True,
        copy=False,
        help='Linked End of Service record for Final Settlement payslip',
    )
