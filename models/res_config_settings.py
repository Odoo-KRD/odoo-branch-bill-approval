from odoo import api, fields, models


CONFIG_PREFIX = "branch_bill_approval."


def _param_value_to_bool(value, default=False):
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    approval_auditor_user_id = fields.Many2one(
        "res.users",
        string="Default Auditor",
        config_parameter="branch_bill_approval.auditor_user_id",
        help="Global Auditor used for all companies. The legacy company-level Auditor is used only as a fallback when this field is empty.",
    )
    approval_allow_reset_after_completion = fields.Boolean(
        string="Allow reset after approval route completion",
        config_parameter="branch_bill_approval.allow_reset_after_completion",
        help="Allow Reset Approval even after the final Auditor approval has completed. The accounting document must still be allowed by Odoo to reset to draft.",
    )
    approval_reset_only_submitter = fields.Boolean(
        string="Only the accountant/request owner can reset approval",
        default=True,
        config_parameter="branch_bill_approval.reset_only_submitter",
        help="When enabled, only the user who created or submitted the document, Accounting Approval Admins, and Accounting Managers can reset approval. When disabled, assigned Branch Managers, CEOs, and Auditors can reset approval too.",
    )
    approval_reset_on_button_draft = fields.Boolean(
        string="Reset approval when Reset to Draft is used",
        default=True,
        config_parameter="branch_bill_approval.reset_on_button_draft",
        help="When an authorized user resets an accounting document to draft, the approval workflow is reset to Draft as well.",
    )
    approval_require_final_auditor_review = fields.Boolean(
        string="Require final Auditor review after posting",
        default=True,
        config_parameter="branch_bill_approval.require_final_auditor_review",
        help="For Branch/CEO routes, forward posted documents to the Auditor for the final review. Keep this enabled for the full Branch Manager → CEO → Auditor workflow.",
    )

    @api.model
    def get_values(self):
        """Read settings explicitly from ir.config_parameter.

        The fields also declare config_parameter for compatibility with Odoo's
        standard settings mechanism, but this explicit read/write layer makes the
        settings stable across Odoo 19 builds and avoids the issue where the form
        appears to save but opens again with old values.
        """
        res = super().get_values()
        params = self.env["ir.config_parameter"].sudo()

        auditor_user_id = params.get_param(f"{CONFIG_PREFIX}auditor_user_id")
        try:
            auditor_user_id = int(auditor_user_id or 0)
        except (TypeError, ValueError):
            auditor_user_id = 0

        res.update({
            "approval_auditor_user_id": auditor_user_id or False,
            "approval_allow_reset_after_completion": _param_value_to_bool(
                params.get_param(f"{CONFIG_PREFIX}allow_reset_after_completion"),
                default=False,
            ),
            "approval_reset_only_submitter": _param_value_to_bool(
                params.get_param(f"{CONFIG_PREFIX}reset_only_submitter"),
                default=True,
            ),
            "approval_reset_on_button_draft": _param_value_to_bool(
                params.get_param(f"{CONFIG_PREFIX}reset_on_button_draft"),
                default=True,
            ),
            "approval_require_final_auditor_review": _param_value_to_bool(
                params.get_param(f"{CONFIG_PREFIX}require_final_auditor_review"),
                default=True,
            ),
        })
        return res

    def set_values(self):
        """Save settings explicitly to ir.config_parameter."""
        res = super().set_values()
        params = self.env["ir.config_parameter"].sudo()

        def set_bool(key, value):
            params.set_param(f"{CONFIG_PREFIX}{key}", "1" if value else "0")

        params.set_param(
            f"{CONFIG_PREFIX}auditor_user_id",
            str(self.approval_auditor_user_id.id or ""),
        )
        set_bool("allow_reset_after_completion", self.approval_allow_reset_after_completion)
        set_bool("reset_only_submitter", self.approval_reset_only_submitter)
        set_bool("reset_on_button_draft", self.approval_reset_on_button_draft)
        set_bool("require_final_auditor_review", self.approval_require_final_auditor_review)
        return res
