from odoo import _, models
from odoo.exceptions import UserError


class AccountMoveReversal(models.TransientModel):
    _inherit = "account.move.reversal"

    def _branch_approval_reversal_moves(self):
        self.ensure_one()
        moves = self.env["account.move"]
        if "move_ids" in self._fields:
            moves |= self.move_ids
        active_model = self.env.context.get("active_model")
        active_ids = self.env.context.get("active_ids") or []
        if active_model == "account.move" and active_ids:
            moves |= self.env["account.move"].browse(active_ids).exists()
        return moves.filtered(
            lambda move: move._is_approval_document()
            and move.move_type in ("in_invoice", "in_refund", "out_invoice", "out_refund")
            and move.approval_route != "not_required"
        )

    def _raise_if_branch_approval_modify_reversal(self):
        controlled_moves = self._branch_approval_reversal_moves()
        if not controlled_moves:
            return
        raise UserError(
            _(
                "Reverse and Create Invoice cannot be used for approval-controlled bills, invoices, or credit notes because Odoo must auto-post the reversal credit note before it can create the replacement document. Use Reverse instead, submit/approve/post the credit note, then create the replacement bill or invoice separately."
            )
        )

    def reverse_moves(self, *args, **kwargs):
        is_modify = bool(kwargs.get("is_modify")) or bool(args and args[0])
        refund_method = getattr(self, "refund_method", False)
        if is_modify or refund_method == "modify":
            self._raise_if_branch_approval_modify_reversal()
        return super().reverse_moves(*args, **kwargs)

    def modify_moves(self, *args, **kwargs):
        self._raise_if_branch_approval_modify_reversal()
        return super().modify_moves(*args, **kwargs)
