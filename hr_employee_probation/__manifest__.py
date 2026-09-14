# -*- coding: utf-8 -*-
{
    'name': 'HR Employee Probation Workflow',
    'version': '19.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Probation to Regular confirmation workflow on the Employee form',
    'description': """
Employee Probation Workflow
============================
Adds a Probation -> Confirmed (Regular) workflow to the Employee form:

* Probation End Date field on the employee
* Employment Status (Probation / Confirmed) shown as a badge
* "Confirm as Regular" button (HR Officer/Manager only) to close out probation
* Warning banner once the probation end date has passed without confirmation
* Daily reminder emails to HR (14 / 7 / 1 / 0 days before the end date)
""",
    'author': 'Mulkiti',
    'depends': ['hr'],
    'data': [
        'data/ir_cron.xml',
        'views/hr_employee_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
