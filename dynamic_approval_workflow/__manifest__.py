{
    'name': 'Leave Multi-Level Approval',
    'version': '19.0.2.0.0',
    'summary': '3-level leave approval: Manager/1st Approver → 2nd Approver (optional) → Time Off Manager',
    'description': """
Adds a configurable multi-level leave approval workflow:

  1st Level  — Employee's Manager (parent_id) OR a custom 1st Approver field.
               Both users can see and approve the leave.

  2nd Level  — A custom 2nd Approver field on the employee.
               Only this person (or HR Manager) can approve this step.
               If no 2nd Approver is set, this step is skipped automatically.

  Final      — Time Off Manager (leave_manager_id on the employee).

States: Draft → Confirm → 1st Approved (validate1) → 2nd Approved (validate2, optional) → Validated
    """,
    'category': 'Human Resources/Time Off',
    'author': 'Mulkiti',
    'depends': ['hr_holidays'],
    'data': [
        'security/security.xml',
        'views/hr_employee_views.xml',
        'views/hr_leave_views.xml',
        'views/hr_leave_approver_menu.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
