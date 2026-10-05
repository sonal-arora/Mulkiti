from odoo import _, fields, models
from odoo.exceptions import AccessError


class ResUsers(models.Model):
    _inherit = 'res.users'

    document_folder_ids = fields.Many2many(
        comodel_name='company.document.folder',
        relation='company_document_folder_user_rel',
        column1='user_id',
        column2='folder_id',
        string='Document Folders',
        help='Company Document folders (with "Specific Users" access) this user can see.',
    )


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # Edited from the employee form by Document Managers, who usually have no
    # write access on res.users, so the inverse writes the folder side instead.
    document_folder_ids = fields.Many2many(
        comodel_name='company.document.folder',
        string='Document Folders',
        compute='_compute_document_folder_ids',
        inverse='_inverse_document_folder_ids',
    )

    def _compute_document_folder_ids(self):
        for employee in self:
            employee.document_folder_ids = employee.user_id.sudo().document_folder_ids

    def _inverse_document_folder_ids(self):
        if not self.env.user.has_group('company_documents.group_company_document_manager'):
            raise AccessError(_('Only Document Managers can change document folder access.'))
        for employee in self.filtered('user_id'):
            user = employee.user_id
            current = user.sudo().document_folder_ids
            wanted = employee.document_folder_ids
            (wanted - current).write({'user_ids': [(4, user.id)]})
            (current - wanted).write({'user_ids': [(3, user.id)]})
