from odoo import _, fields, models
from odoo.exceptions import UserError


class ApprovalRejectWizard(models.TransientModel):
    _name = "approval.reject.wizard"
    _description = "Reject Accounting Approval or Auditor Review"

    move_id = fields.Many2one("account.move", required=True, readonly=True)
    reason = fields.Text(required=True)

    def action_confirm(self):
        self.ensure_one()
        if not self.reason or not self.reason.strip():
            raise UserError(_("Please provide a rejection reason."))
        return self.move_id.with_context(approval_reject_reason=self.reason.strip()).action_reject_approval()
