{
    'name': 'Project Task Categories & Priorities',
    'version': '19.0.1.0.0',
    'summary': 'Configurable categories/priorities + Ticket Ageing (TAT/SLA) for Project & Tasks',
    'description': """
Adds three configuration masters under Project > Configuration:

  Priorities      — dynamic priority levels (Critical/High/Medium/...),
                     each with a Deadline Type (Fixed Hours / Manual) and
                     Deadline Hours, replacing a hardcoded priority list.

  Main Categories — top-level task categories (e.g. Email, Server, Access).

  Sub Categories   — belong to a Main Category, and carry a Default
                     Priority applied automatically when used.

Ticket Ageing / TAT / SLA on Project Tasks:

  - Ageing starts on ticket creation, and restarts whenever a ticket
    (re-)enters a "To Do" stage.
  - TAT deadline is computed on a full 24h/day basis, but skips weekends
    and company holidays entirely (business-day aware, not office-hour
    aware) using the company's Resource Calendar.
  - A ticket flips to Overdue once its TAT deadline passes (checked every
    15 minutes by a scheduled action), notifying everyone linked to it
    (assignees, followers, and the ticket's Tag group).
  - An email reminder goes out to the ticket's Tag group (an Employee
    Tag, e.g. "Group 1"/"Group 2") about ~15 minutes before Ageing End.
  - Status/stage changes notify everyone linked to the ticket.
    """,
    'category': 'Services/Project',
    'author': 'Mulkiti',
    'website': '',
    'depends': ['project', 'hr'],
    'data': [
        'security/ir.model.access.csv',
        'views/project_task_sub_category_views.xml',
        'views/project_task_main_category_views.xml',
        'views/project_task_priority_views.xml',
        'views/project_task_sla_status_views.xml',
        'data/project_task_sla_status_data.xml',
        'views/project_task_views.xml',
        'views/menu_views.xml',
        'data/ir_cron_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
