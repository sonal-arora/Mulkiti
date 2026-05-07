from odoo import fields, models, tools


class HrLeaveSummary(models.Model):
    _name = 'hr.leave.summary'
    _description = 'Leave Summary'
    _auto = False
    _rec_name = 'employee_id'
    _order = 'employee_id, holiday_status_id'

    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    department_id = fields.Many2one('hr.department', string='Department', readonly=True)
    holiday_status_id = fields.Many2one('hr.leave.type', string='Leave Type', readonly=True)
    total_allocated = fields.Float(string='Total Allocated', readonly=True, digits=(16, 2))
    leaves_taken = fields.Float(string='Used', readonly=True, digits=(16, 2))
    pending_approval = fields.Float(string='Pending Approval', readonly=True, digits=(16, 2))
    balance = fields.Float(string='Balance', readonly=True, digits=(16, 2))

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW hr_leave_summary AS
            SELECT
                row_number() OVER ()   AS id,
                e.id                   AS employee_id,
                cur.department_id      AS department_id,
                lt.id                  AS holiday_status_id,
                COALESCE(al.allocated, 0.0)  AS total_allocated,
                COALESCE(lv.taken,    0.0)   AS leaves_taken,
                COALESCE(pn.pending,  0.0)   AS pending_approval,
                GREATEST(
                    COALESCE(al.allocated, 0.0) - COALESCE(lv.taken, 0.0),
                    0.0
                )                            AS balance
            FROM hr_employee e

            -- Current version: latest active version on or before today
            LEFT JOIN (
                SELECT DISTINCT ON (employee_id)
                    employee_id,
                    department_id
                FROM hr_version
                WHERE active = TRUE
                  AND date_version <= CURRENT_DATE
                ORDER BY employee_id, date_version DESC
            ) cur ON cur.employee_id = e.id

            CROSS JOIN hr_leave_type lt

            -- Validated allocations
            LEFT JOIN (
                SELECT employee_id, holiday_status_id, SUM(number_of_days) AS allocated
                FROM hr_leave_allocation
                WHERE state = 'validate'
                GROUP BY employee_id, holiday_status_id
            ) al ON al.employee_id = e.id AND al.holiday_status_id = lt.id

            -- Approved / taken leaves
            LEFT JOIN (
                SELECT employee_id, holiday_status_id, SUM(number_of_days) AS taken
                FROM hr_leave
                WHERE state = 'validate'
                  AND employee_id IS NOT NULL
                GROUP BY employee_id, holiday_status_id
            ) lv ON lv.employee_id = e.id AND lv.holiday_status_id = lt.id

            -- Pending approval
            LEFT JOIN (
                SELECT employee_id, holiday_status_id, SUM(number_of_days) AS pending
                FROM hr_leave
                WHERE state IN ('confirm', 'validate1', 'validate2')
                  AND employee_id IS NOT NULL
                GROUP BY employee_id, holiday_status_id
            ) pn ON pn.employee_id = e.id AND pn.holiday_status_id = lt.id

            WHERE e.active = TRUE
              AND (
                    COALESCE(al.allocated, 0.0) > 0
                 OR COALESCE(lv.taken,    0.0) > 0
                 OR COALESCE(pn.pending,  0.0) > 0
              )
        """)
