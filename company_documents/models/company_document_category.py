from odoo import fields, models


class CompanyDocumentCategory(models.Model):
    _name = 'company.document.category'
    _description = 'Document Category'
    _order = 'sequence, name'

    name = fields.Char(string='Category Name', required=True, translate=True)
    sequence = fields.Integer(string='Sequence', default=10)
    color = fields.Integer(string='Color Index')
    document_count = fields.Integer(
        string='Documents',
        compute='_compute_document_count',
    )

    def _compute_document_count(self):
        for cat in self:
            cat.document_count = self.env['company.document'].search_count(
                [('category_id', '=', cat.id)]
            )
