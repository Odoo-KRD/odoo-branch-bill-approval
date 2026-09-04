from odoo.addons.branch_bill_approval.hooks import (
    ensure_approval_menu_group_visibility,
    ensure_reviewer_group_user_memberships,
)


def migrate(cr, version):
    ensure_reviewer_group_user_memberships(cr)
    ensure_approval_menu_group_visibility(cr)
