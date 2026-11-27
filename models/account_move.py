from contextvars import ContextVar
from functools import wraps

from odoo import _, api, fields, models, SUPERUSER_ID
from odoo.exceptions import AccessError, UserError
from odoo.osv import expression
from markupsafe import Markup, escape


APPROVAL_MOVE_TYPES = ("in_invoice", "in_refund", "out_invoice", "out_refund", "entry")
STANDARD_RESET_APPROVAL_STATES = (
    "waiting_branch",
    "waiting_ceo",
    "waiting_auditor",
    "approved",
    "rejected",
)
COMPLETED_RESET_APPROVAL_STATES = ("auditor_approved",)
CONFIG_PREFIX = "branch_bill_approval."

_APPROVAL_POSTING_MOVE_IDS = ContextVar(
    "branch_bill_approval_posting_move_ids",
    default=frozenset(),
)
_APPROVAL_RESETTING_DRAFT_MOVE_IDS = ContextVar(
    "branch_bill_approval_resetting_draft_move_ids",
    default=frozenset(),
)
_APPROVAL_ACTION_MOVE_IDS = ContextVar(
    "branch_bill_approval_action_move_ids",
    default=frozenset(),
)


def _approval_action_method(method):
    """Allow only the workflow action itself to perform technical mail/activity writes.

    The public write() guard below blocks approval-only users from editing
    accounting documents.  Approve/reject/reset actions still need to create
    chatter messages, clear/schedule activities, and let Odoo update related
    mail/activity technical fields on the same move.  A ContextVar is used
    instead of a context key so users cannot bypass the lock through crafted RPC
    contexts.
    """

    @wraps(method)
    def wrapper(self, *args, **kwargs):
        existing_move_ids = _APPROVAL_ACTION_MOVE_IDS.get()
        token = _APPROVAL_ACTION_MOVE_IDS.set(
            frozenset(set(existing_move_ids) | set(self.ids))
        )
        try:
            return method(self, *args, **kwargs)
        finally:
            _APPROVAL_ACTION_MOVE_IDS.reset(token)

    return wrapper


def _is_id_only_web_read(specification):
    """Return True when ``web_read`` only asks for record ids.

    Odoo 19's ``web_read`` uses this shape to load a many2one value (for
    example ``reversed_entry_id`` on a credit note): it reads the related
    record with an empty specification and then gets its ``display_name``
    with sudo.  In that case Odoo deliberately does not call ``read`` on the
    related model, so related documents the user cannot open still show by
    name.  The approval-only read guard must allow the same.
    """
    return not specification or list(specification) == ["id"]


# Fields that must only be changed by the workflow action methods.  UI readonly
# flags are not security controls, so direct RPC/import/write attempts are
# blocked in create()/write() and workflow actions update these fields through
# _write_approval_values(), which bypasses this model's public write guard.
APPROVER_SNAPSHOT_FIELDS = {
    "branch_approver_id",
    "ceo_approver_id",
    "auditor_approver_id",
}

APPROVAL_WORKFLOW_FIELDS = {
    "approval_state",
    "submitted_for_approval",
    "submitted_for_approval_on",
    "approval_submitted_by",
    "approval_pending_user_id",
    "approval_ready_to_post",
    "branch_approved",
    "branch_approved_by",
    "branch_approved_on",
    "ceo_approved",
    "ceo_approved_by",
    "ceo_approved_on",
    "auditor_forwarded_on",
    "auditor_approved",
    "auditor_approved_by",
    "auditor_approved_on",
    "auditor_rejected",
    "auditor_rejected_by",
    "auditor_rejected_on",
    "auditor_reject_reason",
    "rejected_by",
    "rejected_on",
    "approval_reject_reason",
}


class AccountMove(models.Model):
    _inherit = "account.move"

    approval_state = fields.Selection(
        [
            ("draft", "Draft"),
            ("waiting_branch", "Waiting Branch Approval"),
            ("waiting_ceo", "Waiting CEO Approval"),
            ("approved", "Approved"),
            ("waiting_auditor", "Waiting Auditor Approval"),
            ("auditor_approved", "Auditor Approved"),
            ("rejected", "Rejected"),
            ("not_required", "No Approval Required"),
        ],
        string="Approval Status",
        default="draft",
        tracking=True,
        copy=False,
        index=True,
    )

    approval_route = fields.Selection(
        [
            ("auditor", "Auditor Only"),
            ("ceo", "CEO Only"),
            ("branch_ceo", "Branch then CEO"),
            ("branch", "Branch Only"),
            ("not_required", "Not Required"),
        ],
        string="Approval Route",
        default="auditor",
        tracking=True,
        copy=False,
        index=True,
    )

    approval_badge_state = fields.Selection(
        [
            ("to_submit", "To Submit"),
            ("to_approval", "To Approval"),
            ("ready_to_post", "Ready to Post"),
            ("pending_audit", "Pending Audit"),
            ("audit_approved", "Audit Approved"),
            ("auditor_rejected", "Rejected by Auditor"),
            ("rejected", "Rejected"),
        ],
        string="Approval",
        compute="_compute_approval_badge_state",
    )

    branch_approver_id = fields.Many2one(
        "res.users",
        string="Branch Approver",
        readonly=True,
        copy=False,
        index=True,
        default=lambda self: self.env.company.branch_bill_approver_id,
        help="Branch approver snapshot used for this document. It is copied from the company when the document is submitted.",
    )

    ceo_approver_id = fields.Many2one(
        "res.users",
        string="CEO Approver",
        readonly=True,
        copy=False,
        index=True,
        default=lambda self: self.env.company.ceo_bill_approver_id,
        help="CEO approver snapshot used for this document. It is copied from the company when the document is submitted.",
    )

    auditor_approver_id = fields.Many2one(
        "res.users",
        string="Auditor User",
        readonly=True,
        copy=False,
        index=True,
        default=lambda self: self._default_auditor_approver(),
        help="Auditor snapshot used for this document. It is copied from Accounting Approval settings when the document is submitted.",
    )

    submitted_for_approval = fields.Boolean(copy=False)
    submitted_for_approval_on = fields.Datetime(copy=False)
    approval_submitted_by = fields.Many2one(
        "res.users",
        string="Submitted By",
        copy=False,
        readonly=True,
    )

    approval_pending_user_id = fields.Many2one(
        "res.users",
        string="Waiting For",
        compute="_compute_approval_pending_user",
        store=True,
        copy=False,
        readonly=True,
        index=True,
    )

    approval_ready_to_post = fields.Boolean(
        string="Approved and Ready to Post",
        compute="_compute_approval_ready_to_post",
        store=True,
        copy=False,
        index=True,
    )

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

    auditor_forwarded_on = fields.Datetime(
        string="Forwarded to Auditor On",
        copy=False,
    )
    auditor_approved = fields.Boolean(
        string="Auditor Approved",
        copy=False,
    )
    auditor_approved_by = fields.Many2one(
        "res.users",
        string="Auditor Approved By",
        copy=False,
    )
    auditor_approved_on = fields.Datetime(copy=False)
    auditor_rejected = fields.Boolean(
        string="Rejected by Auditor",
        copy=False,
        index=True,
    )
    auditor_rejected_by = fields.Many2one(
        "res.users",
        string="Auditor Rejected By",
        copy=False,
    )
    auditor_rejected_on = fields.Datetime(copy=False)
    auditor_reject_reason = fields.Text(
        string="Auditor Rejection Reason / Recommendation",
        copy=False,
    )

    rejected_by = fields.Many2one(
        "res.users",
        string="Rejected By",
        copy=False,
    )
    rejected_on = fields.Datetime(copy=False)
    approval_reject_reason = fields.Text(copy=False)

    is_branch_approver = fields.Boolean(compute="_compute_current_user_flags")
    is_ceo_approver = fields.Boolean(compute="_compute_current_user_flags")
    is_auditor_approver = fields.Boolean(compute="_compute_current_user_flags")
    can_submit_for_approval = fields.Boolean(compute="_compute_current_user_flags")
    can_branch_approve = fields.Boolean(compute="_compute_current_user_flags")
    can_ceo_approve = fields.Boolean(compute="_compute_current_user_flags")
    can_auditor_approve = fields.Boolean(compute="_compute_current_user_flags")
    can_auditor_reject = fields.Boolean(compute="_compute_current_user_flags")
    can_reject_approval = fields.Boolean(compute="_compute_current_user_flags")
    can_reset_approval = fields.Boolean(compute="_compute_current_user_flags")
    approval_readonly_mode = fields.Boolean(
        compute="_compute_current_user_flags",
        help="Technical field used by the form view to make accounting documents read-only for Branch Manager, CEO, and Auditor approval-only users.",
    )
    show_approval_readonly_journal_items = fields.Boolean(
        compute="_compute_current_user_flags",
        help="Shows the approval-only read-only Journal Items tab only for approvers who do not already have Odoo's standard Journal Items tab.",
    )

    @api.depends("approval_state", "branch_approver_id", "ceo_approver_id", "auditor_approver_id")
    def _compute_approval_pending_user(self):
        for move in self:
            if move.approval_state == "waiting_branch":
                move.approval_pending_user_id = move.branch_approver_id
            elif move.approval_state == "waiting_ceo":
                move.approval_pending_user_id = move.ceo_approver_id
            elif move.approval_state == "waiting_auditor":
                move.approval_pending_user_id = move.auditor_approver_id
            else:
                move.approval_pending_user_id = False

    @api.depends("approval_route", "approval_state", "state", "move_type")
    def _compute_approval_ready_to_post(self):
        for move in self:
            move.approval_ready_to_post = bool(
                move.move_type in move._get_approval_move_types()
                and move.approval_route != "not_required"
                and move.approval_state == "approved"
                and move.state == "draft"
            )

    @api.model
    def _get_approval_move_types(self):
        """Accounting move types covered by this approval workflow."""
        return APPROVAL_MOVE_TYPES

    def _is_automatic_accounting_entry(self):
        """Return True for system-generated journal entries that must not use this route.

        Manual journal entries are part of the approval workflow, but Odoo also
        stores payments, bank statement entries, exchange-difference entries, and
        cash-basis tax entries as ``account.move`` records with ``move_type ==
        'entry'``.  Those entries are generated by accounting workflows after an
        invoice/bill is already posted, so routing them through manual approval
        blocks payment registration and reconciliation.
        """
        self.ensure_one()
        if self.move_type != "entry":
            return False

        automatic_m2o_fields = (
            "origin_payment_id",
            "statement_line_id",
            "tax_cash_basis_rec_id",
            "tax_cash_basis_origin_move_id",
        )
        if any(
            field_name in self._fields and self[field_name]
            for field_name in automatic_m2o_fields
        ):
            return True

        automatic_o2m_fields = (
            "exchange_diff_partial_ids",
        )
        if any(
            field_name in self._fields and self[field_name]
            for field_name in automatic_o2m_fields
        ):
            return True

        return bool(
            self.env.context.get("is_payment")
            or self.env.context.get("skip_invoice_sync")
            or self.env.context.get("skip_account_move_synchronization")
        )

    def _is_approval_document(self):
        self.ensure_one()
        return bool(
            self.move_type in self._get_approval_move_types()
            and not self._is_automatic_accounting_entry()
        )

    def _write_approval_values(self, vals):
        """Write internal workflow values without exposing them to public write()."""
        return super(AccountMove, self).write(vals)

    def _is_internal_approval_action_write_allowed(self, locked_moves):
        """Allow technical writes generated inside validated workflow buttons only."""
        if not locked_moves:
            return False
        action_move_ids = _APPROVAL_ACTION_MOVE_IDS.get()
        return bool(action_move_ids and set(locked_moves.ids).issubset(action_move_ids))

    def _is_internal_posting_write_allowed(self, locked_moves):
        """Allow accounting writes generated by Odoo's own posting process.

        Approved draft documents are locked against user edits until they are
        posted, but account.move.action_post() legitimately updates accounting
        fields such as journal lines/date due while creating the posted entry.
        A ContextVar is used instead of a normal context key so users cannot
        bypass the edit lock by passing a crafted RPC context to write().
        """
        if not locked_moves:
            return False
        posting_move_ids = _APPROVAL_POSTING_MOVE_IDS.get()
        return bool(posting_move_ids and set(locked_moves.ids).issubset(posting_move_ids))

    def _is_internal_reset_to_draft_write_allowed(self, locked_moves):
        """Allow writes generated by a validated Reset to Draft operation only."""
        if not locked_moves:
            return False
        resetting_move_ids = _APPROVAL_RESETTING_DRAFT_MOVE_IDS.get()
        return bool(resetting_move_ids and set(locked_moves.ids).issubset(resetting_move_ids))

    def _is_auditor_rejection_reset_write_allowed(self, locked_moves):
        """Allow Reset to Draft writes generated by the Auditor rejection flow."""
        return bool(
            locked_moves
            and self.env.context.get("allow_auditor_rejection_reset")
            and all(
                move._is_approval_document()
                and move.state == "posted"
                and move.approval_state == "waiting_auditor"
                and (
                    self.env.su
                    or self.env.user.id == SUPERUSER_ID
                    or move.auditor_approver_id.id == self.env.user.id
                )
                for move in locked_moves
            )
        )

    def _current_user_can_bypass_approval(self):
        user = self.env.user
        return bool(
            self.env.su
            or user.id == SUPERUSER_ID
            or user.has_group("branch_bill_approval.group_bill_approval_admin")
            or user.has_group("account.group_account_manager")
        )

    @api.model
    def _approval_config_bool(self, key, default=False):
        """Read a boolean setting for this module from ir.config_parameter."""
        value = self.env["ir.config_parameter"].sudo().get_param(
            f"{CONFIG_PREFIX}{key}", default=None
        )
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "y", "on")

    @api.model
    def _approval_config_user(self, key):
        value = self.env["ir.config_parameter"].sudo().get_param(
            f"{CONFIG_PREFIX}{key}", default=None
        )
        try:
            user_id = int(value or 0)
        except (TypeError, ValueError):
            user_id = 0
        if not user_id:
            return self.env["res.users"]
        return self.env["res.users"].browse(user_id).exists()

    @api.model
    def _approval_configured_auditor(self, company=None):
        """Return the globally configured Auditor, falling back to the legacy company field."""
        auditor = self._approval_config_user("auditor_user_id")
        if auditor:
            return auditor
        company = company or self.env.company
        return company.account_approval_auditor_id if company else self.env["res.users"]

    @api.model
    def _default_auditor_approver(self):
        return self._approval_configured_auditor(self.env.company)

    def _current_user_is_approval_only_user(self):
        """Users that can approve/reject but must not manually edit accounting documents.

        Odoo's basic Invoicing permission is sometimes assigned only so the user
        can open invoice/bill forms.  It must not turn a Branch Manager, CEO, or
        Auditor into an editor.  Only our accountant/admin groups and Accounting
        Managers bypass the approval-only edit lock.
        """
        user = self.env.user
        if self.env.su or user.id == SUPERUSER_ID:
            return False
        if (
            user.has_group("branch_bill_approval.group_bill_approval_admin")
            or user.has_group("branch_bill_approval.group_invoice_bill_accountant")
            or user.has_group("account.group_account_manager")
        ):
            return False
        return bool(
            user.has_group("branch_bill_approval.group_branch_bill_approver")
            or user.has_group("branch_bill_approval.group_ceo_bill_approver")
            or user.has_group("branch_bill_approval.group_bill_approval_auditor")
        )

    def _current_user_has_standard_journal_items_tab(self):
        """Return True when Odoo already gives the user the native Journal Items tab.

        Approval users need a custom read-only Journal Items tab when they only
        have lightweight approval/invoicing access.  Bookkeepers and Accounting
        Administrators already receive Odoo's native Journal Items tab, so the
        custom tab must stay hidden for them to avoid a duplicate tab.
        """
        user = self.env.user
        if self.env.su or user.id == SUPERUSER_ID:
            return True
        for group_xmlid in (
            "account.group_account_user",
            "account.group_account_readonly",
            "account.group_account_manager",
        ):
            try:
                if user.has_group(group_xmlid):
                    return True
            except Exception:
                # Keep the module compatible with Odoo builds where one of the
                # optional accounting group XML IDs is not present.
                continue
        return False

    def _current_user_is_reset_owner(self):
        self.ensure_one()
        user = self.env.user
        return bool(
            user
            and (
                self.create_uid.id == user.id
                or self.approval_submitted_by.id == user.id
            )
        )

    def _current_user_is_approval_participant(self):
        self.ensure_one()
        user = self.env.user
        return bool(
            self._current_user_is_reset_owner()
            or self.approval_pending_user_id.id == user.id
            or self.branch_approved_by.id == user.id
            or self.ceo_approved_by.id == user.id
            or self.auditor_approved_by.id == user.id
            or self.rejected_by.id == user.id
            or self.auditor_rejected_by.id == user.id
        )

    @api.model
    def _approval_only_move_visibility_domain(self, user=None, prefix=""):
        """Return the exact accounting documents an approval-only user may read.

        This domain is intentionally applied in Python in addition to record
        rules.  Some installations give Branch Managers/CEOs/Auditors the
        standard Invoicing group so they can open invoice forms.  Odoo combines
        group record rules with OR logic, so a standard Accounting/Invoicing
        rule can otherwise make every bill/invoice visible.  This extra domain
        keeps approval-only users limited to documents where they are the
        current pending approver, a previous approver/rejecter, or the request
        owner.  Snapshot approver fields alone are intentionally not enough,
        because those defaults exist on draft/unsubmitted bills and would expose
        every new bill to the configured Branch Manager/CEO/Auditor.
        """
        user = user or self.env.user
        field = lambda name: f"{prefix}{name}"
        participant_domain = expression.OR([
            [(field("approval_pending_user_id"), "=", user.id)],
            [(field("branch_approved_by"), "=", user.id)],
            [(field("ceo_approved_by"), "=", user.id)],
            [(field("auditor_approved_by"), "=", user.id)],
            [(field("rejected_by"), "=", user.id)],
            [(field("auditor_rejected_by"), "=", user.id)],
            [(field("create_uid"), "=", user.id)],
            [(field("approval_submitted_by"), "=", user.id)],
        ])
        return expression.AND([
            [(field("move_type"), "in", list(APPROVAL_MOVE_TYPES))],
            participant_domain,
        ])

    @api.model
    def _apply_approval_only_move_visibility_domain(self, domain):
        if self.env.context.get("skip_approval_only_visibility_domain"):
            return domain
        if not self._current_user_is_approval_only_user():
            return domain
        return expression.AND([
            domain or [],
            self._approval_only_move_visibility_domain(user=self.env.user),
        ])

    def _approval_only_move_visible_to_user(self, user):
        self.ensure_one()
        return bool(
            self.move_type in self._get_approval_move_types()
            and (
                self.approval_pending_user_id.id == user.id
                or self.branch_approved_by.id == user.id
                or self.ceo_approved_by.id == user.id
                or self.auditor_approved_by.id == user.id
                or self.rejected_by.id == user.id
                or self.auditor_rejected_by.id == user.id
                or self.create_uid.id == user.id
                or self.approval_submitted_by.id == user.id
            )
        )

    def _check_approval_only_move_read_access(self):
        if (
            not self
            or self.env.context.get("skip_approval_only_visibility_domain")
            or not self._current_user_is_approval_only_user()
        ):
            return
        user = self.env.user
        forbidden = self.sudo().filtered(
            lambda move: not move._approval_only_move_visible_to_user(user)
        )
        if forbidden:
            raise AccessError(
                _(
                    "You can only view bills, invoices, and journal entries assigned to you in the accounting approval workflow."
                )
            )

    @api.model
    def _search(self, domain, *args, **kwargs):
        domain = self._apply_approval_only_move_visibility_domain(domain)
        return super()._search(domain, *args, **kwargs)

    def read(self, fields=None, load="_classic_read"):
        self._check_approval_only_move_read_access()
        return super().read(fields=fields, load=load)

    def web_read(self, specification):
        if not _is_id_only_web_read(specification):
            self._check_approval_only_move_read_access()
        return super().web_read(specification)

    def _is_completed_approval_route(self):
        self.ensure_one()
        return bool(
            self._is_approval_document()
            and self.submitted_for_approval
            and (
                self.approval_state in COMPLETED_RESET_APPROVAL_STATES
                or (self.state == "posted" and self.approval_state == "approved")
            )
        )

    def _approval_reset_state_allowed(self):
        self.ensure_one()
        if not self._is_approval_document() or not self.submitted_for_approval:
            return False
        if self.state == "draft" and self.approval_state in STANDARD_RESET_APPROVAL_STATES:
            return True
        if self._is_completed_approval_route():
            return self._approval_config_bool("allow_reset_after_completion", default=False)
        return False

    def _current_user_can_reset_approval(self):
        self.ensure_one()
        if self.env.su:
            return True
        user = self.env.user
        if (
            user.has_group("branch_bill_approval.group_bill_approval_admin")
            or user.has_group("account.group_account_manager")
        ):
            return self._approval_reset_state_allowed()
        if not self._approval_reset_state_allowed():
            return False
        if self._approval_config_bool("reset_only_submitter", default=True):
            return self._current_user_is_reset_owner()
        return self._current_user_is_approval_participant()

    @api.onchange("company_id")
    def _onchange_company_id_approval_approvers(self):
        for move in self:
            if move.submitted_for_approval:
                continue
            company = move.company_id or self.env.company
            move.branch_approver_id = company.branch_bill_approver_id
            move.ceo_approver_id = company.ceo_bill_approver_id
            move.auditor_approver_id = move._approval_configured_auditor(company)

    def _snapshot_company_approvers(self):
        """Freeze the company approvers on the document at submission time."""
        for move in self:
            company = move.company_id or self.env.company
            move._write_approval_values({
                "branch_approver_id": company.branch_bill_approver_id.id or False,
                "ceo_approver_id": company.ceo_bill_approver_id.id or False,
                "auditor_approver_id": move._approval_configured_auditor(company).id or False,
            })

    def _approval_document_label(self):
        """Lower-case label used inside sentences."""
        self.ensure_one()
        labels = {
            "in_invoice": _("vendor bill"),
            "in_refund": _("vendor credit note"),
            "out_invoice": _("customer invoice"),
            "out_refund": _("customer credit note"),
            "entry": _("journal entry"),
        }
        return labels.get(self.move_type, _("accounting document"))

    def _approval_document_title(self):
        """Title-case label used in button/activity/chatter text."""
        self.ensure_one()
        labels = {
            "in_invoice": _("Vendor Bill"),
            "in_refund": _("Vendor Credit Note"),
            "out_invoice": _("Customer Invoice"),
            "out_refund": _("Customer Credit Note"),
            "entry": _("Journal Entry"),
        }
        return labels.get(self.move_type, _("Accounting Document"))

    @api.model
    def _approval_redirect_action(self):
        return {
            "type": "ir.actions.act_window",
            "name": _("Accounting Documents"),
            "res_model": "account.move",
            "view_mode": "list,form",
            "target": "current",
            "domain": [("move_type", "in", list(APPROVAL_MOVE_TYPES))],
        }

    def _approval_request_user(self):
        self.ensure_one()
        return self.approval_submitted_by or self.create_uid

    def _approval_request_partner_ids(self):
        self.ensure_one()
        request_user = self._approval_request_user()
        if request_user and request_user.partner_id:
            return [request_user.partner_id.id]
        return []

    def _current_user_is_approval_request_owner(self):
        self.ensure_one()
        user = self.env.user
        return bool(
            user
            and (
                self.create_uid.id == user.id
                or self.approval_submitted_by.id == user.id
            )
        )

    def _is_auditor_approval_required(self):
        self.ensure_one()
        return bool(
            self._is_approval_document()
            and self.state == "posted"
            and self._approval_config_bool("require_final_auditor_review", default=True)
            and self.approval_route not in ("not_required", "auditor")
            and self.auditor_approver_id
            and self.approval_state == "approved"
        )

    def name_get(self):
        result_map = dict(super().name_get())
        result = []
        for move in self:
            if move._is_approval_document():
                number = move.name or move.ref or _("Draft")
                partner = move.partner_id.name or ""
                label = _("%s - %s") % (move._approval_document_title(), number)
                if partner:
                    label = _("%s - %s") % (label, partner)
                result.append((move.id, label))
            else:
                result.append((move.id, result_map.get(move.id, move.name or "/")))
        return result

    @api.depends("move_type", "approval_route", "approval_state", "state", "submitted_for_approval", "auditor_rejected")
    def _compute_approval_badge_state(self):
        for move in self:
            if not move._is_approval_document():
                move.approval_badge_state = False
            elif move.auditor_rejected and move.state == "draft":
                move.approval_badge_state = "auditor_rejected"
            elif move.approval_state == "waiting_auditor":
                move.approval_badge_state = "pending_audit"
            elif move.approval_state == "auditor_approved":
                move.approval_badge_state = "audit_approved"
            elif move.approval_route == "not_required":
                move.approval_badge_state = False
            elif move.approval_state in ("waiting_branch", "waiting_ceo"):
                move.approval_badge_state = "to_approval"
            elif move.approval_state == "approved" and move.state == "draft":
                move.approval_badge_state = "ready_to_post"
            elif move.approval_state == "rejected":
                move.approval_badge_state = "rejected"
            elif move.state == "draft" and not move.submitted_for_approval:
                move.approval_badge_state = "to_submit"
            else:
                move.approval_badge_state = False

    @api.depends_context("uid")
    def _compute_current_user_flags(self):
        user = self.env.user
        user_has_standard_journal_items_tab = self._current_user_has_standard_journal_items_tab()
        for move in self:
            is_approval_document = move._is_approval_document()
            move.is_branch_approver = bool(
                move.branch_approver_id and move.branch_approver_id.id == user.id
            )
            move.is_ceo_approver = bool(
                move.ceo_approver_id and move.ceo_approver_id.id == user.id
            )
            move.is_auditor_approver = bool(
                move.auditor_approver_id and move.auditor_approver_id.id == user.id
            )
            move.can_submit_for_approval = bool(
                is_approval_document
                and move.state == "draft"
                and not move.submitted_for_approval
                and move.approval_route != "not_required"
            )
            move.can_branch_approve = bool(
                is_approval_document
                and move.approval_state == "waiting_branch"
                and move.is_branch_approver
            )
            move.can_ceo_approve = bool(
                is_approval_document
                and move.approval_state == "waiting_ceo"
                and move.is_ceo_approver
            )
            move.can_auditor_approve = bool(
                is_approval_document
                and move.approval_state == "waiting_auditor"
                and move.is_auditor_approver
                and (
                    (move.approval_route == "auditor" and move.state == "draft")
                    or (move.approval_route != "auditor" and move.state == "posted")
                )
            )
            move.can_auditor_reject = move.can_auditor_approve
            move.can_reject_approval = bool(
                move.can_branch_approve or move.can_ceo_approve or move.can_auditor_reject
            )
            move.can_reset_approval = bool(
                is_approval_document
                and move._current_user_can_reset_approval()
            )
            is_approval_only_user = move._current_user_is_approval_only_user()
            move.approval_readonly_mode = bool(
                is_approval_document
                and is_approval_only_user
            )
            move.show_approval_readonly_journal_items = bool(
                is_approval_document
                and is_approval_only_user
                and not user_has_standard_journal_items_tab
            )

    def _check_approval_document(self):
        for move in self:
            if not move._is_approval_document():
                raise UserError(
                    _(
                        "This workflow only applies to vendor bills, vendor credit notes, customer invoices, customer credit notes, and journal entries."
                    )
                )

    def _check_vendor_bill(self):
        # Backward-compatible alias for any external custom code that may call the old method.
        return self._check_approval_document()

    def _validate_route_approvers(self):
        for move in self:
            document = move._approval_document_label()
            if move.approval_route in ("branch", "branch_ceo") and not move.branch_approver_id:
                raise UserError(
                    _(
                        "Please set a Branch Approver on the company before submitting this %s."
                    )
                    % document
                )
            if move.approval_route in ("ceo", "branch_ceo") and not move.ceo_approver_id:
                raise UserError(
                    _(
                        "Please set a CEO Approver on the company before submitting this %s."
                    )
                    % document
                )
            if move.approval_route == "auditor" and not move.auditor_approver_id:
                raise UserError(
                    _(
                        "Please set an Auditor User in Accounting Approval settings before submitting this %s."
                    )
                    % document
                )

    def _compute_initial_approval_state(self):
        self.ensure_one()
        if self.approval_route == "not_required":
            return "not_required"
        if self.approval_route == "auditor":
            return "waiting_auditor"
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
            raise AccessError(
                _("Only the configured Branch Approver can approve this %s.")
                % self._approval_document_label()
            )

    def _ensure_ceo_approver_user(self):
        self.ensure_one()
        if self.env.su:
            return
        if not self.ceo_approver_id or self.env.user.id != self.ceo_approver_id.id:
            raise AccessError(
                _("Only the configured CEO Approver can approve this %s.")
                % self._approval_document_label()
            )

    def _ensure_auditor_approver_user(self):
        self.ensure_one()
        if self.env.su:
            return
        if not self.auditor_approver_id or self.env.user.id != self.auditor_approver_id.id:
            raise AccessError(
                _("Only the configured Auditor User can approve or reject this %s.")
                % self._approval_document_label()
            )

    def _approval_activity_message(self, stage):
        self.ensure_one()
        document_title = self._approval_document_title()
        document_label = self._approval_document_label()
        document_number = self.name or self.ref or _("Draft")

        if stage == "branch":
            return {
                "summary": _("%s needs Branch approval") % document_title,
                "note": _("Please review and approve this %s: %s.")
                % (document_label, document_number),
            }

        if stage == "ceo":
            return {
                "summary": _("%s needs CEO approval") % document_title,
                "note": _("Please review and approve this %s: %s.")
                % (document_label, document_number),
            }

        if stage == "auditor":
            return {
                "summary": _("%s needs Auditor approval") % document_title,
                "note": _("Please review and approve this %s: %s.")
                % (document_label, document_number),
            }

        if stage == "post":
            return {
                "summary": _("%s approved - ready to post") % document_title,
                "note": _(
                    "Approval is complete for this %s: %s. Please review and post it."
                ) % (document_label, document_number),
            }

        if stage == "rejected":
            return {
                "summary": _("%s approval rejected") % document_title,
                "note": _(
                    "Please review the rejection reason and update this %s: %s."
                ) % (document_label, document_number),
            }

        if stage == "auditor_rejected":
            return {
                "summary": _("%s rejected by Auditor") % document_title,
                "note": _(
                    "Please review the auditor recommendation and update this %s: %s."
                ) % (document_label, document_number),
            }

        return {
            "summary": _("Accounting document approval"),
            "note": _("Please review this %s: %s.") % (document_label, document_number),
        }

    def _approval_activity_summaries(self, stages=None):
        self.ensure_one()
        stages = set(stages or ("branch", "ceo", "auditor", "post", "rejected", "auditor_rejected", "generic"))
        summaries = []
        if "branch" in stages:
            summaries.append(self._approval_activity_message("branch")["summary"])
        if "ceo" in stages:
            summaries.append(self._approval_activity_message("ceo")["summary"])
        if "auditor" in stages:
            summaries.append(self._approval_activity_message("auditor")["summary"])
        if "post" in stages:
            summaries.append(self._approval_activity_message("post")["summary"])
        if "rejected" in stages:
            summaries.append(self._approval_activity_message("rejected")["summary"])
        if "auditor_rejected" in stages:
            summaries.append(self._approval_activity_message("auditor_rejected")["summary"])
        if "generic" in stages:
            summaries.append(_("Accounting document approval"))
        return summaries

    def _clear_approval_activities(self, stages=None):
        """Remove only activities created by this approval workflow."""
        todo = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        if not todo or not self.ids:
            return
        activities = self.env["mail.activity"].sudo().search([
            ("res_model", "=", "account.move"),
            ("res_id", "in", self.ids),
            ("activity_type_id", "=", todo.id),
        ])
        if not activities:
            return

        moves_by_id = {move.id: move for move in self}
        activities_to_unlink = self.env["mail.activity"]
        for activity in activities:
            move = moves_by_id.get(activity.res_id)
            if move and activity.summary in move._approval_activity_summaries(stages=stages):
                activities_to_unlink |= activity
        if activities_to_unlink:
            activities_to_unlink.sudo().unlink()

    def _schedule_approval_activity(self, user, stage):
        self.ensure_one()
        if not user:
            return
        self._clear_approval_activities(stages=("branch", "ceo", "auditor"))
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

    def _schedule_submitter_activity(self, stage):
        self.ensure_one()
        request_user = self._approval_request_user()
        if not request_user:
            return
        activity_type = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        if not activity_type:
            return
        message = self._approval_activity_message(stage)
        self.activity_schedule(
            activity_type_id=activity_type.id,
            user_id=request_user.id,
            summary=message["summary"],
            note=message["note"],
        )

    def _notify_submitter_ready_to_post(self):
        for move in self:
            move._clear_approval_activities(stages=("branch", "ceo", "auditor", "post"))
            document_title = move._approval_document_title()
            document_number = move.name or move.ref or _("Draft")
            move.message_post(
                body=_(
                    "%s approval is complete for %s. The document is ready to post."
                ) % (document_title, document_number),
                partner_ids=move._approval_request_partner_ids(),
            )
            move._schedule_submitter_activity("post")

    def _notify_submitter_rejected(self, stage="rejected"):
        for move in self:
            move._clear_approval_activities(stages=(stage,))
            move._schedule_submitter_activity(stage)

    def _open_reject_wizard(self):
        self.ensure_one()
        if not self.can_reject_approval:
            raise AccessError(_("You are not allowed to reject this document."))
        return {
            "type": "ir.actions.act_window",
            "name": _(
                "Reject Auditor Approval"
                if self.approval_state == "waiting_auditor"
                else "Reject Approval"
            ),
            "res_model": "approval.reject.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_move_id": self.id,
            },
        }

    def action_submit_for_approval(self):
        for move in self:
            move._check_approval_document()
            document = move._approval_document_label()
            document_title = move._approval_document_title()

            if move.state != "draft":
                raise UserError(_("Only draft %s can be submitted for approval.") % document)

            if move.approval_route == "not_required":
                raise UserError(
                    _(
                        "%s with 'Not Required' approval route do not need submission for approval."
                    )
                    % document_title
                )

            if move.submitted_for_approval:
                raise UserError(
                    _(
                        "This %s has already been submitted. Reset approval before submitting it again."
                    )
                    % document
                )

            move._snapshot_company_approvers()
            move._validate_route_approvers()
            move._reset_approval_fields(keep_approvers=True)

            initial_approval_state = move._compute_initial_approval_state()
            branch_approver = move.branch_approver_id
            ceo_approver = move.ceo_approver_id
            auditor_approver = move.auditor_approver_id

            move.message_post(
                body=_("%s submitted for approval by %s.")
                % (document_title, self.env.user.name)
            )

            move._write_approval_values({
                "approval_state": initial_approval_state,
                "submitted_for_approval": True,
                "submitted_for_approval_on": fields.Datetime.now(),
                "approval_submitted_by": self.env.user.id,
                "approval_reject_reason": False,
                "rejected_by": False,
                "rejected_on": False,
            })

            if initial_approval_state == "waiting_branch":
                move._schedule_approval_activity(branch_approver, "branch")
            elif initial_approval_state == "waiting_ceo":
                move.sudo()._schedule_approval_activity(ceo_approver, "ceo")
            elif initial_approval_state == "waiting_auditor":
                move.sudo()._schedule_approval_activity(auditor_approver, "auditor")

        return True

    @_approval_action_method
    def action_branch_approve(self):
        redirect_after_hide = False
        for move in self:
            move._check_approval_document()
            document = move._approval_document_label()

            if move.approval_state != "waiting_branch":
                raise UserError(_("This %s is not waiting for branch approval.") % document)

            move._ensure_branch_approver_user()

            move._write_approval_values({
                "branch_approved": True,
                "branch_approved_by": self.env.user.id,
                "branch_approved_on": fields.Datetime.now(),
            })
            move.message_post(
                body=_("Branch approval completed by %s.") % self.env.user.name
            )
            move._clear_approval_activities()

            if move.approval_route == "branch_ceo":
                if not move.ceo_approver_id:
                    raise UserError(
                        _(
                            "A CEO Approver must be configured on the company before this %s can continue."
                        )
                        % document
                    )
                ceo_approver = move.ceo_approver_id
                redirect_after_hide = redirect_after_hide or bool(
                    not self.env.su
                    and move.branch_approver_id
                    and move.branch_approver_id.id == self.env.user.id
                    and (not ceo_approver or ceo_approver.id != self.env.user.id)
                    and not move._current_user_is_approval_request_owner()
                )
                move._write_approval_values({"approval_state": "waiting_ceo"})
                # Once the move is waiting for CEO approval, a branch approver may no
                # longer have read access. Use sudo only for the technical activity setup.
                move.sudo()._schedule_approval_activity(ceo_approver, "ceo")
            else:
                move._write_approval_values({"approval_state": "approved"})
                move._notify_submitter_ready_to_post()

        if redirect_after_hide:
            return self._approval_redirect_action()
        return True

    @_approval_action_method
    def action_ceo_approve(self):
        for move in self:
            move._check_approval_document()
            document = move._approval_document_label()

            if move.approval_state != "waiting_ceo":
                raise UserError(_("This %s is not waiting for CEO approval.") % document)

            move._ensure_ceo_approver_user()

            move._write_approval_values({
                "ceo_approved": True,
                "ceo_approved_by": self.env.user.id,
                "ceo_approved_on": fields.Datetime.now(),
                "approval_state": "approved",
            })
            move.message_post(body=_("CEO approval completed by %s.") % self.env.user.name)
            move._notify_submitter_ready_to_post()

    @_approval_action_method
    def action_reject_approval(self):
        self.ensure_one()

        if not self.env.context.get("approval_reject_reason"):
            return self._open_reject_wizard()

        reason = self.env.context.get("approval_reject_reason")

        if self.approval_state == "waiting_branch":
            self._ensure_branch_approver_user()
        elif self.approval_state == "waiting_ceo":
            self._ensure_ceo_approver_user()
        elif self.approval_state == "waiting_auditor":
            self._ensure_auditor_approver_user()
            return self._reject_auditor_approval(reason)
        else:
            raise UserError(_("Only documents waiting for approval can be rejected."))

        self._write_approval_values({
            "approval_state": "rejected",
            "approval_reject_reason": reason,
            "rejected_by": self.env.user.id,
            "rejected_on": fields.Datetime.now(),
        })
        self._clear_approval_activities(stages=("branch", "ceo"))
        self.message_post(
            body=Markup(
                f"Approval rejected by {escape(self.env.user.name)}.<br/>"
                f"Reason: {escape(reason)}"
            ),
            partner_ids=self._approval_request_partner_ids(),
        )
        self._notify_submitter_rejected()
        return True

    @_approval_action_method
    def action_auditor_approve(self):
        for move in self:
            move._check_approval_document()
            if move.approval_state != "waiting_auditor":
                raise UserError(_("This %s is not waiting for Auditor approval.") % move._approval_document_label())

            move._ensure_auditor_approver_user()

            # Auditor-only route: the Auditor is the pre-posting approver for any
            # supported accounting document type.
            if move.approval_route == "auditor" and move.state == "draft":
                move._write_approval_values({
                    "approval_state": "approved",
                    "auditor_approved": True,
                    "auditor_approved_by": self.env.user.id,
                    "auditor_approved_on": fields.Datetime.now(),
                    "auditor_rejected": False,
                    "auditor_rejected_by": False,
                    "auditor_rejected_on": False,
                    "auditor_reject_reason": False,
                })
                move._clear_approval_activities(stages=("auditor",))
                move.message_post(
                    body=_("Auditor approval completed by %s.") % self.env.user.name,
                    partner_ids=move._approval_request_partner_ids(),
                )
                move._notify_submitter_ready_to_post()
                continue

            # Final audit stage: after non-auditor routes, posted accounting
            # documents are forwarded to the Auditor for the final review.
            if move.approval_route == "auditor" or move.state != "posted":
                raise UserError(_("Only posted accounting documents can receive final Auditor approval."))

            move._write_approval_values({
                "approval_state": "auditor_approved",
                "auditor_approved": True,
                "auditor_approved_by": self.env.user.id,
                "auditor_approved_on": fields.Datetime.now(),
                "auditor_rejected": False,
                "auditor_rejected_by": False,
                "auditor_rejected_on": False,
                "auditor_reject_reason": False,
            })
            move._clear_approval_activities(stages=("auditor",))
            move.message_post(
                body=_("Auditor Approved by %s") % self.env.user.name,
                partner_ids=move._approval_request_partner_ids(),
            )
        return True

    def _reject_auditor_approval(self, reason):
        self.ensure_one()
        self._ensure_auditor_approver_user()
        request_user = self._approval_request_user()
        request_partner_ids = self._approval_request_partner_ids()
        self._clear_approval_activities(stages=("auditor",))

        if self.approval_route == "auditor" and self.state == "draft":
            self._write_approval_values({
                "approval_state": "rejected",
                "approval_reject_reason": reason,
                "rejected_by": self.env.user.id,
                "rejected_on": fields.Datetime.now(),
                "auditor_approved": False,
                "auditor_approved_by": False,
                "auditor_approved_on": False,
                "auditor_rejected": True,
                "auditor_rejected_by": self.env.user.id,
                "auditor_rejected_on": fields.Datetime.now(),
                "auditor_reject_reason": reason,
            })
            self.message_post(
                body=Markup(
                    f"Auditor Rejected by {escape(self.env.user.name)}.<br/>"
                    f"Reason / Recommendation: {escape(reason)}"
                ),
                partner_ids=request_partner_ids,
            )
            self._notify_submitter_rejected(stage="auditor_rejected")
            return True

        if self.approval_route == "auditor" or self.state != "posted":
            raise UserError(_("Only Auditor-only draft documents or posted accounting documents can be rejected by the Auditor."))

        self.with_context(
            allow_auditor_rejection_reset=True,
        ).button_draft()

        self._write_approval_values({
            "approval_state": "draft",
            "submitted_for_approval": False,
            "submitted_for_approval_on": False,
            "approval_submitted_by": request_user.id if request_user else False,
            "branch_approved": False,
            "branch_approved_by": False,
            "branch_approved_on": False,
            "ceo_approved": False,
            "ceo_approved_by": False,
            "ceo_approved_on": False,
            "approval_reject_reason": False,
            "rejected_by": False,
            "rejected_on": False,
            "auditor_approved": False,
            "auditor_approved_by": False,
            "auditor_approved_on": False,
            "auditor_rejected": True,
            "auditor_rejected_by": self.env.user.id,
            "auditor_rejected_on": fields.Datetime.now(),
            "auditor_reject_reason": reason,
        })
        self.message_post(
            body=Markup(
                f"Auditor Rejected by {escape(self.env.user.name)}.<br/>"
                f"Reason / Recommendation: {escape(reason)}"
            ),
            partner_ids=request_partner_ids,
        )
        self._notify_submitter_rejected(stage="auditor_rejected")
        return True

    def _reset_approval_fields(self, keep_approvers=False):
        for move in self:
            move._clear_approval_activities()
            vals = {
                "branch_approved": False,
                "ceo_approved": False,
                "branch_approved_by": False,
                "branch_approved_on": False,
                "ceo_approved_by": False,
                "ceo_approved_on": False,
                "auditor_forwarded_on": False,
                "auditor_approved": False,
                "auditor_approved_by": False,
                "auditor_approved_on": False,
                "auditor_rejected": False,
                "auditor_rejected_by": False,
                "auditor_rejected_on": False,
                "auditor_reject_reason": False,
                "rejected_by": False,
                "rejected_on": False,
                "submitted_for_approval": False,
                "submitted_for_approval_on": False,
                "approval_submitted_by": False,
                "approval_state": "draft",
                "approval_reject_reason": False,
            }
            if not keep_approvers:
                vals.update({
                    "branch_approver_id": False,
                    "ceo_approver_id": False,
                    "auditor_approver_id": False,
                })
            move._write_approval_values(vals)

    @_approval_action_method
    def action_reset_approval(self):
        for move in self:
            if not move._current_user_can_reset_approval():
                raise AccessError(
                    _("You are not allowed to reset the approval of this document.")
                )
            if move.state == "posted":
                if not move._is_completed_approval_route():
                    raise UserError(
                        _("Only completed approval routes can be reset after posting.")
                    )
                move.with_context(skip_approval_reset_on_button_draft=True).button_draft()
        self._reset_approval_fields()
        return True

    def _mark_automatic_entry_approval_not_required(self):
        automatic_moves = self.filtered(lambda move: move._is_automatic_accounting_entry())
        if automatic_moves:
            automatic_moves._clear_approval_activities()
            automatic_moves._write_approval_values({
                "approval_route": "not_required",
                "approval_state": "not_required",
                "submitted_for_approval": False,
                "submitted_for_approval_on": False,
                "approval_submitted_by": False,
                "approval_reject_reason": False,
                "rejected_by": False,
                "rejected_on": False,
            })

    @api.model_create_multi
    def create(self, vals_list):
        sanitized_vals_list = []
        for vals in vals_list:
            clean_vals = vals.copy()
            for field_name in APPROVAL_WORKFLOW_FIELDS:
                clean_vals.pop(field_name, None)
            sanitized_vals_list.append(clean_vals)
        moves = super().create(sanitized_vals_list)
        moves._mark_automatic_entry_approval_not_required()
        return moves

    def write(self, vals):
        protected_approval_fields = {"approval_route"}
        protected_move_fields = {
            "partner_id",
            "date",
            "invoice_date",
            "invoice_date_due",
            "currency_id",
            "invoice_line_ids",
            "line_ids",
            "journal_id",
            "invoice_payment_term_id",
            "ref",
        }

        workflow_fields = APPROVAL_WORKFLOW_FIELDS.intersection(vals)
        if workflow_fields:
            raise AccessError(
                _(
                    "Approval workflow fields can only be changed by the approval action buttons."
                )
            )

        approver_snapshot_fields = APPROVER_SNAPSHOT_FIELDS.intersection(vals)
        if approver_snapshot_fields:
            locked_approver_records = self.filtered(
                lambda m: m._is_approval_document() and m.submitted_for_approval
            )
            if locked_approver_records:
                raise AccessError(
                    _(
                        "Approver snapshots cannot be changed after submission. Reset approval first."
                    )
                )

        approval_only_documents = self.filtered(lambda m: m._is_approval_document())
        if (
            approval_only_documents
            and self._current_user_is_approval_only_user()
            and not self._is_internal_approval_action_write_allowed(approval_only_documents)
            and not self._is_internal_reset_to_draft_write_allowed(approval_only_documents)
            and not self._is_auditor_rejection_reset_write_allowed(approval_only_documents)
        ):
            raise AccessError(
                _(
                    "Branch Managers, CEOs, and Auditors can approve, reject, or reset approval only. They cannot edit accounting documents."
                )
            )

        if vals.get("approval_route") == "not_required" and not self._current_user_can_bypass_approval():
            approval_documents = self.filtered(lambda m: m._is_approval_document())
            if approval_documents:
                raise AccessError(
                    _(
                        "Only Accounting Approval Admins or Accounting Managers can select the 'Not Required' approval route."
                    )
                )

        if protected_approval_fields.intersection(vals):
            locked = self.filtered(
                lambda m: m._is_approval_document()
                and m.submitted_for_approval
                and m.approval_state in (
                    "waiting_branch",
                    "waiting_ceo",
                    "waiting_auditor",
                    "approved",
                    "auditor_approved",
                )
            )
            if locked:
                raise UserError(
                    _("You cannot change the approval route after submission.")
                )

        if protected_move_fields.intersection(vals):
            locked_moves = self.filtered(
                lambda m: m._is_approval_document()
                and m.submitted_for_approval
                and m.approval_state in (
                    "waiting_branch",
                    "waiting_ceo",
                    "waiting_auditor",
                    "approved",
                )
            )
            allow_auditor_rejection_reset_write = self._is_auditor_rejection_reset_write_allowed(locked_moves)
            allow_internal_posting_write = self._is_internal_posting_write_allowed(locked_moves)
            allow_internal_reset_to_draft_write = self._is_internal_reset_to_draft_write_allowed(locked_moves)
            if locked_moves and not (
                allow_auditor_rejection_reset_write
                or allow_internal_posting_write
                or allow_internal_reset_to_draft_write
            ):
                raise UserError(
                    _(
                        "You cannot edit document details after submission or approval. Reset approval first."
                    )
                )

        result = super().write(vals)

        automatic_entry_link_fields = {
            "origin_payment_id",
            "statement_line_id",
            "tax_cash_basis_rec_id",
            "tax_cash_basis_origin_move_id",
            "exchange_diff_partial_ids",
        }
        if automatic_entry_link_fields.intersection(vals):
            self._mark_automatic_entry_approval_not_required()

        return result

    def button_draft(self):
        locked_waiting_auditor = self.filtered(
            lambda move: move._is_approval_document()
            and move.state == "posted"
            and move.approval_state == "waiting_auditor"
        )
        if locked_waiting_auditor and not self.env.context.get(
            "allow_auditor_rejection_reset"
        ):
            raise UserError(
                _(
                    "Accounting documents waiting for Auditor approval can only be reset to draft through Auditor rejection."
                )
            )

        reset_candidates = self.env["account.move"]
        if self.env.context.get("allow_auditor_rejection_reset"):
            reset_candidates = self.env["account.move"]
        elif self.env.context.get("skip_approval_reset_on_button_draft"):
            reset_candidates = self.filtered(
                lambda move: move._is_approval_document()
                and move.submitted_for_approval
                and move.approval_state in (STANDARD_RESET_APPROVAL_STATES + COMPLETED_RESET_APPROVAL_STATES)
            )
        elif self._approval_config_bool("reset_on_button_draft", default=True):
            reset_candidates = self.filtered(
                lambda move: move._is_approval_document()
                and move.submitted_for_approval
                and move.approval_state in (STANDARD_RESET_APPROVAL_STATES + COMPLETED_RESET_APPROVAL_STATES)
            )
            for move in reset_candidates:
                if not move._current_user_can_reset_approval():
                    raise AccessError(
                        _("You are not allowed to reset approval through Reset to Draft for this document.")
                    )

        existing_resetting_move_ids = _APPROVAL_RESETTING_DRAFT_MOVE_IDS.get()
        resetting_token = _APPROVAL_RESETTING_DRAFT_MOVE_IDS.set(
            frozenset(set(existing_resetting_move_ids) | set(reset_candidates.ids))
        )
        try:
            result = super().button_draft()
        finally:
            _APPROVAL_RESETTING_DRAFT_MOVE_IDS.reset(resetting_token)

        if reset_candidates and not self.env.context.get("skip_approval_reset_on_button_draft"):
            reset_candidates._reset_approval_fields()
        return result

    def _forward_posted_entries_to_auditor(self):
        for move in self:
            if not move._is_auditor_approval_required():
                continue

            auditor = move.auditor_approver_id
            move._write_approval_values({
                "approval_state": "waiting_auditor",
                "auditor_forwarded_on": fields.Datetime.now(),
                "auditor_approved": False,
                "auditor_approved_by": False,
                "auditor_approved_on": False,
                "auditor_rejected": False,
                "auditor_rejected_by": False,
                "auditor_rejected_on": False,
                "auditor_reject_reason": False,
            })
            partner_ids = auditor.partner_id.ids if auditor.partner_id else []
            move.message_post(
                body=_(
                    "%s posted and forwarded to Auditor %s for final approval."
                ) % (move._approval_document_title(), auditor.name),
                partner_ids=partner_ids,
            )
            move.sudo()._schedule_approval_activity(auditor, "auditor")

    def _check_approval_before_posting(self):
        """Enforce approval before any posting path, including reversal auto-posts."""
        for move in self:
            if not move._is_approval_document():
                continue
            if move.approval_route == "not_required":
                if not move._current_user_can_bypass_approval():
                    raise UserError(
                        _(
                            "This %s uses the 'Not Required' route. Only Accounting Approval Admins or Accounting Managers can post without approval. Select an approval route and submit it first."
                        )
                        % move._approval_document_label()
                    )
                continue
            if move.approval_state != "approved":
                raise UserError(
                    _("This %s must be approved before posting.")
                    % move._approval_document_label()
                )

    def _post(self, *args, **kwargs):
        self._check_approval_before_posting()
        approval_moves = self.filtered(lambda move: move._is_approval_document())
        existing_posting_move_ids = _APPROVAL_POSTING_MOVE_IDS.get()
        posting_token = _APPROVAL_POSTING_MOVE_IDS.set(
            frozenset(set(existing_posting_move_ids) | set(approval_moves.ids))
        )
        try:
            return super()._post(*args, **kwargs)
        finally:
            _APPROVAL_POSTING_MOVE_IDS.reset(posting_token)

    def action_post(self):
        self._check_approval_before_posting()
        approval_moves = self.filtered(lambda move: move._is_approval_document())
        existing_posting_move_ids = _APPROVAL_POSTING_MOVE_IDS.get()
        posting_token = _APPROVAL_POSTING_MOVE_IDS.set(
            frozenset(set(existing_posting_move_ids) | set(approval_moves.ids))
        )
        try:
            result = super().action_post()
        finally:
            _APPROVAL_POSTING_MOVE_IDS.reset(posting_token)

        approval_moves._clear_approval_activities(stages=("post",))
        auditor_only_moves = approval_moves.filtered(
            lambda move: move.approval_route == "auditor"
            and move.auditor_approved
            and move.approval_state == "approved"
        )
        if auditor_only_moves:
            auditor_only_moves._write_approval_values({"approval_state": "auditor_approved"})
        approval_moves._forward_posted_entries_to_auditor()
        return result

class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    approval_analytic_display = fields.Char(
        string="Analytic",
        compute="_compute_approval_analytic_display",
        compute_sudo=True,
        help="Read-only analytic distribution display for approval users who do not have full accounting access.",
    )

    @api.depends("analytic_distribution")
    def _compute_approval_analytic_display(self):
        AnalyticAccount = self.env["account.analytic.account"].sudo()
        for line in self:
            distribution = line.analytic_distribution or {}
            parts = []
            if isinstance(distribution, dict):
                for analytic_key, percentage in distribution.items():
                    account_ids = []
                    for analytic_id in str(analytic_key).split(","):
                        try:
                            account_ids.append(int(analytic_id.strip()))
                        except (TypeError, ValueError):
                            continue

                    accounts = AnalyticAccount.browse(account_ids).exists()
                    label = ", ".join(accounts.mapped("display_name")) or str(analytic_key)

                    try:
                        percentage_value = float(percentage)
                    except (TypeError, ValueError):
                        percentage_value = 100.0

                    if percentage_value and percentage_value != 100.0:
                        label = _("%s (%s%%)") % (label, format(percentage_value, "g"))
                    parts.append(label)

            line.approval_analytic_display = "; ".join(parts)

    @api.model
    def _approval_only_line_visibility_domain(self, user=None):
        return self.env["account.move"]._approval_only_move_visibility_domain(
            user=user or self.env.user,
            prefix="move_id.",
        )

    @api.model
    def _apply_approval_only_line_visibility_domain(self, domain):
        if self.env.context.get("skip_approval_only_visibility_domain"):
            return domain
        if not self.env["account.move"]._current_user_is_approval_only_user():
            return domain
        return expression.AND([
            domain or [],
            self._approval_only_line_visibility_domain(user=self.env.user),
        ])

    def _check_approval_only_line_read_access(self):
        if (
            not self
            or self.env.context.get("skip_approval_only_visibility_domain")
            or not self.env["account.move"]._current_user_is_approval_only_user()
        ):
            return
        user = self.env.user
        forbidden = self.sudo().filtered(
            lambda line: not line.move_id._approval_only_move_visible_to_user(user)
        )
        if forbidden:
            raise AccessError(
                _(
                    "You can only view journal items belonging to accounting approval documents assigned to you."
                )
            )

    @api.model
    def _search(self, domain, *args, **kwargs):
        domain = self._apply_approval_only_line_visibility_domain(domain)
        return super()._search(domain, *args, **kwargs)

    def read(self, fields=None, load="_classic_read"):
        self._check_approval_only_line_read_access()
        return super().read(fields=fields, load=load)

    def web_read(self, specification):
        if not _is_id_only_web_read(specification):
            self._check_approval_only_line_read_access()
        return super().web_read(specification)

    def _approval_locked_moves_for_line_guard(self):
        return self.mapped("move_id").filtered(lambda move: move._is_approval_document())

    def _check_approval_only_line_edit_allowed(self):
        moves = self._approval_locked_moves_for_line_guard()
        if not moves or not self.env["account.move"]._current_user_is_approval_only_user():
            return
        if (
            moves._is_internal_approval_action_write_allowed(moves)
            or moves._is_internal_posting_write_allowed(moves)
            or moves._is_internal_reset_to_draft_write_allowed(moves)
            or moves._is_auditor_rejection_reset_write_allowed(moves)
        ):
            return
        raise AccessError(
            _(
                "Branch Managers, CEOs, and Auditors can only read journal items. "
                "They cannot create, edit, or delete accounting lines."
            )
        )

    @api.model_create_multi
    def create(self, vals_list):
        move_ids = [vals.get("move_id") for vals in vals_list if vals.get("move_id")]
        if move_ids and self.env["account.move"]._current_user_is_approval_only_user():
            moves = self.env["account.move"].browse(move_ids).exists().filtered(lambda move: move._is_approval_document())
            if moves and not (
                moves._is_internal_approval_action_write_allowed(moves)
                or moves._is_internal_posting_write_allowed(moves)
                or moves._is_internal_reset_to_draft_write_allowed(moves)
                or moves._is_auditor_rejection_reset_write_allowed(moves)
            ):
                raise AccessError(
                    _(
                        "Branch Managers, CEOs, and Auditors can only read journal items. "
                        "They cannot create accounting lines."
                    )
                )
        return super().create(vals_list)

    def write(self, vals):
        self._check_approval_only_line_edit_allowed()
        return super().write(vals)

    def unlink(self):
        self._check_approval_only_line_edit_allowed()
        return super().unlink()

