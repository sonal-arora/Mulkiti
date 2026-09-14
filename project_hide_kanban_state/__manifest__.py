# -*- coding: utf-8 -*-
{
    'name': 'Project: Hide Task State on Kanban Card',
    'version': '19.0.1.0.0',
    'category': 'Project',
    'summary': "Remove the separate 'State' dot from the task Kanban card — Stage stays the single indicator",
    'description': """
Project: Hide Task State on Kanban Card
=========================================
Odoo's task Kanban card shows two independent indicators: the Stage
(which column it's in) and a separate State dot (In Progress / Changes
Requested / Approved / Done / Cancelled). Since these don't affect each
other, it's easy to confuse the two.

This module hides that State dot from the Kanban card only. Stage
remains the single source of truth, and is already shown consistently
between the Kanban board (columns) and the task Form view (statusbar) —
no syncing needed.

The State field/column is left untouched everywhere else (e.g. the List
view), in case it's still useful there for filtering/reporting.
""",
    'author': 'Mulkiti',
    'depends': ['project'],
    'data': [
        'views/project_task_kanban_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'project_hide_kanban_state/static/src/components/project_stage_kanban_selection/project_stage_kanban_selection.js',
            'project_hide_kanban_state/static/src/components/project_stage_kanban_selection/project_stage_kanban_selection.xml',
        ],
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
