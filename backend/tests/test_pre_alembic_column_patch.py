"""Regression: an Alembic-untracked DB must gain the columns migrations added.

``create_all()`` adds missing *tables* but never missing *columns*, so a
database that was first built that way never gets an ``alembic_version`` and
takes the create_all branch on every start for the rest of its life. Its only
route to a column a later migration introduced is
``_patch_pre_alembic_columns``.

app.py states the rule outright — "A column added by a migration MUST be
repeated here" — but nothing enforced it. The three columns the automation
queue gained on 2026-08-14/16 (``task_type``, ``source_language``,
``video_path``) were never added, so every untracked install ran 1.13.x with a
queue table the ORM could not query: the drain worker died at boot with
``no such column: subtitle_automation_queue.task_type``. Observed on the beta
instance on 2026-08-28, the second time this class of drift took it down.
"""

from __future__ import annotations

import sqlalchemy as sa

# The shape the table had before the 2026-08-14 migration, taken verbatim from
# an install that predates it.
_PRE_MIGRATION_QUEUE_DDL = """
CREATE TABLE subtitle_automation_queue (
    id INTEGER NOT NULL,
    wanted_item_id INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    target_language VARCHAR(8) NOT NULL,
    state VARCHAR(10) NOT NULL,
    attempt_count INTEGER NOT NULL,
    next_retry_at DATETIME,
    last_error TEXT,
    last_started_at DATETIME,
    last_finished_at DATETIME,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (wanted_item_id)
)
"""


def _model_columns(table_name: str) -> set[str]:
    import db.models  # noqa: F401  — registers the models on the metadata
    from extensions import db as sa_db

    return {c.name for c in sa_db.metadata.tables[table_name].columns}


def test_patcher_restores_columns_migrations_added(tmp_path):
    from app import _patch_pre_alembic_columns

    engine = sa.create_engine(f"sqlite:///{tmp_path / 'untracked.db'}")
    with engine.begin() as conn:
        conn.execute(sa.text(_PRE_MIGRATION_QUEUE_DDL))

    _patch_pre_alembic_columns(engine, sa.inspect)

    present = {c["name"] for c in sa.inspect(engine).get_columns("subtitle_automation_queue")}
    missing = _model_columns("subtitle_automation_queue") - present
    assert not missing, f"untracked DB still misses columns the ORM queries: {sorted(missing)}"


def test_patcher_is_idempotent(tmp_path):
    """Running twice must not fail — it runs on every start of an untracked DB."""
    from app import _patch_pre_alembic_columns

    engine = sa.create_engine(f"sqlite:///{tmp_path / 'untracked.db'}")
    with engine.begin() as conn:
        conn.execute(sa.text(_PRE_MIGRATION_QUEUE_DDL))

    _patch_pre_alembic_columns(engine, sa.inspect)
    _patch_pre_alembic_columns(engine, sa.inspect)

    present = {c["name"] for c in sa.inspect(engine).get_columns("subtitle_automation_queue")}
    assert "task_type" in present
