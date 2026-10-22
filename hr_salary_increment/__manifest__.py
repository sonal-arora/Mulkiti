{
    'name': 'Salary Increment',
    'version': '19.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Record salary increments, approve them and update the employee contract',
    'description': """
Salary Increment
================
HR records an employee's salary increment (old vs new salary, increment %,
effective date). On approval a new contract version is created from the
effective date with the new salary. Contract start date and joining date stay
unchanged. Approved increments are locked.
    """,
    'author': 'Mulkiti',
    'depends': [
        'hr',
        'hr_payroll',
        'l10n_ae_hr_payroll',
        'hr_employee_custom',
        'mail',
    ],
    'data': [
        'security/hr_salary_increment_security.xml',
        'security/ir.model.access.csv',
        'data/hr_salary_increment_sequence.xml',
        'views/hr_salary_increment_views.xml',
        'views/hr_employee_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
