"""Widen the automation-queue unique key to include file_path.

`uq_automation_queue_item_task` keyed queue rows on
`(wanted_item_id, task_type)`. That held while every task type belonged to
a wanted item that outlived its row. `auto_sync` does not: it is enqueued on
the line before `delete_wanted_item(item_id)` in two of its four call sites,
and SQLite hands the freed rowid to the next inserted item. The next item to
inherit that id would find a still-pending sync under its own key and, since
`enqueue` returns an existing pending row unchanged, lose its sync without a
word. The database constraint made the application-level fix impossible on
its own — the insert would simply have failed instead.

`file_path` is what the work is about, so it joins the key. For the two older
task types this is a no-op in practice: one item has one video to extract from
and one source sidecar to translate. Should a path ever change under them, the
result is a second row rather than a silent update, and the stale one fails
once with FileNotFoundError and is dropped — a path the runner already handles.

Revision ID: d5b3c8a1f742
Revises: c7e1a9d4b6f3
Create Date: 2026-08-16

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision = "d5b3c8a1f742"
down_revision = "c7e1a9d4b6f3"
branch_labels = None
depends_on = None

_TABLE = "subtitle_automation_queue"
_OLD_UQ = "uq_automation_queue_item_task"
_NEW_UQ = "uq_automation_queue_item_task_file"
_OLD_COLS = ["wanted_item_id", "task_type"]
_NEW_COLS = ["wanted_item_id", "task_type", "file_path"]

# SQLite reflects a constraint it created inline with no name at all. Inside
# batch mode this convention is what lets drop_constraint address it.
_SQLITE_NAMING = {"uq": "uq_%(table_name)s_%(column_0_name)s"}


def _uniques(bind) -> list[dict]:
    return sa.inspect(bind).get_unique_constraints(_TABLE)


def _matching(bind, columns: list[str]) -> list[dict]:
    """Reflected UNIQUE constraints covering exactly ``columns``, in any order."""
    want = sorted(columns)
    return [u for u in _uniques(bind) if sorted(u.get("column_names") or []) == want]


def _migrate(bind, drop: list[dict], create_name: str, create_cols: list[str]) -> None:
    if bind.dialect.name == "postgresql":
        for uq in drop:
            op.drop_constraint(uq["name"] or _OLD_UQ, _TABLE, type_="unique")
        op.create_unique_constraint(create_name, _TABLE, create_cols)
        return
    with op.batch_alter_table(_TABLE, naming_convention=_SQLITE_NAMING) as batch:
        for uq in drop:
            batch.drop_constraint(uq["name"] or _OLD_UQ, type_="unique")
        batch.create_unique_constraint(create_name, create_cols)


def upgrade() -> None:
    bind = op.get_bind()
    if _TABLE not in sa.inspect(bind).get_table_names():
        return
    if _matching(bind, _NEW_COLS):
        # Schema built from the current model metadata rather than by replaying
        # migrations — a fresh install is already the shape we want.
        return
    _migrate(bind, _matching(bind, _OLD_COLS), _NEW_UQ, _NEW_COLS)


def downgrade() -> None:
    bind = op.get_bind()
    if _TABLE not in sa.inspect(bind).get_table_names():
        return
    if not _matching(bind, _NEW_COLS):
        return
    # The narrower key cannot hold while rows only the wider one allowed are
    # present, so one row per (wanted_item_id, task_type) has to go. Which one
    # is not arbitrary: keeping the oldest would routinely keep a `done` row —
    # history — and delete the `pending` row next to it that still has work in
    # it. Rank by how much is still owed on the row instead, newest first
    # within a state, since a newer row carries the newer paths.
    op.execute(
        f"DELETE FROM {_TABLE} WHERE id NOT IN ("  # noqa: S608 — constant table name
        "SELECT keep_id FROM (SELECT id AS keep_id, ROW_NUMBER() OVER ("
        "PARTITION BY wanted_item_id, task_type ORDER BY CASE state "
        "WHEN 'running' THEN 0 WHEN 'pending' THEN 1 WHEN 'failed' THEN 2 "
        f"ELSE 3 END, id DESC) AS rn FROM {_TABLE}) ranked WHERE rn = 1)"
    )
    _migrate(bind, _matching(bind, _NEW_COLS), _OLD_UQ, _OLD_COLS)
