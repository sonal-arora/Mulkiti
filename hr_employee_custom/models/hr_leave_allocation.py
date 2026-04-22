from odoo import models, fields

class HrLeaveAllocation(models.Model):
    _inherit = 'hr.leave.allocation'

    cf = fields.Float(string="Carrying Forward")