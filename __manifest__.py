{
    "name": "Branch Accounting Approval",
    "version": "19.0.5.0.26",
    "summary": "Auditor, Branch, CEO, and final Auditor approval routing for accounting documents",
    "description": """
Branch Accounting Approval
==========================

Adds a controlled accounting approval workflow for vendor bills, vendor credit notes, customer invoices, customer credit notes, and journal entries in Odoo 19.

Main capabilities:
- Auditor Only route
- CEO Only route
- Branch then CEO route
- Branch Only route
- Restricted Not Required route
- Final Auditor approval for posted bills, invoices, and manual journal entries that use Branch/CEO routes
- Approval activity scheduling
- Auditor notification after accounting document posting
- Auditor approve/reject actions with recommendation capture
- Rejection with reason
- Posting restriction until approval is complete
- Workflow-field tamper protection
- Approver snapshots at submission
- Edit lock for approved-but-unposted documents
- Approval audit trail in the accounting document form and chatter
- CEO-pending documents hidden from the configured branch approver, while keeping the creator/submitter visibility
- Submitter tracking and filters for personal approval requests
- Ready-to-post notification activity after final pre-posting approval
- Auditor rejected posted accounting documents reset to draft for correction and resubmission
- Dedicated Accounting Approval settings and approval-only menus for non-bookkeeper approvers
- Configurable approval reset after completed routes and Reset to Draft synchronization
- Approval ribbons and reset support for rejected requests
- Assigned-only visibility enforcement for approval-only users, even if standard Invoicing access is assigned
- Read-only Assigned Journal Items menu for Branch Manager, CEO, and Auditor
- Assigned Manual Journal Entries menu for approval-only users without Bookkeeper permission
- Short Bill Approval app menu with the module icon in the Odoo app launcher
- Approval launcher visibility repaired for Branch Manager, CEO, and Auditor roles
- Direct Bill Approval app menu access for Branch Manager, CEO, Auditor, and Accountant roles
- Hide the approval-only Journal Items tab when the native Odoo Journal Items tab is already available
- Credit note approval workflow support for vendor and customer refunds
- Approval posting guard also covers reversal auto-post paths
- Product column in approval-only Journal Items views
- Odoo-consistent Analytic Distribution column in approval-only Journal Items views
- Prevents Reverse and Create Invoice from auto-posting unapproved credit notes
- Tightened approver visibility so default approver fields do not expose every draft/unsubmitted bill
- Approval-only users can open credit notes created with Reverse; the original document shows by name only
""",
    "category": "Accounting/Accounting",
    "author": "HostKurd",
    "maintainer": "HostKurd",
    "website": "https://odoo.krd/modules/accounting-approval/",
    "license": "Other OSI approved licence",
    "depends": ["account", "mail"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/res_company_views.xml",
        "views/res_config_settings_views.xml",
        "views/account_move_views.xml",
        "views/approval_menu_views.xml",
        "views/approval_reject_wizard_views.xml",
    ],
    "pre_init_hook": "pre_init_hook",
    "post_init_hook": "post_init_hook",
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
