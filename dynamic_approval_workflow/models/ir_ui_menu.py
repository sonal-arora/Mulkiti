from odoo import api, models


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    def _visible_menu_ids(self, debug=False):
        """ Brickwork Leaves viewers only get their own app: the whole Time Off
        app is hidden from them, unless they are also Time Off Officers. """
        visible_ids = super()._visible_menu_ids(debug)
        user = self.env.user
        if not user.has_group('dynamic_approval_workflow.group_brickwork_leave_viewer') \
                or user.has_group('hr_holidays.group_hr_holidays_user'):
            return visible_ids
        time_off_root = self.env.ref('hr_holidays.menu_hr_holidays_root', raise_if_not_found=False)
        if not time_off_root:
            return visible_ids
        hidden_ids = self.sudo().with_context(active_test=False).search(
            [('id', 'child_of', time_off_root.id)]
        ).ids
        return visible_ids - set(hidden_ids)
