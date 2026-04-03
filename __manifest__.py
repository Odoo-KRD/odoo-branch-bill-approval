{
    "name": "Branch Bill Approval",
    "version": "19.0.2.0.0",
    "summary": "Vendor bill approval workflow with Branch and CEO approval routes",
    "description": """
Branch Bill Approval
====================

Adds a controlled approval workflow for vendor bills in Odoo 19.

Main capabilities:
- Not Required route
- Branch Only route
- Branch then CEO route
- CEO Only route
- Approval activity scheduling
- Rejection with reason
- Posting restriction until approval is complete
- Approval audit trail in the bill form and chatter
""",
    "category": "Accounting/Accounting",
    "author": "HostKurd",
    "maintainer": "HostKurd",
    "website": "https://odoo.krd/modules/bill-approval/",
    "license": "MIT",
    "depends": ["account", "mail"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/res_company_views.xml",
        "views/account_move_views.xml",
        "views/approval_reject_wizard_views.xml",
    ],
    "images": [
        "static/description/banner.png",
        "static/description/assets/screenshots/screenshot_1.png",
        "static/description/assets/screenshots/screenshot_2.png",
        "static/description/assets/screenshots/screenshot_3.png",
        "static/description/assets/screenshots/screenshot_4.png",
        "static/description/assets/screenshots/screenshot_5.png",
        "static/description/assets/screenshots/screenshot_6.png",
    ],
    "installable": True,
    "application": False,
}
