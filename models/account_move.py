from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from markupsafe import Markup, escape


class AccountMove(models.Model):
    _inherit = "account.move"

    approval_state = fields.Selection(
        [
            ("draft", "Draft"),
            ("waiting_branch", "Waiting Branch Approval"),
            ("waiting_ceo", "Waiting CEO Approval"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("not_required", "No Approval Required"),
        ],
        string="Approval Status",
        default="draft",
        tracking=True,
        copy=False,
    )

    approval_route = fields.Selection(
        [
            ("not_required", "Not Required"),
            ("branch", "Branch Only"),
            ("branch_ceo", "Branch then CEO"),
            ("ceo", "CEO Only"),
        ],
        string="Approval Route",
        default="not_required",
        tracking=True,
        copy=False,
    )

    branch_approver_id = fields.Many2one(
        "res.users",
        string="Branch Approver",
        related="company_id.branch_bill_approver_id",
        store=True,
        readonly=True,
        copy=False,
    )

    ceo_approver_id = fields.Many2one(
        "res.users",
        string="CEO Approver",
        related="company_id.ceo_bill_approver_id",
        store=True,
        readonly=True,
        copy=False,
    )

    submitted_for_approval = fields.Boolean(copy=False)
    submitted_for_approval_on = fields.Datetime(copy=False)

    branch_approved = fields.Boolean(copy=False)
    ceo_approved = fields.Boolean(copy=False)

    branch_approved_by = fields.Many2one(
        "res.users",
        string="Branch Approved By",
        copy=False,
    )
    branch_approved_on = fields.Datetime(copy=False)

    ceo_approved_by = fields.Many2one(
        "res.users",
        string="CEO Approved By",
        copy=False,
    )
    ceo_approved_on = fields.Datetime(copy=False)

    rejected_by = fields.Many2one(
        "res.users",
        string="Rejected By",
        copy=False,
    )
    rejected_on = fields.Datetime(copy=False)
    approval_reject_reason = fields.Text(copy=False)

    is_branch_approver = fields.Boolean(compute="_compute_current_user_flags")
    is_ceo_approver = fields.Boolean(compute="_compute_current_user_flags")
    can_submit_for_approval = fields.Boolean(compute="_compute_current_user_flags")
    can_branch_approve = fields.Boolean(compute="_compute_current_user_flags")
    can_ceo_approve = fields.Boolean(compute="_compute_current_user_flags")
    can_reject_approval = fields.Boolean(compute="_compute_current_user_flags")

    def name_get(self):
        result_map = dict(super().name_get())
        result = []
        for move in self:
            if move.move_type == "in_invoice":
                number = move.name or move.ref or _("Draft")
                partner = move.partner_id.name or ""
                label = _("Vendor Bill - %s") % number
                if partner:
                    label = _("%s - %s") % (label, partner)
                result.append((move.id, label))
            else:
                result.append((move.id, result_map.get(move.id, move.name or "/")))
        return result

    @api.depends_context("uid")
    def _compute_current_user_flags(self):
        user = self.env.user
        for move in self:
            move.is_branch_approver = bool(
                move.branch_approver_id and move.branch_approver_id.id == user.id
            )
            move.is_ceo_approver = bool(
                move.ceo_approver_id and move.ceo_approver_id.id == user.id
            )
            move.can_submit_for_approval = bool(
                move.move_type == "in_invoice"
                and move.state == "draft"
                and not move.submitted_for_approval
                and move.approval_route != "not_required"
            )
            move.can_branch_approve = bool(
                move.move_type == "in_invoice"
                and move.approval_state == "waiting_branch"
                and move.is_branch_approver
            )
            move.can_ceo_approve = bool(
                move.move_type == "in_invoice"
                and move.approval_state == "waiting_ceo"
                and move.is_ceo_approver
            )
            move.can_reject_approval = bool(
                move.can_branch_approve or move.can_ceo_approve
            )

    def _check_vendor_bill(self):
        for move in self:
            if move.move_type != "in_invoice":
                raise UserError(_("This workflow only applies to vendor bills."))

    def _validate_route_approvers(self):
        for move in self:
            if move.approval_route in ("branch", "branch_ceo") and not move.branch_approver_id:
                raise UserError(
                    _("Please set a Branch Bill Approver on the company before submitting this vendor bill.")
                )
            if move.approval_route in ("ceo", "branch_ceo") and not move.ceo_approver_id:
                raise UserError(
                    _("Please set a CEO Bill Approver on the company before submitting this vendor bill.")
                )

    def _compute_initial_approval_state(self):
        self.ensure_one()
        if self.approval_route == "not_required":
            return "not_required"
        if self.approval_route == "ceo":
            return "waiting_ceo"
        if self.approval_route in ("branch", "branch_ceo"):
            return "waiting_branch"
        return "not_required"

    def _ensure_branch_approver_user(self):
        self.ensure_one()
        if self.env.su:
            return
        if not self.branch_approver_id or self.env.user.id != self.branch_approver_id.id:
            raise AccessError(_("Only the configured Branch Bill Approver can approve this bill."))

    def _ensure_ceo_approver_user(self):
        self.ensure_one()
        if self.env.su:
            return
        if not self.ceo_approver_id or self.env.user.id != self.ceo_approver_id.id:
            raise AccessError(_("Only the configured CEO Bill Approver can approve this bill."))

    def _approval_activity_message(self, stage):
        self.ensure_one()
        bill_label = self.name or self.ref or _("Draft Bill")

        if stage == "branch":
            approver_name = self.branch_approver_id.name or _("Branch Approver")
            return {
                "summary": _("Bill needs Branch approval"),
                "note": _("Please review and approve vendor bill %s for %s.") % (
                    bill_label,
                    approver_name,
                ),
            }

        if stage == "ceo":
            approver_name = self.ceo_approver_id.name or _("CEO Approver")
            return {
                "summary": _("Bill needs CEO approval"),
                "note": _("Please review and approve vendor bill %s for %s.") % (
                    bill_label,
                    approver_name,
                ),
            }

        return {
            "summary": _("Vendor bill approval"),
            "note": _("Please review vendor bill %s.") % bill_label,
        }

    def _clear_approval_activities(self):
        todo = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        if not todo:
            return
        activities = self.env["mail.activity"].search([
            ("res_model", "=", "account.move"),
            ("res_id", "in", self.ids),
            ("activity_type_id", "=", todo.id),
        ])
        activities.unlink()

    def _schedule_approval_activity(self, user, stage):
        self.ensure_one()
        if not user:
            return
        self._clear_approval_activities()
        activity_type = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        if not activity_type:
            return
        message = self._approval_activity_message(stage)
        self.activity_schedule(
            activity_type_id=activity_type.id,
            user_id=user.id,
            summary=message["summary"],
            note=message["note"],
        )

    def _open_reject_wizard(self):
        self.ensure_one()
        if not self.can_reject_approval:
            raise AccessError(_("You are not allowed to reject this bill."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Reject Approval"),
            "res_model": "approval.reject.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_move_id": self.id,
            },
        }

    def action_submit_for_approval(self):
        for move in self:
            move._check_vendor_bill()

            if move.state != "draft":
                raise UserError(_("Only draft bills can be submitted for approval."))

            if move.approval_route == "not_required":
                raise UserError(
                    _("Bills with 'Not Required' approval route do not need submission for approval.")
                )

            move._validate_route_approvers()
            move.action_reset_approval()

            move.write({
                "approval_state": move._compute_initial_approval_state(),
                "submitted_for_approval": True,
                "submitted_for_approval_on": fields.Datetime.now(),
                "approval_reject_reason": False,
                "rejected_by": False,
                "rejected_on": False,
            })

            move.message_post(body=_("Bill submitted for approval."))

            if move.approval_state == "waiting_branch":
                move._schedule_approval_activity(move.branch_approver_id, "branch")
            elif move.approval_state == "waiting_ceo":
                move._schedule_approval_activity(move.ceo_approver_id, "ceo")

    def action_branch_approve(self):
        for move in self:
            move._check_vendor_bill()

            if move.approval_state != "waiting_branch":
                raise UserError(_("This bill is not waiting for branch approval."))

            move._ensure_branch_approver_user()

            move.write({
                "branch_approved": True,
                "branch_approved_by": self.env.user.id,
                "branch_approved_on": fields.Datetime.now(),
            })
            move.message_post(body=_("Branch approval completed by %s.") % self.env.user.name)
            move._clear_approval_activities()

            if move.approval_route == "branch_ceo":
                if not move.ceo_approver_id:
                    raise UserError(
                        _("A CEO Bill Approver must be configured on the company before this bill can continue.")
                    )
                move.write({"approval_state": "waiting_ceo"})
                move._schedule_approval_activity(move.ceo_approver_id, "ceo")
            else:
                move.write({"approval_state": "approved"})

    def action_ceo_approve(self):
        for move in self:
            move._check_vendor_bill()

            if move.approval_state != "waiting_ceo":
                raise UserError(_("This bill is not waiting for CEO approval."))

            move._ensure_ceo_approver_user()

            move.write({
                "ceo_approved": True,
                "ceo_approved_by": self.env.user.id,
                "ceo_approved_on": fields.Datetime.now(),
                "approval_state": "approved",
            })
            move._clear_approval_activities()
            move.message_post(body=_("CEO approval completed by %s.") % self.env.user.name)

    def action_reject_approval(self):
        self.ensure_one()

        if not self.env.context.get("approval_reject_reason"):
            return self._open_reject_wizard()

        if self.approval_state == "waiting_branch":
            self._ensure_branch_approver_user()
        elif self.approval_state == "waiting_ceo":
            self._ensure_ceo_approver_user()
        else:
            raise UserError(_("Only bills waiting for approval can be rejected."))

        reason = self.env.context.get("approval_reject_reason")
        self.write({
            "approval_state": "rejected",
            "approval_reject_reason": reason,
            "rejected_by": self.env.user.id,
            "rejected_on": fields.Datetime.now(),
        })
        self._clear_approval_activities()
        self.message_post(
            body=Markup(
                f"Approval rejected by {escape(self.env.user.name)}.<br/>"
                f"Reason: {escape(reason)}"
            )
        )
        return True

    def action_reset_approval(self):
        for move in self:
            move._clear_approval_activities()
            move.write({
                "branch_approved": False,
                "ceo_approved": False,
                "branch_approved_by": False,
                "branch_approved_on": False,
                "ceo_approved_by": False,
                "ceo_approved_on": False,
                "rejected_by": False,
                "rejected_on": False,
                "submitted_for_approval": False,
                "submitted_for_approval_on": False,
                "approval_state": "draft",
                "approval_reject_reason": False,
            })

    def write(self, vals):
        protected_approval_fields = {"approval_route"}
        protected_bill_fields = {
            "partner_id",
            "invoice_date",
            "invoice_date_due",
            "currency_id",
            "invoice_line_ids",
            "line_ids",
            "journal_id",
            "invoice_payment_term_id",
            "ref",
        }

        if not self.env.context.get("skip_bill_approval_write_check"):
            if protected_approval_fields.intersection(vals):
                locked = self.filtered(
                    lambda m: m.move_type == "in_invoice"
                    and m.submitted_for_approval
                    and m.approval_state in ("waiting_branch", "waiting_ceo", "approved")
                )
                if locked:
                    raise UserError(
                        _("You cannot change the approval route after submission.")
                    )

            if protected_bill_fields.intersection(vals):
                locked_bills = self.filtered(
                    lambda m: m.move_type == "in_invoice"
                    and m.approval_state in ("waiting_branch", "waiting_ceo")
                )
                if locked_bills:
                    raise UserError(
                        _("You cannot edit bill details while approval is in progress. Reset approval first.")
                    )

        return super().write(vals)

    def action_post(self):
        for move in self:
            if move.move_type == "in_invoice" and move.approval_route != "not_required":
                if move.approval_state != "approved":
                    raise UserError(_("This vendor bill must be approved before posting."))
        return super().action_post()