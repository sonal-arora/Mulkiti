{
    'name': 'Company Documents & Policies',
    'version': '1.0.0',
    'summary': 'Manage and share company documents and policies with employees',
    'description': """
        Company Documents & Policies
        ============================
        - Upload company documents and policies
        - Set visibility: Public (all employees) or Private (HR/Admin only)
        - Categorize documents (Policy, Announcement, Handbook, SOP, etc.)
        - Employees can view public documents from their portal
        - HR/Admin can manage all documents
    """,
    'category': 'Human Resources',
    'author': 'Mulkiti',
    'depends': ['hr', 'mail', 'portal'],
    'assets': {
        'web.assets_backend': [
            'company_documents/static/src/js/document_view_tracker.js',
        ],
    },
    'data': [
        'security/company_documents_security.xml',
        'security/ir.model.access.csv',
        'data/document_category_data.xml',
        'data/mail_template.xml',
        'views/signature_views.xml',
        'views/company_document_views.xml',
        'views/company_document_menu.xml',
        'views/portal_document_views.xml',
        'views/sign_portal_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
