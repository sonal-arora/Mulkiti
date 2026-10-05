from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Put existing documents into a per-company "General" folder open to all
    employees, so everyone keeps seeing exactly what they saw before."""
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {
        'skip_document_notification': True,
        'document_allow_published_edit': True,
    })
    Document = env['company.document'].with_context(active_test=False)
    docs = Document.search([('folder_id', '=', False)])
    for company in docs.company_id:
        folder = env['company.document.folder'].create({
            'name': 'General',
            'company_id': company.id,
            'access_type': 'all',
            'sequence': 1,
        })
        docs.filtered(lambda d: d.company_id == company).write({'folder_id': folder.id})
