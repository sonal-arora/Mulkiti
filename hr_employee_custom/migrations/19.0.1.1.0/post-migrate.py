from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Fill the new fixed Joining Date from each employee's first contract."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    employees = env['hr.employee'].with_context(active_test=False).search([
        ('joining_date', '=', False),
    ])
    for employee in employees:
        first_date = employee._get_first_contract_date(no_gap=False)
        if first_date:
            employee.with_context(tracking_disable=True).joining_date = first_date
