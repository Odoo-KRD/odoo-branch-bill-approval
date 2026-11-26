from odoo.tests.common import TransactionCase
from odoo.exceptions import AccessError, UserError
from odoo import fields


class TestBillApproval(TransactionCase):
    def setUp(self):
        super().setUp()

        self.company = self.env.company

        branch_groups = [
            self.env.ref("account.group_account_invoice").id,
            self.env.ref("account.group_account_user").id,
            self.env.ref("branch_bill_approval.group_branch_bill_approver").id,
        ]
        ceo_groups = [
            self.env.ref("account.group_account_invoice").id,
            self.env.ref("account.group_account_user").id,
            self.env.ref("branch_bill_approval.group_ceo_bill_approver").id,
        ]
        auditor_groups = [
            self.env.ref("account.group_account_invoice").id,
            self.env.ref("account.group_account_user").id,
            self.env.ref("branch_bill_approval.group_bill_approval_auditor").id,
        ]

        self.branch_user = self.env["res.users"].create({
            "name": "Branch Approver",
            "login": "branch.approver.min.v3",
            "email": "branch@example.com",
            "company_id": self.company.id,
            "company_ids": [(6, 0, [self.company.id])],
            "group_ids": [(6, 0, branch_groups)],
        })

        self.ceo_user = self.env["res.users"].create({
            "name": "CEO Approver",
            "login": "ceo.approver.min.v3",
            "email": "ceo@example.com",
            "company_id": self.company.id,
            "company_ids": [(6, 0, [self.company.id])],
            "group_ids": [(6, 0, ceo_groups)],
        })

        self.auditor_user = self.env["res.users"].create({
            "name": "Auditor User",
            "login": "auditor.approver.min.v5",
            "email": "auditor@example.com",
            "company_id": self.company.id,
            "company_ids": [(6, 0, [self.company.id])],
            "group_ids": [(6, 0, auditor_groups)],
        })

        self.company.branch_bill_approver_id = self.branch_user
        self.company.ceo_bill_approver_id = self.ceo_user
        self.company.account_approval_auditor_id = self.auditor_user

        self.payable = self.env["account.account"].search([
            ("company_ids", "in", self.company.id),
            ("account_type", "=", "liability_payable"),
        ], limit=1)

        self.receivable = self.env["account.account"].search([
            ("company_ids", "in", self.company.id),
            ("account_type", "=", "asset_receivable"),
        ], limit=1)

        self.expense = self.env["account.account"].search([
            ("company_ids", "in", self.company.id),
            ("account_type", "=", "expense"),
        ], limit=1)

        self.income = self.env["account.account"].search([
            ("company_ids", "in", self.company.id),
            ("account_type", "=", "income"),
        ], limit=1)

        self.general_journal = self.env["account.journal"].search([
            ("company_id", "=", self.company.id),
            ("type", "=", "general"),
        ], limit=1)

        self.vendor = self.env["res.partner"].create({
            "name": "Test Vendor",
            "property_account_payable_id": self.payable.id,
        })
        self.customer = self.env["res.partner"].create({
            "name": "Test Customer",
            "property_account_receivable_id": self.receivable.id,
        })

    def _create_bill(self, approval_route="not_required"):
        return self.env["account.move"].create({
            "move_type": "in_invoice",
            "partner_id": self.vendor.id,
            "invoice_date": fields.Date.today(),
            "approval_route": approval_route,
            "invoice_line_ids": [(0, 0, {
                "name": "Line",
                "quantity": 1.0,
                "price_unit": 100.0,
                "account_id": self.expense.id,
            })],
        })

    def _create_customer_invoice(self, approval_route="not_required"):
        return self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": self.customer.id,
            "invoice_date": fields.Date.today(),
            "approval_route": approval_route,
            "invoice_line_ids": [(0, 0, {
                "name": "Line",
                "quantity": 1.0,
                "price_unit": 100.0,
                "account_id": self.income.id,
            })],
        })

    def _create_vendor_credit_note(self, approval_route="not_required"):
        return self.env["account.move"].create({
            "move_type": "in_refund",
            "partner_id": self.vendor.id,
            "invoice_date": fields.Date.today(),
            "approval_route": approval_route,
            "invoice_line_ids": [(0, 0, {
                "name": "Credit Note Line",
                "quantity": 1.0,
                "price_unit": 100.0,
                "account_id": self.expense.id,
            })],
        })

    def _create_customer_credit_note(self, approval_route="not_required"):
        return self.env["account.move"].create({
            "move_type": "out_refund",
            "partner_id": self.customer.id,
            "invoice_date": fields.Date.today(),
            "approval_route": approval_route,
            "invoice_line_ids": [(0, 0, {
                "name": "Credit Note Line",
                "quantity": 1.0,
                "price_unit": 100.0,
                "account_id": self.income.id,
            })],
        })

    def _journal_entry_values(self, approval_route="not_required"):
        return {
            "move_type": "entry",
            "journal_id": self.general_journal.id,
            "date": fields.Date.today(),
            "approval_route": approval_route,
            "line_ids": [
                (0, 0, {
                    "name": "Debit Line",
                    "account_id": self.expense.id,
                    "debit": 100.0,
                    "credit": 0.0,
                }),
                (0, 0, {
                    "name": "Credit Line",
                    "account_id": self.income.id,
                    "debit": 0.0,
                    "credit": 100.0,
                }),
            ],
        }

    def _create_journal_entry(self, approval_route="not_required"):
        return self.env["account.move"].create(self._journal_entry_values(approval_route))

    def _create_journal_entry_as_user(self, user, approval_route="not_required"):
        return self.env["account.move"].with_user(user).create(
            self._journal_entry_values(approval_route)
        )

    def test_not_required_can_post_without_approval(self):
        bill = self._create_bill("not_required")

        bill.action_post()

        self.assertEqual(bill.state, "posted")

    def test_branch_approval_flow(self):
        bill = self._create_bill("branch")

        bill.action_submit_for_approval()
        self.assertEqual(bill.approval_state, "waiting_branch")

        bill.with_user(self.branch_user).action_branch_approve()
        self.assertEqual(bill.approval_state, "approved")

    def test_branch_then_ceo_approval_flow(self):
        bill = self._create_bill("branch_ceo")

        bill.action_submit_for_approval()
        self.assertEqual(bill.approval_state, "waiting_branch")

        bill.with_user(self.branch_user).action_branch_approve()
        self.assertEqual(bill.approval_state, "waiting_ceo")

        bill.with_user(self.ceo_user).action_ceo_approve()
        self.assertEqual(bill.approval_state, "approved")

    def test_ceo_only_approval_flow(self):
        bill = self._create_bill("ceo")

        bill.action_submit_for_approval()
        self.assertEqual(bill.approval_state, "waiting_ceo")

        bill.with_user(self.ceo_user).action_ceo_approve()
        self.assertEqual(bill.approval_state, "approved")

    def test_auditor_only_approval_flow(self):
        bill = self._create_bill("auditor")

        bill.action_submit_for_approval()
        self.assertEqual(bill.approval_state, "waiting_auditor")
        self.assertEqual(bill.approval_pending_user_id, self.auditor_user)

        bill.with_user(self.auditor_user).action_auditor_approve()
        self.assertEqual(bill.approval_state, "approved")
        self.assertTrue(bill.auditor_approved)
        self.assertEqual(bill.auditor_approved_by, self.auditor_user)
        self.assertTrue(bill.approval_ready_to_post)

        bill.action_post()
        self.assertEqual(bill.state, "posted")
        self.assertEqual(bill.approval_state, "auditor_approved")

    def test_auditor_only_rejection_marks_document_rejected(self):
        invoice = self._create_customer_invoice("auditor")

        invoice.action_submit_for_approval()
        invoice.with_user(self.auditor_user).with_context(
            approval_reject_reason="Please attach the signed invoice."
        ).action_reject_approval()

        self.assertEqual(invoice.state, "draft")
        self.assertEqual(invoice.approval_state, "rejected")
        self.assertTrue(invoice.auditor_rejected)
        self.assertEqual(invoice.auditor_rejected_by, self.auditor_user)
        self.assertIn("signed invoice", invoice.auditor_reject_reason)

    def test_customer_invoice_uses_same_approval_flow(self):
        invoice = self._create_customer_invoice("branch")

        invoice.action_submit_for_approval()
        self.assertEqual(invoice.approval_state, "waiting_branch")

        invoice.with_user(self.branch_user).action_branch_approve()
        self.assertEqual(invoice.approval_state, "approved")

    def test_vendor_credit_note_uses_same_approval_flow(self):
        credit_note = self._create_vendor_credit_note("branch")

        self.assertTrue(credit_note._is_approval_document())
        credit_note.action_submit_for_approval()
        self.assertEqual(credit_note.approval_state, "waiting_branch")

        credit_note.with_user(self.branch_user).action_branch_approve()
        self.assertEqual(credit_note.approval_state, "approved")

    def test_customer_credit_note_uses_same_approval_flow(self):
        credit_note = self._create_customer_credit_note("auditor")

        self.assertTrue(credit_note._is_approval_document())
        credit_note.action_submit_for_approval()
        self.assertEqual(credit_note.approval_state, "waiting_auditor")

        credit_note.with_user(self.auditor_user).action_auditor_approve()
        self.assertEqual(credit_note.approval_state, "approved")
        self.assertTrue(credit_note.approval_ready_to_post)

    def test_direct_posting_path_blocks_unapproved_vendor_credit_note(self):
        credit_note = self._create_vendor_credit_note("auditor")

        with self.assertRaises(UserError):
            credit_note._post(soft=False)

        self.assertEqual(credit_note.state, "draft")

    def test_approved_customer_invoice_can_be_posted_after_branch_ceo_approval(self):
        invoice = self._create_customer_invoice("branch_ceo")

        invoice.action_submit_for_approval()
        invoice.with_user(self.branch_user).action_branch_approve()
        invoice.with_user(self.ceo_user).action_ceo_approve()
        self.assertEqual(invoice.approval_state, "approved")

        invoice.action_post()

        self.assertEqual(invoice.state, "posted")
        self.assertEqual(invoice.approval_state, "waiting_auditor")
        self.assertEqual(invoice.approval_pending_user_id, self.auditor_user)

    def test_journal_entry_uses_same_approval_flow(self):
        entry = self._create_journal_entry("branch")

        entry.action_submit_for_approval()
        self.assertEqual(entry.approval_state, "waiting_branch")

        entry.with_user(self.branch_user).action_branch_approve()
        self.assertEqual(entry.approval_state, "approved")

    def test_branch_approver_cannot_see_ceo_waiting_document(self):
        bill = self._create_bill("branch_ceo")

        bill.action_submit_for_approval()
        bill.with_user(self.branch_user).action_branch_approve()
        self.assertEqual(bill.approval_state, "waiting_ceo")

        visible_to_branch = self.env["account.move"].with_user(self.branch_user).search([
            ("id", "=", bill.id),
        ])
        visible_to_ceo = self.env["account.move"].with_user(self.ceo_user).search([
            ("id", "=", bill.id),
        ])

        self.assertFalse(visible_to_branch)
        self.assertEqual(visible_to_ceo.ids, bill.ids)

    def test_submitter_can_see_journal_entry_waiting_ceo(self):
        entry = self._create_journal_entry("branch_ceo")

        entry.with_user(self.branch_user).action_submit_for_approval()
        entry.with_user(self.branch_user).action_branch_approve()
        self.assertEqual(entry.approval_state, "waiting_ceo")
        self.assertEqual(entry.approval_submitted_by, self.branch_user)

        visible_to_submitter = self.env["account.move"].with_user(self.branch_user).search([
            ("id", "=", entry.id),
        ])
        self.assertEqual(visible_to_submitter.ids, entry.ids)

    def test_ready_to_post_activity_scheduled_for_submitter_after_approval(self):
        bill = self._create_bill("branch")

        bill.action_submit_for_approval()
        self.assertEqual(bill.approval_pending_user_id, self.branch_user)
        bill.with_user(self.branch_user).action_branch_approve()
        self.assertTrue(bill.approval_ready_to_post)

        activity = self.env["mail.activity"].search([
            ("res_model", "=", "account.move"),
            ("res_id", "=", bill.id),
            ("user_id", "=", bill.approval_submitted_by.id),
            ("summary", "ilike", "ready to post"),
        ])
        self.assertTrue(activity)

        bill.action_post()
        activity_after_posting = self.env["mail.activity"].search([
            ("res_model", "=", "account.move"),
            ("res_id", "=", bill.id),
            ("user_id", "=", bill.approval_submitted_by.id),
            ("summary", "ilike", "ready to post"),
        ])
        self.assertFalse(activity_after_posting)

    def test_posted_bill_forwarded_to_auditor_after_branch_ceo_approval(self):
        bill = self._create_bill("branch_ceo")

        bill.action_submit_for_approval()
        bill.with_user(self.branch_user).action_branch_approve()
        bill.with_user(self.ceo_user).action_ceo_approve()
        bill.action_post()

        self.assertEqual(bill.state, "posted")
        self.assertEqual(bill.approval_state, "waiting_auditor")
        self.assertEqual(bill.approval_pending_user_id, self.auditor_user)

        activity = self.env["mail.activity"].search([
            ("res_model", "=", "account.move"),
            ("res_id", "=", bill.id),
            ("user_id", "=", self.auditor_user.id),
            ("summary", "ilike", "Auditor"),
        ])
        self.assertTrue(activity)

    def test_posted_bill_forwarded_to_auditor_after_ceo_only_approval(self):
        bill = self._create_bill("ceo")

        bill.action_submit_for_approval()
        bill.with_user(self.ceo_user).action_ceo_approve()
        bill.action_post()

        self.assertEqual(bill.state, "posted")
        self.assertEqual(bill.approval_state, "waiting_auditor")
        self.assertEqual(bill.approval_pending_user_id, self.auditor_user)

    def test_auditor_can_approve_posted_bill(self):
        bill = self._create_bill("branch_ceo")

        bill.action_submit_for_approval()
        bill.with_user(self.branch_user).action_branch_approve()
        bill.with_user(self.ceo_user).action_ceo_approve()
        bill.action_post()
        bill.with_user(self.auditor_user).action_auditor_approve()

        self.assertEqual(bill.approval_state, "auditor_approved")
        self.assertTrue(bill.auditor_approved)
        self.assertEqual(bill.auditor_approved_by, self.auditor_user)

    def test_posted_journal_entry_forwarded_to_auditor(self):
        entry = self._create_journal_entry("branch")

        entry.action_submit_for_approval()
        entry.with_user(self.branch_user).action_branch_approve()
        entry.action_post()

        self.assertEqual(entry.state, "posted")
        self.assertEqual(entry.approval_state, "waiting_auditor")
        self.assertEqual(entry.approval_pending_user_id, self.auditor_user)

        activity = self.env["mail.activity"].search([
            ("res_model", "=", "account.move"),
            ("res_id", "=", entry.id),
            ("user_id", "=", self.auditor_user.id),
            ("summary", "ilike", "Auditor"),
        ])
        self.assertTrue(activity)

    def test_auditor_can_approve_posted_journal_entry(self):
        entry = self._create_journal_entry("branch")

        entry.action_submit_for_approval()
        entry.with_user(self.branch_user).action_branch_approve()
        entry.action_post()
        entry.with_user(self.auditor_user).action_auditor_approve()

        self.assertEqual(entry.approval_state, "auditor_approved")
        self.assertTrue(entry.auditor_approved)
        self.assertEqual(entry.auditor_approved_by, self.auditor_user)

    def test_auditor_rejection_resets_journal_entry_to_draft(self):
        entry = self._create_journal_entry("branch")

        entry.action_submit_for_approval()
        entry.with_user(self.branch_user).action_branch_approve()
        entry.action_post()
        entry.with_user(self.auditor_user).with_context(
            approval_reject_reason="Please attach the missing supporting document."
        ).action_reject_approval()

        self.assertEqual(entry.state, "draft")
        self.assertEqual(entry.approval_state, "draft")
        self.assertFalse(entry.submitted_for_approval)
        self.assertTrue(entry.auditor_rejected)
        self.assertEqual(entry.auditor_rejected_by, self.auditor_user)
        self.assertIn("missing supporting document", entry.auditor_reject_reason)

        entry.action_submit_for_approval()
        self.assertEqual(entry.approval_state, "waiting_branch")
        self.assertFalse(entry.auditor_rejected)


    def test_submitter_can_reset_waiting_request_to_edit_again(self):
        entry = self._create_journal_entry("branch")

        entry.action_submit_for_approval()
        self.assertEqual(entry.approval_state, "waiting_branch")
        self.assertTrue(entry.can_reset_approval)

        entry.action_reset_approval()
        self.assertEqual(entry.approval_state, "draft")
        self.assertFalse(entry.submitted_for_approval)
        self.assertFalse(entry.approval_submitted_by)

    def test_submitter_can_reset_approved_unposted_request(self):
        invoice = self._create_customer_invoice("branch")

        invoice.action_submit_for_approval()
        invoice.with_user(self.branch_user).action_branch_approve()
        self.assertEqual(invoice.approval_state, "approved")
        self.assertTrue(invoice.approval_ready_to_post)

        invoice.action_reset_approval()
        self.assertEqual(invoice.approval_state, "draft")
        self.assertFalse(invoice.approval_ready_to_post)
        self.assertFalse(invoice.submitted_for_approval)

    def test_post_blocked_before_approval_branch(self):
        bill = self._create_bill("branch")

        bill.action_submit_for_approval()

        with self.assertRaises(UserError):
            bill.action_post()

    def test_post_blocked_before_approval_branch_ceo(self):
        bill = self._create_bill("branch_ceo")

        bill.action_submit_for_approval()

        with self.assertRaises(UserError):
            bill.action_post()

    def test_post_blocked_before_approval_ceo(self):
        bill = self._create_bill("ceo")

        bill.action_submit_for_approval()

        with self.assertRaises(UserError):
            bill.action_post()

    def test_cannot_submit_not_required_route(self):
        bill = self._create_bill("not_required")

        with self.assertRaises(UserError):
            bill.action_submit_for_approval()

    def test_approved_unposted_document_cannot_be_edited_without_reset(self):
        bill = self._create_bill("branch")

        bill.action_submit_for_approval()
        bill.with_user(self.branch_user).action_branch_approve()
        self.assertEqual(bill.approval_state, "approved")

        with self.assertRaises(UserError):
            bill.write({"invoice_date": fields.Date.today()})

    def test_direct_workflow_write_is_blocked(self):
        bill = self._create_bill("branch")

        with self.assertRaises(AccessError):
            bill.write({"approval_state": "approved"})

    def test_company_approver_change_does_not_reroute_submitted_document(self):
        bill = self._create_bill("branch")
        bill.action_submit_for_approval()
        original_branch = bill.branch_approver_id

        replacement_branch = self.env["res.users"].create({
            "name": "Replacement Branch Approver",
            "login": "replacement.branch.approver.min.v1",
            "email": "replacement.branch@example.com",
            "company_id": self.company.id,
            "company_ids": [(6, 0, [self.company.id])],
            "group_ids": [(6, 0, [
                self.env.ref("account.group_account_invoice").id,
                self.env.ref("account.group_account_user").id,
                self.env.ref("branch_bill_approval.group_branch_bill_approver").id,
            ])],
        })
        self.company.branch_bill_approver_id = replacement_branch

        self.assertEqual(bill.branch_approver_id, original_branch)
        self.assertEqual(bill.approval_pending_user_id, original_branch)

    def test_regular_user_cannot_post_not_required_route(self):
        bill = self._create_bill("not_required")

        with self.assertRaises(UserError):
            bill.with_user(self.branch_user).action_post()

    def test_system_generated_payment_entry_bypasses_manual_approval(self):
        payment_journal = self.env["account.journal"].search([
            ("company_id", "=", self.company.id),
            ("type", "in", ["bank", "cash", "credit"]),
        ], limit=1)
        if not payment_journal:
            self.skipTest("No payment journal available in this chart template.")

        payment = self.env["account.payment"].create({
            "payment_type": "outbound",
            "partner_type": "supplier",
            "partner_id": self.vendor.id,
            "amount": 100.0,
            "date": fields.Date.today(),
            "journal_id": payment_journal.id,
        })
        values = self._journal_entry_values("branch")
        values["origin_payment_id"] = payment.id
        payment_entry = self.env["account.move"].create(values)

        self.assertEqual(payment_entry.approval_route, "not_required")
        self.assertEqual(payment_entry.approval_state, "not_required")
        self.assertFalse(payment_entry._is_approval_document())

        payment_entry.with_user(self.branch_user).action_post()
        self.assertEqual(payment_entry.state, "posted")

    def test_branch_manager_group_can_read_assigned_journal_items(self):
        minimal_branch_user = self.env["res.users"].create({
            "name": "Branch Manager Only",
            "login": "branch.manager.only.min.v1",
            "email": "branch.manager.only@example.com",
            "company_id": self.company.id,
            "company_ids": [(6, 0, [self.company.id])],
            "group_ids": [(6, 0, [
                self.env.ref("branch_bill_approval.group_branch_bill_approver").id,
            ])],
        })
        self.company.branch_bill_approver_id = minimal_branch_user
        bill = self._create_bill("branch")

        bill.action_submit_for_approval()
        visible_lines = self.env["account.move.line"].with_user(minimal_branch_user).search([
            ("move_id", "=", bill.id),
        ])

        self.assertEqual(set(visible_lines.ids), set(bill.line_ids.ids))


    def _create_branch_credit_note_from_reversal(self):
        """Post a bill the Branch Manager is not assigned to, then reverse it."""
        original_bill = self._create_bill("not_required")
        original_bill.action_post()
        credit_note = original_bill._reverse_moves([{
            "ref": "Reversal of: %s" % original_bill.name,
            "invoice_date": fields.Date.today(),
        }])
        self.assertEqual(credit_note.move_type, "in_refund")
        self.assertEqual(credit_note.reversed_entry_id, original_bill)
        credit_note.approval_route = "branch"
        credit_note.action_submit_for_approval()
        self.assertEqual(credit_note.approval_pending_user_id, self.branch_user)
        return original_bill, credit_note

    def test_branch_manager_can_open_credit_note_created_by_reverse(self):
        original_bill, credit_note = self._create_branch_credit_note_from_reversal()
        branch_credit_note = credit_note.with_user(self.branch_user)

        # Same shape of request as the credit note form: the original bill is
        # loaded as a many2one with its display name only.
        result = branch_credit_note.web_read({
            "name": {},
            "approval_state": {},
            "reversed_entry_id": {"fields": {"display_name": {}}},
            "line_ids": {"fields": {"name": {}, "balance": {}}},
        })

        self.assertEqual(result[0]["id"], credit_note.id)
        self.assertEqual(result[0]["reversed_entry_id"]["id"], original_bill.id)
        self.assertEqual(
            result[0]["reversed_entry_id"]["display_name"],
            original_bill.display_name,
        )
        self.assertEqual(
            {line["id"] for line in result[0]["line_ids"]},
            set(credit_note.line_ids.ids),
        )

    def test_branch_manager_still_cannot_open_unassigned_original_bill(self):
        original_bill, _credit_note = self._create_branch_credit_note_from_reversal()
        branch_bill = original_bill.with_user(self.branch_user)

        with self.assertRaises(AccessError):
            branch_bill.web_read({"name": {}})
        with self.assertRaises(AccessError):
            branch_bill.read(["name"])
        with self.assertRaises(AccessError):
            original_bill.line_ids.with_user(self.branch_user).read(["name"])
        self.assertFalse(
            self.env["account.move"].with_user(self.branch_user).search([
                ("id", "=", original_bill.id),
            ])
        )
