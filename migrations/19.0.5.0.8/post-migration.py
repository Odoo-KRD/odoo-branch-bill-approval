from odoo.addons.branch_bill_approval.hooks import (
    ensure_auditor_schema,
    seed_global_auditor_setting,
)


def migrate(cr, version):
    ensure_auditor_schema(cr)
    seed_global_auditor_setting(cr)
