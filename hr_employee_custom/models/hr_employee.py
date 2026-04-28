# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import date, timedelta
import logging

_logger = logging.getLogger(__name__)


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # ─── Work Permit Fields ───────────────────────────────────────────
    work_permit_document = fields.Binary(
        string='Work Permit Document',
        attachment=True,
    )
    work_permit_document_name = fields.Char(string='Work Permit File Name')
    work_permit_issue_date = fields.Date(string='Work Permit Issue Date')

    # Work permit expiry already exists in base: permit_expiration_date
    # We use it for notification

    # ─── Gratuity ─────────────────────────────────────────────────────
    gratuity_amount = fields.Float(
        string='Gratuity',
        # compute='_compute_gratuity',
        store=True,
        help='Gratuity calculated based on Basic Salary and years of service',
    )

    document_ids = fields.One2many('employee.document', 'employee_id', string="Documents")
    document_count = fields.Integer(compute="_compute_document_count")
    mol_contract_date = fields.Date(string='MOL Contract date')
    leave_second_approver_id = fields.Many2one(
        'res.users',
        string="Second Leave Approver"
    )

    def _compute_document_count(self):
        for rec in self:
            rec.document_count = len(rec.document_ids)

    def action_view_documents(self):
        return {
            'name': 'Documents',
            'type': 'ir.actions.act_window',
            'res_model': 'employee.document',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }

class EmployeePublic(models.Model):
    _inherit = 'hr.employee.public'

    work_permit_document_name = fields.Char()
    work_permit_issue_date = fields.Date()
    gratuity_amount = fields.Float()
    mol_contract_date = fields.Date()
    leave_second_approver_id = fields.Many2one(
        'res.users',
        string="Second Leave Approver"
    )