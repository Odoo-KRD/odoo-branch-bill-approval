from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    branch_bill_approver_id = fields.Many2one(
        "res.users",
        string="Branch Bill Approver",
        help="Default approver for vendor bills of this company/branch.",
    )
    ceo_bill_approver_id = fields.Many2one(
        "res.users",
        string="CEO Bill Approver",
        help="CEO or final approver for sensitive vendor bills.",
    )