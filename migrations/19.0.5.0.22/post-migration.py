from odoo.addons.branch_bill_approval.hooks import (
    ensure_approval_menu_group_visibility,
    seed_default_approval_settings,
)


def migrate(cr, version):
    seed_default_approval_settings(cr)
    ensure_approval_menu_group_visibility(cr)
