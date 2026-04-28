# -*- coding: utf-8 -*-
{
    'name': 'HR Employee Custom - UAE',
    'version': '19.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Custom HR Employee form for UAE',
    'depends': [
        'hr',
        # 'hr_contract',
        'hr_payroll',
        'hr_holidays',
    ],
    'data': [
        # 'security/security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'views/hr_employee_views.xml',
        'views/employee_document_views.xml',
        # 'views/hr_leave_allocation_view.xml',

    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
