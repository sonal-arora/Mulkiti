from odoo import models, fields, _
from odoo.exceptions import UserError


class HrLeaveAllocation(models.Model):
    _inherit = 'hr.leave.allocation'

    cf = fields.Float(string="Carrying Forward")



class HrLeave(models.Model):
    _inherit = 'hr.leave'

    # state = fields.Selection(selection_add=[
    #     ('second_approve', 'Second Approval')
    # ])

    # def action_approve(self):
    #     for leave in self:
    #
    #         user = self.env.user
    #         employee = leave.employee_id
    #
    #         # ✅ Step 1: Manager Approval
    #         if leave.state == 'confirm':
    #             if user != employee.parent_id.user_id:
    #                 raise UserError(_("Only Manager can approve at this stage"))
    #
    #             # move to next
    #             if employee.leave_second_approver_id:
    #                 leave.state = 'second_approve'
    #             else:
    #                 leave.state = 'validate1'
    #
    #         # ✅ Step 2: Second Approver
    #         elif leave.state == 'second_approve':
    #             if user != employee.leave_second_approver_id:
    #                 raise UserError(_("Only Second Approver can approve"))
    #
    #             leave.state = 'validate1'
    #
    #         # ✅ Step 3: HR Final Approval
    #         elif leave.state == 'validate1':
    #             # HR group check
    #             if not user.has_group('hr_holidays.group_hr_holidays_user'):
    #                 raise UserError(_("Only HR can finalize leave"))
    #
    #             return super(HrLeave, leave).action_approve()
    #
    #     return True