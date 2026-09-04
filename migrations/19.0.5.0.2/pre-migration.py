"""Pre-migration for the Auditor approval release."""


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


def migrate(cr, version):
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
