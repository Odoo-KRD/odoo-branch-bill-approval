"""Schema safety helpers for Branch Accounting Approval.

The Auditor release adds stored fields on res.company and account.move. If code is
copied before the Odoo module upgrade is completed, Odoo may load the new Python
fields while the database columns are still missing. These helpers create the
new columns defensively during install/upgrade so the service can start cleanly.
"""


def _cursor(env_or_cr):
    return getattr(env_or_cr, "cr", env_or_cr)


def _table_exists(cr, table):
    cr.execute("SELECT to_regclass(%s)", (table,))
    return bool(cr.fetchone()[0])


def _column_exists(cr, table, column):
    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = %s
           AND column_name = %s
        """,
        (table, column),
    )
    return bool(cr.fetchone())


def _add_column_if_missing(cr, table, column, column_type):
    if _table_exists(cr, table) and not _column_exists(cr, table, column):
        cr.execute(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {column_type}')


def ensure_auditor_schema(cr):
    """Create Auditor-release columns if they are missing.

    This is intentionally limited to nullable columns added by the Auditor
    workflow. Odoo's normal module upgrade can still manage metadata and related
    recomputation afterwards.
    """
    _add_column_if_missing(cr, "res_company", "account_approval_auditor_id", "integer")

    account_move_columns = {
        "auditor_approver_id": "integer",
        "auditor_forwarded_on": "timestamp without time zone",
        "auditor_approved": "boolean",
        "auditor_approved_by": "integer",
        "auditor_approved_on": "timestamp without time zone",
        "auditor_rejected": "boolean",
        "auditor_rejected_by": "integer",
        "auditor_rejected_on": "timestamp without time zone",
        "auditor_reject_reason": "text",
    }
    for column, column_type in account_move_columns.items():
        _add_column_if_missing(cr, "account_move", column, column_type)



def normalize_automatic_entry_approval_state(cr):
    """Mark Odoo-generated journal entries as not requiring manual approval.

    This keeps existing payment/reconciliation entries from being caught by the
    manual journal-entry approval route after an upgrade.
    """
    if not _table_exists(cr, "account_move"):
        return
    required_columns = (
        "approval_route",
        "approval_state",
        "submitted_for_approval",
        "origin_payment_id",
        "statement_line_id",
        "tax_cash_basis_rec_id",
        "tax_cash_basis_origin_move_id",
    )
    if not all(_column_exists(cr, "account_move", column) for column in required_columns):
        return
    automatic_entry_predicates = [
        "origin_payment_id IS NOT NULL",
        "statement_line_id IS NOT NULL",
        "tax_cash_basis_rec_id IS NOT NULL",
        "tax_cash_basis_origin_move_id IS NOT NULL",
    ]
    if (
        _table_exists(cr, "account_partial_reconcile")
        and _column_exists(cr, "account_partial_reconcile", "exchange_move_id")
    ):
        automatic_entry_predicates.append(
            "EXISTS (SELECT 1 FROM account_partial_reconcile apr WHERE apr.exchange_move_id = account_move.id)"
        )
    predicate_sql = " OR ".join(automatic_entry_predicates)
    cr.execute(
        f"""
        UPDATE account_move
           SET approval_route = 'not_required',
               approval_state = 'not_required',
               submitted_for_approval = FALSE
         WHERE move_type = 'entry'
           AND COALESCE(approval_state, 'draft') != 'not_required'
           AND ({predicate_sql})
        """
    )


def seed_global_auditor_setting(cr):
    """Move a single shared company Auditor to the new global settings parameter."""
    if not (_table_exists(cr, "res_company") and _table_exists(cr, "ir_config_parameter")):
        return
    if not _column_exists(cr, "res_company", "account_approval_auditor_id"):
        return
    cr.execute(
        "SELECT value FROM ir_config_parameter WHERE key = %s",
        ("branch_bill_approval.auditor_user_id",),
    )
    existing = cr.fetchone()
    if existing and existing[0]:
        return
    cr.execute(
        """
        SELECT DISTINCT account_approval_auditor_id
          FROM res_company
         WHERE account_approval_auditor_id IS NOT NULL
        """
    )
    auditor_ids = [row[0] for row in cr.fetchall()]
    if len(auditor_ids) != 1:
        return
    cr.execute(
        """
        INSERT INTO ir_config_parameter (key, value, create_date, write_date)
        VALUES (%s, %s, NOW(), NOW())
        ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value,
                write_date = NOW()
        """,
        ("branch_bill_approval.auditor_user_id", str(auditor_ids[0])),
    )


def seed_default_approval_settings(cr):
    """Create default config parameters when they do not exist yet.

    This keeps Settings > Accounting Approval consistent on fresh databases and
    after upgrades. Existing administrator choices are not overwritten.
    """
    if not _table_exists(cr, "ir_config_parameter"):
        return
    defaults = {
        "branch_bill_approval.allow_reset_after_completion": "0",
        "branch_bill_approval.reset_only_submitter": "1",
        "branch_bill_approval.reset_on_button_draft": "1",
        "branch_bill_approval.require_final_auditor_review": "1",
    }
    for key, value in defaults.items():
        cr.execute(
            """
            INSERT INTO ir_config_parameter (key, value, create_date, write_date)
            SELECT %s, %s, NOW(), NOW()
             WHERE NOT EXISTS (
                   SELECT 1 FROM ir_config_parameter WHERE key = %s
             )
            """,
            (key, value, key),
        )


def cleanup_launcher_visibility_settings(cr):
    """Remove deprecated launcher setting parameters from version 19.0.5.0.18."""
    if not _table_exists(cr, "ir_config_parameter"):
        return
    cr.execute(
        """
        DELETE FROM ir_config_parameter
         WHERE key IN (
            'branch_bill_approval.app_available_branch_manager',
            'branch_bill_approval.app_available_ceo',
            'branch_bill_approval.app_available_auditor',
            'branch_bill_approval.app_available_accountant'
         )
        """
    )


def _menu_group_relation(cr):
    """Return the SQL M2M table/columns used for menu group visibility.

    In Odoo 19 the menu group relation may no longer be exposed as an ORM
    field on ir.ui.menu, so writing ``groups_id`` can crash upgrades.  The XML
    ``groups=`` attribute still stores rows in a relation table, therefore this
    repair uses SQL and detects the table shape defensively.
    """
    candidates = [
        ("ir_ui_menu_group_rel", "menu_id", "gid"),
        ("ir_ui_menu_group_rel", "menu_id", "group_id"),
        ("ir_ui_menu_res_groups_rel", "ir_ui_menu_id", "res_groups_id"),
        ("ir_ui_menu_res_groups_rel", "menu_id", "group_id"),
    ]
    for table, menu_col, group_col in candidates:
        if (
            _table_exists(cr, table)
            and _column_exists(cr, table, menu_col)
            and _column_exists(cr, table, group_col)
        ):
            return table, menu_col, group_col
    return None


def _replace_menu_groups_sql(cr, menu_id, group_ids):
    relation = _menu_group_relation(cr)
    if not relation:
        return
    table, menu_col, group_col = relation
    cr.execute(f'DELETE FROM "{table}" WHERE "{menu_col}" = %s', (menu_id,))
    for group_id in group_ids:
        cr.execute(
            f'INSERT INTO "{table}" ("{menu_col}", "{group_col}") VALUES (%s, %s) ON CONFLICT DO NOTHING',
            (menu_id, group_id),
        )


def _config_bool(cr, key, default=True):
    if not _table_exists(cr, "ir_config_parameter"):
        return default
    cr.execute("SELECT value FROM ir_config_parameter WHERE key = %s", (key,))
    row = cr.fetchone()
    if not row or row[0] in (None, ""):
        return default
    return str(row[0]).strip().lower() in {"1", "true", "yes", "y", "on"}


def _replace_menu_groups(env, menu, groups):
    """Replace menu group visibility using the field name used by this Odoo build.

    Odoo 19 renamed several security M2M fields from groups_id to group_ids.
    Some builds no longer expose the old groups_id field on ir.ui.menu, so this
    method writes group_ids when available and falls back to SQL only if needed.
    """
    group_ids = groups.ids if hasattr(groups, "ids") else list(groups)
    menu_model = env["ir.ui.menu"]
    if "group_ids" in menu_model._fields:
        menu.sudo().write({"group_ids": [(6, 0, group_ids)]})
        return
    if "groups_id" in menu_model._fields:
        menu.sudo().write({"groups_id": [(6, 0, group_ids)]})
        return
    _replace_menu_groups_sql(env.cr, menu.id, group_ids)


def _clear_menu_caches(env):
    menu_model = env["ir.ui.menu"]
    for method_name in ("clear_caches", "_clear_cache", "_clear_caches"):
        method = getattr(menu_model, method_name, None)
        if method:
            try:
                method()
            except TypeError:
                pass
    try:
        env.registry.clear_cache()
    except Exception:
        pass



def _user_group_relation(cr):
    """Return the SQL M2M table/columns used for user/group membership."""
    candidates = [
        ("res_groups_users_rel", "uid", "gid"),
        ("res_users_groups_rel", "user_id", "group_id"),
        ("res_groups_res_users_rel", "res_users_id", "res_groups_id"),
    ]
    for table, user_col, group_col in candidates:
        if (
            _table_exists(cr, table)
            and _column_exists(cr, table, user_col)
            and _column_exists(cr, table, group_col)
        ):
            return table, user_col, group_col
    return None


def ensure_reviewer_group_user_memberships(cr):
    """Apply the internal reviewer group to existing role users after upgrade.

    Adding implied_ids to a group definition is not always reflected on users
    that already had the parent group before the upgrade. This keeps the
    internal reviewer group synchronized for existing Branch Manager, CEO,
    Auditor, and Approval Admin users.
    """
    relation = _user_group_relation(cr)
    if not relation or not _table_exists(cr, "ir_model_data"):
        return

    def group_id(xmlid_name):
        cr.execute(
            """
            SELECT res_id
              FROM ir_model_data
             WHERE module = %s
               AND name = %s
               AND model = 'res.groups'
            """,
            ("branch_bill_approval", xmlid_name),
        )
        row = cr.fetchone()
        return row[0] if row else None

    reviewer_id = group_id("group_bill_approval_reviewer")
    role_ids = [
        group_id("group_branch_bill_approver"),
        group_id("group_ceo_bill_approver"),
        group_id("group_bill_approval_auditor"),
        group_id("group_bill_approval_admin"),
    ]
    role_ids = [gid for gid in role_ids if gid]
    if not reviewer_id or not role_ids:
        return

    table, user_col, group_col = relation
    cr.execute(
        f"""
        INSERT INTO "{table}" ("{user_col}", "{group_col}")
        SELECT DISTINCT src."{user_col}", %s
          FROM "{table}" src
         WHERE src."{group_col}" = ANY(%s)
           AND NOT EXISTS (
               SELECT 1
                 FROM "{table}" existing
                WHERE existing."{user_col}" = src."{user_col}"
                  AND existing."{group_col}" = %s
           )
        """,
        (reviewer_id, role_ids, reviewer_id),
    )

def ensure_approval_menu_group_visibility(cr):
    """Keep the Approval launcher/menu tied to the actual approval role groups.

    The previous experimental launcher checkboxes are intentionally ignored here.
    A user sees the app only when the proper approval/access-right group is
    assigned on the user form.
    """
    try:
        from odoo import SUPERUSER_ID, api
    except Exception:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})

    def ref(xmlid):
        return env.ref(xmlid, raise_if_not_found=False)

    def refs(xmlids):
        records = env["res.groups"]
        for xmlid in xmlids:
            record = ref(xmlid)
            if record:
                records |= record
        return records

    reviewer_groups = refs([
        "branch_bill_approval.group_branch_bill_approver",
        "branch_bill_approval.group_ceo_bill_approver",
        "branch_bill_approval.group_bill_approval_auditor",
        "branch_bill_approval.group_bill_approval_admin",
    ])
    request_groups = refs([
        "branch_bill_approval.group_bill_approval_owner",
        "branch_bill_approval.group_invoice_bill_accountant",
        "branch_bill_approval.group_bill_approval_admin",
    ])
    accountant_groups = refs([
        "branch_bill_approval.group_invoice_bill_accountant",
        "branch_bill_approval.group_bill_approval_admin",
    ])
    root_groups = reviewer_groups | request_groups | accountant_groups

    menu_groups = {
        "branch_bill_approval.menu_accounting_approval_root": root_groups,
        "branch_bill_approval.menu_accounting_approval_accounting_shortcut_root": root_groups,
        "branch_bill_approval.menu_accounting_approval_waiting_my_action": reviewer_groups,
        "branch_bill_approval.menu_accounting_approval_reviewed_by_me": reviewer_groups,
        "branch_bill_approval.menu_accounting_approval_assigned_journal_entries": reviewer_groups,
        "branch_bill_approval.menu_accounting_approval_assigned_journal_items": reviewer_groups,
        "branch_bill_approval.menu_accounting_approval_accounting_waiting_my_action": reviewer_groups,
        "branch_bill_approval.menu_accounting_approval_accounting_reviewed_by_me": reviewer_groups,
        "branch_bill_approval.menu_accounting_approval_accounting_assigned_journal_entries": reviewer_groups,
        "branch_bill_approval.menu_accounting_approval_accounting_assigned_journal_items": reviewer_groups,
        "branch_bill_approval.menu_accounting_approval_my_requests": request_groups,
        "branch_bill_approval.menu_accounting_approval_accounting_my_requests": request_groups,
        "branch_bill_approval.menu_accounting_approval_all_visible": accountant_groups,
    }
    for menu_xmlid, groups in menu_groups.items():
        menu = ref(menu_xmlid)
        if menu and groups:
            _replace_menu_groups(env, menu, groups)

    _clear_menu_caches(env)

def pre_init_hook(env_or_cr):
    ensure_auditor_schema(_cursor(env_or_cr))


def post_init_hook(env_or_cr):
    cr = _cursor(env_or_cr)
    ensure_auditor_schema(cr)
    seed_global_auditor_setting(cr)
    seed_default_approval_settings(cr)
    cleanup_launcher_visibility_settings(cr)
    normalize_automatic_entry_approval_state(cr)
    ensure_reviewer_group_user_memberships(cr)
    ensure_approval_menu_group_visibility(cr)
