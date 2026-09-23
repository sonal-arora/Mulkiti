{
    'name': 'Project Error Log',
    'version': '19.0.1.0.0',
    'category': 'Services/Project',
    'summary': 'Track errors/mistakes reported against projects (replaces the Excel error log)',
    'description': """
Project Error Log
==================
Adds an "Error Log" menu under the Project app to record errors reported
against a project/unit: who reported it, who made it, the type of error,
description, screenshots, and whether it is a repeated or new error.
""",
    'author': 'Mulkiti',
    'depends': ['project'],
    'data': [
        'security/project_error_log_groups.xml',
        'security/ir.model.access.csv',
        'data/project_error_log_sequence.xml',
        'views/project_error_type_views.xml',
        'views/project_error_log_views.xml',
        'views/project_error_log_menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
