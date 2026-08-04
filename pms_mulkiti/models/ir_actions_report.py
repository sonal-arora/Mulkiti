from odoo import models


class IrActionsReport(models.Model):
    _inherit = "ir.actions.report"

    def _build_wkhtmltopdf_args(self, paperformat_id, landscape, specific_paperformat_args=None, set_viewport_size=False):
        command_args = super()._build_wkhtmltopdf_args(
            paperformat_id,
            landscape,
            specific_paperformat_args=specific_paperformat_args,
            set_viewport_size=set_viewport_size,
        )
        # wkhtmltopdf ignores --footer-right whenever a report also supplies
        # --footer-html, so this is a no-op for every report with its own
        # HTML footer (e.g. invoices). It only takes effect for reports that
        # render no <div class="footer"> at all — i.e. the PMS appraisal
        # report, which deliberately skips the HTML/JS footer because it
        # breaks on wkhtmltopdf builds without patched Qt.
        command_args += ["--footer-right", "Page [page] of [topage]", "--footer-font-size", "8"]
        # Unpatched-Qt wkhtmltopdf builds (e.g. 0.12.6) sometimes misread the
        # UTF-8 HTML as Latin-1, turning curly quotes/dashes into "â€™"-style
        # garbage. Forcing the encoding explicitly avoids that regardless of
        # what the binary would otherwise guess.
        command_args += ["--encoding", "utf-8"]
        return command_args
