import io

from odoo import _
from odoo.exceptions import UserError
from odoo.http import Controller, content_disposition, request, route


def _clean(value):
    if value is False or value is None:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return value


class PmsAppraisalXlsxController(Controller):

    @route("/pms/appraisal/export_xlsx", type="http", auth="user")
    def export_appraisal_xlsx(self, ids, **kwargs):
        record_ids = [int(i) for i in ids.split(",") if i]
        appraisals = request.env["pms.appraisal"].browse(record_ids).exists()
        appraisals = appraisals.filtered(lambda a: a.state == "approved")
        if not appraisals:
            raise UserError(_("No Approved PMS record found to export."))

        import xlsxwriter  # noqa: PLC0415

        buffer = io.BytesIO()
        workbook = xlsxwriter.Workbook(buffer, {"in_memory": True})
        worksheet = workbook.add_worksheet(_("PMS Report"))

        header_fmt = workbook.add_format({
            "bold": True, "bg_color": "#D9E1F2", "border": 1, "valign": "vcenter",
        })
        cell_fmt = workbook.add_format({"border": 1, "text_wrap": True, "valign": "top"})

        headers = [
            _("Appraisal Ref"), _("Employee"), _("Department"), _("Job Position"),
            _("Financial Year"), _("1st Approver (Manager)"), _("2nd Approver"),
            _("KRA Set"), _("Status"),
            _("Submitted On"), _("Manager Reviewed On"), _("Approved On"),
            _("KRA / Responsibility"), _("Key Deliverable / Target"),
            _("Self Rating"), _("Self Comments"),
            _("Manager Rating"), _("Manager Comments"),
            _("2nd Approver Rating"), _("2nd Approver Comments"),
            _("Overall Self Comments"), _("Overall Manager Comments"), _("Overall 2nd Approver Comments"),
        ]
        worksheet.write_row(0, 0, headers, header_fmt)
        worksheet.freeze_panes(1, 0)

        state_labels = dict(request.env["pms.appraisal"]._fields["state"].selection)

        row = 1
        for appraisal in appraisals:
            header_values = [
                appraisal.name,
                appraisal.employee_id.name,
                appraisal.department_id.name,
                appraisal.job_id.name,
                appraisal.financial_year_id.name,
                appraisal.manager_id.name,
                appraisal.second_manager_id.name,
                appraisal.kra_id.name,
                state_labels.get(appraisal.state),
                appraisal.submit_date,
                appraisal.manager_review_date,
                appraisal.approval_date,
            ]
            overall_values = [
                appraisal.overall_self_comments,
                appraisal.overall_manager_comments,
                appraisal.overall_second_comments,
            ]
            lines = appraisal.line_ids
            if not lines:
                values = header_values + [""] * 8 + overall_values
                worksheet.write_row(row, 0, [_clean(v) for v in values], cell_fmt)
                row += 1
                continue
            for line in lines:
                values = header_values + [
                    line.job_responsibility,
                    line.deliverable,
                    line.self_rating_id.name,
                    line.self_comments,
                    line.manager_rating_id.name,
                    line.manager_comments,
                    line.second_rating_id.name,
                    line.second_comments,
                ] + overall_values
                worksheet.write_row(row, 0, [_clean(v) for v in values], cell_fmt)
                row += 1

        for col_idx in range(len(headers)):
            worksheet.set_column(col_idx, col_idx, 22)

        workbook.close()
        content = buffer.getvalue()
        buffer.close()

        response_headers = [
            ("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ("Content-Disposition", content_disposition(_("PMS Approved Report.xlsx"))),
        ]
        return request.make_response(content, response_headers)
