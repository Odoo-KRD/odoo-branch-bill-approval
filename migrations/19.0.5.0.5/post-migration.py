from odoo import SUPERUSER_ID, api

from odoo.addons.branch_bill_approval.hooks import (
    ensure_auditor_schema,
    normalize_automatic_entry_approval_state,
)


def migrate(cr, version):
    """Repair approval state for records affected by the previous routing gaps."""
    ensure_auditor_schema(cr)
    normalize_automatic_entry_approval_state(cr)

    env = api.Environment(cr, SUPERUSER_ID, {})
    moves = env["account.move"].search([
        ("move_type", "in", ["in_invoice", "out_invoice", "entry"]),
        ("state", "=", "posted"),
        ("approval_state", "=", "approved"),
        ("approval_route", "not in", ["not_required", "auditor"]),
        ("auditor_approver_id", "!=", False),
    ])
    moves.filtered(lambda move: move._is_approval_document())._forward_posted_entries_to_auditor()
