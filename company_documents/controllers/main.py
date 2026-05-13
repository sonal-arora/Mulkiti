import base64
from odoo import fields, http, _
from odoo.http import request


class CompanyDocumentController(http.Controller):

    # ── Download with tracking ────────────────────────────────────────────────
    @http.route('/company-documents/download/<int:document_id>', auth='user', type='http')
    def download_document(self, document_id, **kwargs):
        doc = request.env['company.document'].browse(document_id)
        if not doc.exists():
            return request.not_found()

        request.env['company.document.log'].sudo().create({
            'document_id': doc.id,
            'user_id': request.env.user.id,
            'action': 'downloaded',
        })

        return request.env['ir.binary']._get_stream_from(
            doc, 'document_file', filename=doc.document_filename
        ).get_response(as_attachment=True)

    # ── View log ─────────────────────────────────────────────────────────────
    @http.route('/company-documents/view/<int:document_id>', auth='user', type='jsonrpc')
    def log_view(self, document_id, **kwargs):
        doc = request.env['company.document'].browse(document_id)
        if not doc.exists():
            return {'success': False}

        existing = request.env['company.document.log'].sudo().search([
            ('document_id', '=', doc.id),
            ('user_id', '=', request.env.user.id),
            ('action', '=', 'viewed'),
            ('date', '>=', fields.Datetime.today()),
        ], limit=1)

        if not existing:
            request.env['company.document.log'].sudo().create({
                'document_id': doc.id,
                'user_id': request.env.user.id,
                'action': 'viewed',
            })
        return {'success': True}

    # ── Signature Portal Page ─────────────────────────────────────────────────
    @http.route('/document/sign/<int:document_id>/<string:token>',
                auth='user', type='http', website=True)
    def sign_document(self, document_id, token, **kwargs):
        """Show document signing page to employee."""
        sig_request = request.env['company.document.signature'].sudo().search([
            ('document_id', '=', document_id),
            ('token', '=', token),
            ('user_id', '=', request.env.user.id),
        ], limit=1)

        if not sig_request:
            return request.render('company_documents.sign_page_error', {
                'error': _('Invalid or expired signature link.'),
            })

        if sig_request.state == 'signed':
            return request.render('company_documents.sign_page_already_signed', {
                'sig': sig_request,
            })

        return request.render('company_documents.sign_page', {
            'sig': sig_request,
            'document': sig_request.document_id,
            'employee': sig_request.employee_id,
        })

    @http.route('/document/sign/submit', auth='user', type='http',
                methods=['POST'], website=True, csrf=True)
    def sign_submit(self, document_id, token, signature=None, action='sign', reason='', **kwargs):
        """Handle signature submission or decline."""
        sig_request = request.env['company.document.signature'].sudo().search([
            ('document_id', '=', int(document_id)),
            ('token', '=', token),
            ('user_id', '=', request.env.user.id),
            ('state', '=', 'pending'),
        ], limit=1)

        if not sig_request:
            return request.render('company_documents.sign_page_error', {
                'error': _('Invalid request or already processed.'),
            })

        if action == 'decline':
            sig_request.write({
                'state': 'declined',
                'decline_reason': reason,
            })
            return request.render('company_documents.sign_page_declined', {
                'sig': sig_request,
            })

        if not signature:
            return request.render('company_documents.sign_page', {
                'sig': sig_request,
                'document': sig_request.document_id,
                'employee': sig_request.employee_id,
                'error': _('Please provide your signature.'),
            })

        # Save signature (comes as base64 data URL: "data:image/png;base64,...")
        if ',' in signature:
            signature = signature.split(',')[1]

        sig_request.action_mark_signed(signature)

        return request.render('company_documents.sign_page_success', {
            'sig': sig_request,
            'document': sig_request.document_id,
        })
