from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError
from odoo import fields


class TestBillApproval(TransactionCase):
    def setUp(self):
        super().setUp()

        self.company = self.env.company

        self.branch_user = self.env["res.users"].create({
            "name": "Branch Approver",
            "login": "branch.approver.min.v3",
            "email": "branch@example.com",
            "company_id": self.company.id,
            "company_ids": [(6, 0, [self.company.id])],
            "groups_id": [(6, 0, [self.env.ref("account.group_account_invoice").id])],
        })

        self.ceo_user = self.env["res.users"].create({
            "name": "CEO Approver",
            "login": "ceo.approver.min.v3",
            "email": "ceo@example.com",
            "company_id": self.company.id,
            "company_ids": [(6, 0, [self.company.id])],
            "groups_id": [(6, 0, [self.env.ref("account.group_account_invoice").id])],
        })

        self.company.branch_bill_approver_id = self.branch_user
        self.company.ceo_bill_approver_id = self.ceo_user

        self.payable = self.env["account.account"].search([
            ("company_ids", "in", self.company.id),
            ("account_type", "=", "liability_payable"),
        ], limit=1)

        self.expense = self.env["account.account"].search([
            ("company_ids", "in", self.company.id),
            ("account_type", "=", "expense"),
        ], limit=1)

        self.partner = self.env["res.partner"].create({
            "name": "Test Vendor",
            "property_account_payable_id": self.payable.id,
        })

    def _create_bill(self, approval_route="not_required"):
        return self.env["account.move"].create({
            "move_type": "in_invoice",
            "partner_id": self.partner.id,
            "invoice_date": fields.Date.today(),
            "approval_route": approval_route,
            "invoice_line_ids": [(0, 0, {
                "name": "Line",
                "quantity": 1.0,
                "price_unit": 100.0,
                "account_id": self.expense.id,
            })],
        })

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