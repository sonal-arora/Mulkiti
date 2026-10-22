from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class HrEmployeeCategory(models.Model):
    _inherit = 'hr.employee.category'

    is_brickwork = fields.Boolean(string="Brickwork", copy=False)

    _brickwork_unique = models.UniqueIndex(
        "(is_brickwork) WHERE is_brickwork IS TRUE",
        "Only one Employee Tag can be marked as Brickwork.",
    )

    @api.constrains('is_brickwork')
    def _check_single_brickwork(self):
        if self.search_count([('is_brickwork', '=', True)]) > 1:
            raise ValidationError(_("Only one Employee Tag can be marked as Brickwork."))
