import json
import unicodedata

from werkzeug.exceptions import Forbidden, NotFound

from odoo import http, _
from odoo.http import request

from ..models.company_document import UPLOAD_TAG

PREVIEW_IMAGE = ('image/png', 'image/jpeg', 'image/gif', 'image/webp', 'image/bmp')


class CompanyDocumentController(http.Controller):

    def _get_document(self, document_id):
        """Document the current user may open: through folder access, or as
        the signer of a signature request on it (HR sent it to them)."""
        doc = request.env['company.document'].browse(document_id).exists()
        if not doc:
            raise NotFound()
        is_signer = request.env['company.document.signature'].sudo().search_count([
            ('document_id', '=', doc.id),
            ('user_id', '=', request.env.user.id),
        ], limit=1)
        if not is_signer:
            doc.check_access('read')
        return doc, bool(is_signer)

    def _get_file_access(self, doc, is_signer):
        # Folder options apply to everyone, managers included (they can still
        # get the file from the form's file field).
        can_preview, can_download = doc._get_folder_file_options()
        # A signer must always be able to read what they are asked to sign.
        return can_preview or is_signer, can_download

    def _file_stream(self, doc):
        # document_file is restricted to managers: access was checked above.
        doc = doc.sudo()
        if not doc.document_file:
            raise NotFound()
        return request.env['ir.binary']._get_stream_from(
            doc, 'document_file', filename=doc.document_filename)

    # ── Download with tracking ────────────────────────────────────────────────
    # ── File upload (form widget) ─────────────────────────────────────────────

    @http.route('/company-documents/upload', auth='user', type='http', methods=['POST'])
    def upload_document_file(self, ufile, **kwargs):
        """Store the file sent as multipart in a temporary attachment. The
        form then saves only its id (upload_attachment_id), never the base64
        content, which crashes the browser on large files."""
        if not request.env.user.has_group('company_documents.group_company_document_manager'):
            return json.dumps({'error': _('Only document managers can upload files.')})
        ufile = request.httprequest.files.get('ufile')
        if not ufile:
            return json.dumps({'error': _('No file received.')})
        # Safari sends file names in NFD form.
        filename = unicodedata.normalize('NFC', ufile.filename or 'document')
        attachment = request.env['ir.attachment'].sudo().create({
            'name': filename,
            'raw': ufile.read(),
            'res_model': 'company.document',
            'res_id': 0,
            'description': UPLOAD_TAG,
        })
        return json.dumps([{
            'id': attachment.id,
            'filename': filename,
            'mimetype': attachment.mimetype,
            'size': attachment.file_size,
        }])

    @http.route('/company-documents/download/<int:document_id>', auth='user', type='http')
    def download_document(self, document_id, **kwargs):
        doc, is_signer = self._get_document(document_id)
        if not self._get_file_access(doc, is_signer)[1]:
            raise Forbidden(_('Download is not allowed for the documents of this folder.'))
        stream = self._file_stream(doc)

        request.env['company.document.log'].sudo().create({
            'document_id': doc.id,
            'user_id': request.env.user.id,
            'action': 'downloaded',
        })
        return stream.get_response(as_attachment=True)

    # ── Preview ───────────────────────────────────────────────────────────────
    @http.route('/company-documents/preview/<int:document_id>', auth='user', type='http')
    def preview_document(self, document_id, **kwargs):
        doc, is_signer = self._get_document(document_id)
        can_preview, can_download = self._get_file_access(doc, is_signer)
        if not can_preview:
            raise Forbidden(_('Preview is not allowed for the documents of this folder.'))
        stream = self._file_stream(doc)

        mimetype = stream.mimetype or ''
        if mimetype == 'application/pdf':
            kind = 'pdf'
        elif mimetype in PREVIEW_IMAGE:
            kind = 'image'
        elif mimetype.startswith('video/'):
            kind = 'video'
        elif mimetype.startswith('text/'):
            kind = 'text'
        else:
            kind = 'other'

        doc.action_log_view()
        return request.render('company_documents.document_preview_page', {
            'document': doc.sudo(),
            'kind': kind,
            'can_download': can_download,
            'file_url': '/company-documents/preview/%d/file' % doc.id,
        })

    @http.route('/company-documents/preview/<int:document_id>/file', auth='user', type='http')
    def preview_document_file(self, document_id, **kwargs):
        """The file itself, served inline (never as an attachment) for the viewer."""
        doc, is_signer = self._get_document(document_id)
        if not self._get_file_access(doc, is_signer)[0]:
            raise Forbidden()
        response = self._file_stream(doc).get_response(as_attachment=False)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    # ── View log ─────────────────────────────────────────────────────────────
    @http.route('/company-documents/view/<int:document_id>', auth='user', type='jsonrpc')
    def log_view(self, document_id, **kwargs):
        doc = request.env['company.document'].browse(document_id)
        if not doc.exists():
            return {'success': False}
        doc.check_access('read')
        doc.action_log_view()
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
