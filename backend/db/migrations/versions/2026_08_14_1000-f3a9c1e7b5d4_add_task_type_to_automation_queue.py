"""Add task_type + source_language to subtitle_automation_queue.

The queue only ever held embedded extractions, so `wanted_item_id` was
UNIQUE. Sidecar translation moves onto the same queue, and one wanted item
can legitimately need both — an embedded track to extract *and* an external
source sidecar to translate. The uniqueness that still holds is per
(wanted_item_id, task_type).

The old constraint is named by the database, not by us, and the two
dialects disagree: PostgreSQL auto-named it
`subtitle_automation_queue_wanted_item_id_key` (verified against production
2026-08-14), while SQLite created it inline with no name at all. Hence the
dialect split — a single `drop_constraint(name)` cannot be right on both,
and CI only ever exercises the SQLite half.

Revision ID: f3a9c1e7b5d4
Revises: c8d9e0f1a2b3
Create Date: 2026-08-14

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision = "f3a9c1e7b5d4"
down_revision = "c8d9e0f1a2b3"
branch_labels = None
depends_on = None

_TABLE = "subtitle_automation_queue"
_NEW_UQ = "uq_automation_queue_item_task"
_PG_OLD_UQ = "subtitle_automation_queue_wanted_item_id_key"

# SQLite named nothing, so batch mode has to invent a name for the reflected
# constraint before it can drop it. This convention is what produces it.
_SQLITE_NAMING = {"uq": "uq_%(table_name)s_%(column_0_name)s"}
_SQLITE_OLD_UQ = "uq_subtitle_automation_queue_wanted_item_id"


def _existing_columns(bind) -> set[str]:
    return {c["name"] for c in sa.inspect(bind).get_columns(_TABLE)}


def _uniques(bind) -> list[dict]:
    return sa.inspect(bind).get_unique_constraints(_TABLE)


def _single_column_uniques(bind, column: str) -> list[dict]:
    """Reflected UNIQUE constraints covering exactly ``column``.

    Reflection rather than a hardcoded name, because the name is whatever the
    database chose: PostgreSQL auto-named it, SQLite created it inline with no
    name at all, and a database built by ``create_all`` from the current model
    has neither. Batch mode defers drop_constraint to its flush() at __exit__,
    so a try/except around the call cannot catch a missing constraint — the
    check has to happen before the batch opens.
    """
    return [u for u in _uniques(bind) if list(u.get("column_names") or []) == [column]]


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    columns = _existing_columns(bind)

    # A fresh SQLite install creates its schema from the model metadata rather
    # than by replaying migrations, so the columns can already be here.
    if "task_type" not in columns:
        op.add_column(
            _TABLE,
            sa.Column(
                "task_type",
                sa.String(24),
                nullable=False,
                server_default="embedded_extract",
            ),
        )
    if "source_language" not in columns:
        op.add_column(_TABLE, sa.Column("source_language", sa.String(8), nullable=True))

    # Existing rows are all extractions — that is all this queue ever held.
    op.execute(
        f"UPDATE {_TABLE} SET task_type = 'embedded_extract' "  # noqa: S608 — constant table name
        "WHERE task_type IS NULL OR task_type = ''"
    )

    stale = _single_column_uniques(bind, "wanted_item_id")
    has_new = any(u.get("name") == _NEW_UQ for u in _uniques(bind))
    if not stale and has_new:
        # Schema built from the current model metadata rather than by replaying
        # migrations — already the shape we want.
        return

    if dialect == "postgresql":
        for uq in stale:
            op.drop_constraint(uq["name"] or _PG_OLD_UQ, _TABLE, type_="unique")
        if not has_new:
            op.create_unique_constraint(_NEW_UQ, _TABLE, ["wanted_item_id", "task_type"])
    else:
        with op.batch_alter_table(_TABLE, naming_convention=_SQLITE_NAMING) as batch:
            for uq in stale:
                # SQLite reflects an inline UNIQUE with no name; inside batch
                # the naming convention above is what gives it one.
                batch.drop_constraint(uq["name"] or _SQLITE_OLD_UQ, type_="unique")
            if not has_new:
                batch.create_unique_constraint(_NEW_UQ, ["wanted_item_id", "task_type"])


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    columns = _existing_columns(bind)
    if "task_type" not in columns:
        return

    # Going back to one row per item means the extra rows cannot survive.
    # Keep the oldest per item, which is the extraction for anything that
    # existed before this migration.
    op.execute(
        f"DELETE FROM {_TABLE} WHERE id NOT IN "  # noqa: S608 — constant table name
        f"(SELECT MIN(id) FROM {_TABLE} GROUP BY wanted_item_id)"
    )

    has_new = any(u.get("name") == _NEW_UQ for u in _uniques(bind))
    if dialect == "postgresql":
        if has_new:
            op.drop_constraint(_NEW_UQ, _TABLE, type_="unique")
        op.create_unique_constraint(_PG_OLD_UQ, _TABLE, ["wanted_item_id"])
        op.drop_column(_TABLE, "source_language")
        op.drop_column(_TABLE, "task_type")
    else:
        with op.batch_alter_table(_TABLE, naming_convention=_SQLITE_NAMING) as batch:
            if has_new:
                batch.drop_constraint(_NEW_UQ, type_="unique")
            batch.create_unique_constraint(_SQLITE_OLD_UQ, ["wanted_item_id"])
            if "source_language" in columns:
                batch.drop_column("source_language")
            batch.drop_column("task_type")
