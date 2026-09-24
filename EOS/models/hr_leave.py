from odoo import fields, models


class HrLeave(models.Model):
    _inherit = 'hr.leave'

    active = fields.Boolean(default=True)
