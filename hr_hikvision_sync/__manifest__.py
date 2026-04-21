{
    'name': 'Hikvision iVMS-4200 Attendance Sync',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Attendances',
    'summary': 'Sync attendance records from Hikvision devices via ISAPI',
    'description': """
Hikvision iVMS-4200 Attendance Integration
==========================================
Connects Odoo 19 HR Attendance module to Hikvision biometric/access control
devices using the Hikvision ISAPI (HTTP REST) protocol.

Features:
- Configure multiple Hikvision devices
- Manual sync via wizard
- Automatic hourly sync via scheduled action
- Maps Hikvision employee badge numbers to Odoo hr.employee (barcode field)
- Handles both check-in and check-out events
- Duplicate prevention
    """,
    'author': 'Custom',
    'depends': ['hr_attendance'],
    'data': [
        'security/ir.model.access.csv',
        'data/cron_sync.xml',
        'views/hikvision_device_views.xml',
        'views/hikvision_sync_wizard_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
