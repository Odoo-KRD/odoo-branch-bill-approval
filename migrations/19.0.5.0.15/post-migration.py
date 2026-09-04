from odoo.addons.branch_bill_approval.hooks import ensure_approval_menu_group_visibility


def migrate(cr, version):
    ensure_approval_menu_group_visibility(cr)
