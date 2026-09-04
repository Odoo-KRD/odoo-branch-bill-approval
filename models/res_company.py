from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    branch_bill_approver_id = fields.Many2one(
        "res.users",
        string="Branch Approver",
        help="Default branch approver for vendor bills, vendor credit notes, customer invoices, customer credit notes, and journal entries of this company/branch.",
    )
    ceo_bill_approver_id = fields.Many2one(
        "res.users",
        string="CEO Approver",
        help="CEO or final approver for vendor bills, vendor credit notes, customer invoices, customer credit notes, and journal entries.",
    )
    account_approval_auditor_id = fields.Many2one(
        "res.users",
        string="Legacy Auditor User",
        help="Legacy company-level Auditor. The global Auditor in Settings > Accounting Approval is preferred; this value is used only as a fallback when the global Auditor is empty.",
    )

    def _register_hook(self):
        result = super()._register_hook()
        # Defensive startup safety: if the new Auditor code is loaded before the
        # database schema has been upgraded, create the nullable columns needed
        # by the Auditor release before any HTTP request fetches res.company.
        from ..hooks import ensure_auditor_schema

        ensure_auditor_schema(self.env.cr)
        return result
