# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import timedelta
from odoo.exceptions import UserError

class EmployeeDocument(models.Model):
    _name = 'employee.document'
    _description = 'Employee Document'
    _inherit = ['mail.thread']

    name = fields.Char("Document Number")
    employee_id = fields.Many2one('hr.employee', required=True)

    document_type = fields.Selection([
        ('passport', 'Passport'),
        ('visa', 'Visa'),
        ('eid', 'EID'),
        ('labour', 'Labour Card'),
        ('cv', 'CV'),
        ('certificate', 'Certificate'),
        ('iloe', 'ILOE'),
        ('medical_insurance', 'Medical Insurance'),
        ('others', 'Others')
    ], string="Document")

    issue_date = fields.Date()
    expiry_date = fields.Date()

    document_file = fields.Binary("File", attachment=True)
    file_name = fields.Char("File Name")

    state = fields.Selection([
        ('valid', 'Valid'),
        ('expire_soon', 'Expire Soon'),
        ('expired', 'Expired')
    ], compute="_compute_state", store=True)

    @api.depends('expiry_date')
    def _compute_state(self):
        today = fields.Date.today()
        for rec in self:
            if not rec.expiry_date:
                rec.state = 'valid'
            elif rec.expiry_date < today:
                rec.state = 'expired'
            elif rec.expiry_date <= today + timedelta(days=30):
                rec.state = 'expire_soon'
            else:
                rec.state = 'valid'

    def cron_expiry_notification(self):
        today = fields.Date.today()
        alert_date = today + timedelta(days=30)

        docs = self.search([
            ('expiry_date', '<=', alert_date),
            ('expiry_date', '>=', today)
        ])

        hr_group = self.env.ref('hr.group_hr_user')
        hr_users = self.env['res.users'].sudo().search([
            ('group_ids', 'in', [hr_group.id]),
            ('active', '=', True),
        ])
        email_list = hr_users.filtered(lambda u: u.partner_id.email).mapped('partner_id.email')

        for doc in docs:
            doc.message_post(
                body=f"Document {doc.document_type} of {doc.employee_id.name} will expire on {doc.expiry_date}"
            )

            if email_list:
                self.env['mail.mail'].create({
                    'subject': 'Document Expiry Alert',
                    'body_html': f"""
                        <p>Document <b>{doc.document_type}</b> of employee <b>{doc.employee_id.name}</b>
                        will expire on <b>{doc.expiry_date}</b></p>
                    """,
                    'email_to': ','.join(email_list),
                }).send()