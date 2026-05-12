from odoo import fields, models, _
from odoo.exceptions import UserError
import base64
import csv
import io
import pytz
import xlsxwriter


class HrPayrollPaymentReportWizard(models.TransientModel):
    _inherit = 'hr.payroll.payment.report.wizard'

    export_format = fields.Selection(
        selection_add=[
            ('l10n_ae_wps', 'UAE WPS (.sif)'),
            ('l10n_ae_wps_xlsx', 'UAE WPS (.xlsx)'),
            ('l10n_ae_sif_report', 'SIF Excel Report (.xlsx)'),
        ],
        default='l10n_ae_wps',
        ondelete={
            'l10n_ae_wps': 'set csv',
            'l10n_ae_wps_xlsx': 'set csv',
            'l10n_ae_sif_report': 'set csv',
        }
    )
    l10n_ae_employer_narrative = fields.Char(string="Employer Reference")

    def _l10n_ae_get_company_wps(self, raise_if_multi=False):
        """
        Return the appropriate company based on whether the
        wizard is called upon a batch or individual payslips
        :param raise_if_multi: (optional) Check and raise error if payslips belong to multiple companies
        :return: A record of res.company
        """
        self.ensure_one()
        if self.payslip_run_id:
            return self.payslip_run_id.company_id
        if raise_if_multi and len(self.payslip_ids.company_id) > 1:
            raise UserError(_("WPS report can only be generated for one company at a time"))
        return self.payslip_ids.company_id[:1]

    def _perform_checks(self):
        super()._perform_checks()
        if self.export_format in ('l10n_ae_wps', 'l10n_ae_wps_xlsx'):
            # Strict WPS submission checks — all fields mandatory
            payslips = self.payslip_ids.filtered(lambda p: p.state == "validated" and p.net_wage > 0)
            employees = payslips.employee_id
            invalid_banks_employee_ids = employees.filtered(lambda e: not e.primary_bank_account_id.bank_id.l10n_ae_routing_code)
            if invalid_banks_employee_ids:
                raise UserError(_(
                    "Missing UAE routing code for the bank account for the following employees:\n%s",
                    invalid_banks_employee_ids.mapped('name')))
            missing_id_employee_ids = employees.filtered(
                lambda e: not e.l10n_ae_wps_employee_id and not e.identification_id
            )
            if missing_id_employee_ids:
                raise UserError(_(
                    "Missing WPS Employee Unique ID (or Emirates ID) for the following employees:\n%s",
                    missing_id_employee_ids.mapped('name')))

            company = self._l10n_ae_get_company_wps(raise_if_multi=True)
            company_bank_account = company.l10n_ae_bank_account_id
            if not company_bank_account:
                raise UserError(_("Please set the salaries bank account in the settings"))
            if not company_bank_account.bank_id.l10n_ae_routing_code:
                raise UserError(_("Missing UAE routing code for the salaries bank account"))
            if not company.l10n_ae_employer_code:
                raise UserError(_("Please set the Employer Unique ID in the settings"))
        # SIF Excel Report — no mandatory field checks, missing data shown as blank in Excel

    def _l10n_ae_wps_render_xlsx(self, create_time):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('WPS')

        records = self.payslip_ids._l10n_ae_get_wps_data()
        footer = self._l10n_ae_get_wps_footer(create_time)

        for row_idx, row in enumerate(records + footer):
            worksheet.write_row(row_idx, 0, row)

        workbook.close()
        return base64.encodebytes(output.getvalue())

    def _l10n_ae_wps_render_csv(self, create_time):
        csv_data = io.StringIO()
        csv_writer = csv.writer(csv_data, delimiter=',')

        sif_records = self.payslip_ids._l10n_ae_get_wps_data()
        sif_footer = self._l10n_ae_get_wps_footer(create_time)

        for row in sif_records + sif_footer:
            csv_writer.writerow(row)
        csv_data.seek(0)
        generated_file = csv_data.read()
        csv_data.close()
        return base64.encodebytes(generated_file.encode())

    def _l10n_ae_sif_report_render_xlsx(self):
        """
        Generate a readable Excel SIF report with proper column headers.
        Format matches the SIF file generator Excel layout.
        """
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('SIF Report')

        # ── Formats ──────────────────────────────────────────────────
        header_fmt = workbook.add_format({
            'bold': True,
            'bg_color': '#4472C4',
            'font_color': '#FFFFFF',
            'border': 1,
            'align': 'center',
            'valign': 'vcenter',
            'text_wrap': True,
        })
        cell_fmt = workbook.add_format({'border': 1, 'valign': 'vcenter'})
        date_fmt = workbook.add_format({'border': 1, 'valign': 'vcenter', 'num_format': 'YYYY-MM-DD'})
        number_fmt = workbook.add_format({'border': 1, 'valign': 'vcenter', 'num_format': '#,##0.00'})
        int_fmt = workbook.add_format({'border': 1, 'valign': 'vcenter', 'num_format': '0'})
        total_fmt = workbook.add_format({
            'bold': True, 'border': 1, 'bg_color': '#D9E1F2',
            'valign': 'vcenter', 'num_format': '#,##0.00',
        })

        # ── Headers ──────────────────────────────────────────────────
        headers = [
            'Employee Name',
            'Employee Unique ID',
            'Agent ID / Routing No.',
            'Employee Account with Agent',
            'Pay Start Date',
            'Pay End Date',
            'Days in Period',
            'Income Fixed Component',
            'Income Variable Component',
            'Days on Leave for Period',
            'Validation Remarks',
        ]
        col_widths = [24, 20, 20, 32, 14, 14, 14, 24, 24, 22, 22]

        worksheet.set_row(0, 30)
        for col, (header, width) in enumerate(zip(headers, col_widths)):
            worksheet.set_column(col, col, width)
            worksheet.write(0, col, header, header_fmt)

        # ── Data rows ─────────────────────────────────────────────────
        input_codes = [
            "HOUALLOWINP", "CONVALLOWINP", "MEDALLOWINP",
            "ANNUALPASSALLOWINP", "OVERTIMEALLOWINP", "OTALLOWINP", "LEAVEENCASHINP",
        ]
        inputs_dict = self.payslip_ids._get_line_values(input_codes)

        row_idx = 1
        total_fixed = 0.0
        total_variable = 0.0

        payslips = self.payslip_ids.filtered(
            lambda p: p.state == "validated" and p.net_wage > 0
        )

        for payslip in payslips:
            employee = payslip.employee_id
            bank_account = employee.primary_bank_account_id
            routing_code = bank_account.bank_id.l10n_ae_routing_code or ''

            # Variable inputs
            evp_inputs = [inputs_dict[code][payslip.id]['total'] for code in input_codes]
            total_evp = sum(evp_inputs)
            fixed_component = payslip.net_wage - total_evp

            # Unpaid (leave) days
            unpaid_days = payslip.worked_days_line_ids.filtered(
                lambda x: x.work_entry_type_id in payslip.struct_id.unpaid_work_entry_type_ids
            )
            leave_days = sum(unpaid_days.mapped('number_of_days'))

            wps_uid = (employee.l10n_ae_wps_employee_id or employee.identification_id or '').zfill(14)

            worksheet.set_row(row_idx, 18)
            worksheet.write(row_idx, 0, employee.name or '', cell_fmt)
            worksheet.write(row_idx, 1, wps_uid, cell_fmt)
            worksheet.write(row_idx, 2, routing_code.zfill(9) if routing_code else '', cell_fmt)
            worksheet.write(row_idx, 3, bank_account.acc_number or '', cell_fmt)
            worksheet.write_datetime(row_idx, 4, payslip.date_from, date_fmt)
            worksheet.write_datetime(row_idx, 5, payslip.date_to, date_fmt)
            worksheet.write(row_idx, 6, (payslip.date_to - payslip.date_from).days + 1, int_fmt)
            worksheet.write(row_idx, 7, round(fixed_component, 2), number_fmt)
            worksheet.write(row_idx, 8, round(total_evp, 2), number_fmt)
            worksheet.write(row_idx, 9, leave_days, int_fmt)
            worksheet.write(row_idx, 10, '', cell_fmt)  # Validation Remarks

            total_fixed += fixed_component
            total_variable += total_evp
            row_idx += 1

        # ── Totals row ────────────────────────────────────────────────
        worksheet.set_row(row_idx, 22)
        worksheet.write(row_idx, 0, 'TOTAL', workbook.add_format({
            'bold': True, 'border': 1, 'bg_color': '#D9E1F2',
            'align': 'center', 'valign': 'vcenter',
        }))
        for col in range(1, 7):
            worksheet.write(row_idx, col, '', workbook.add_format({
                'bold': True, 'border': 1, 'bg_color': '#D9E1F2',
            }))
        worksheet.write(row_idx, 7, round(total_fixed, 2), total_fmt)
        worksheet.write(row_idx, 8, round(total_variable, 2), total_fmt)
        for col in range(9, 11):
            worksheet.write(row_idx, col, '', workbook.add_format({
                'bold': True, 'border': 1, 'bg_color': '#D9E1F2',
            }))

        workbook.close()
        return base64.encodebytes(output.getvalue())

    # TODO: adjust for multiple bank accounts
    def generate_payment_report(self):
        super().generate_payment_report()
        if self.export_format in ('l10n_ae_wps', 'l10n_ae_wps_xlsx'):
            now = fields.Datetime.now()
            user_tz = pytz.timezone(self.env.context.get('tz') or self.env.user.tz or 'UTC')
            create_time = pytz.utc.localize(now, is_dst=None).astimezone(user_tz)
            filename = self._get_l10n_ae_wps_file_name(create_time)
            file, ext = (self._l10n_ae_wps_render_csv(create_time), '.sif') \
                if self.export_format == 'l10n_ae_wps' \
                else (self._l10n_ae_wps_render_xlsx(create_time), '.xlsx')
            self._write_file(file, ext, filename)
        elif self.export_format == 'l10n_ae_sif_report':
            file = self._l10n_ae_sif_report_render_xlsx()
            batch_name = self.payslip_run_id.name if self.payslip_run_id else 'Payslips'
            self._write_file(file, '.xlsx', f'SIF Report - {batch_name}')

    def _get_l10n_ae_wps_file_name(self, create_time):
        self.ensure_one()
        timestamp = create_time.strftime('%y%m%d%H%M%S')
        employer_code = self._l10n_ae_get_company_wps().l10n_ae_employer_code
        return f"{(employer_code or '')[:13].zfill(13)}{timestamp}"

    def _l10n_ae_get_wps_footer(self, create_time):
        self.ensure_one()
        company = self._l10n_ae_get_company_wps()
        return [[
            "SCR",
            (company.l10n_ae_employer_code or '').zfill(13),
            (company.l10n_ae_bank_account_id.bank_id.l10n_ae_routing_code or '').zfill(9),
            create_time.strftime("%Y-%m-%d") if create_time else '',
            create_time.strftime("%H%M") if create_time else '',
            self.payslip_run_id.date_start and self.payslip_run_id.date_start.strftime("%m%Y") or '',
            len(self.payslip_ids),
            self.env['hr.payslip']._l10n_ae_get_wps_formatted_amount(sum(self.payslip_ids.mapped('net_wage'))),
            "AED",
            self.l10n_ae_employer_narrative or '/',
        ]]
