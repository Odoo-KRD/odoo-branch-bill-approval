from odoo.addons.branch_bill_approval.hooks import (
    cleanup_launcher_visibility_settings,
    ensure_approval_menu_group_visibility,
    seed_default_approval_settings,
)


def migrate(cr, version):
    seed_default_approval_settings(cr)
    cleanup_launcher_visibility_settings(cr)
    ensure_approval_menu_group_visibility(cr)
