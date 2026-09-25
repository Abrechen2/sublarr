"""Run data migrations on databases Alembic does not track — once each.

A database first created by ``create_all()`` has no ``alembic_version`` table,
so app startup takes the create_all branch on every start and never runs a
migration. Schema changes reach it through ``_patch_pre_alembic_columns``; data
migrations reached it not at all. Found by the VM test of 1.14.3-rc.2: a
poisoned ``ollama de -> en`` translation-memory entry survived the upgrade and
kept serving German for English, undoing the prompt fix on those installs.

Each registered repair is the same function its Alembic migration calls, and
runs exactly once per database: the repair and its marker row in
``untracked_data_repairs`` are written in one transaction. Once matters —
``tm4_wrong_direction`` deletes Ollama entries for a non-configured target, and
after the fix such entries are correct, so re-running it on every start would
destroy good data. A repair that fails is logged, leaves no marker and is
retried on the next start; it never blocks startup.

Tracked databases do not use this module; Alembic records the same revisions.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

import sqlalchemy as sa

logger = logging.getLogger(__name__)

MARKER_TABLE = "untracked_data_repairs"


def _tm1(conn) -> int:
    from db.migrations.versions.tm1_strip_invented_hard_breaks import strip_breaks

    return strip_breaks(conn)


def _tm2(conn) -> int:
    from db.migrations.versions.tm2_drop_same_language_entries import drop_same_language

    return drop_same_language(conn)


def _tm3(conn) -> int:
    from db.migrations.versions.tm3_strip_invented_soft_breaks import strip_breaks

    return strip_breaks(conn)


def _tm4(conn) -> int:
    from db.migrations.versions.tm4_drop_wrong_direction_ollama import (
        configured_target_language,
        drop_wrong_direction,
    )

    return drop_wrong_direction(conn, configured_target_language(conn))


def _wq1(conn) -> int:
    from db.migrations.versions.wq1_refund_unanswered_searches import (
        configured_max_attempts,
        refund_unanswered,
    )

    return refund_unanswered(conn, configured_max_attempts(conn))


# (Alembic revision id, repair) — in migration order. Add every future data
# migration here as well, or untracked installs never receive it.
REPAIRS: list[tuple[str, Callable]] = [
    ("tm1_strip_breaks", _tm1),
    ("tm2_drop_same_lang", _tm2),
    ("tm3_strip_soft", _tm3),
    ("tm4_wrong_direction", _tm4),
    ("wq1_refund_unanswered", _wq1),
]


def _ensure_marker_table(engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                f"CREATE TABLE IF NOT EXISTS {MARKER_TABLE} "
                "(revision VARCHAR(64) PRIMARY KEY, applied_at VARCHAR(40) NOT NULL, "
                "affected INTEGER NOT NULL)"
            )
        )


def apply_untracked_data_repairs(engine) -> dict[str, int]:
    """Apply every repair not yet recorded; return ``{revision: rows affected}``."""
    _ensure_marker_table(engine)
    with engine.connect() as conn:
        done = {row[0] for row in conn.execute(sa.text(f"SELECT revision FROM {MARKER_TABLE}"))}

    applied: dict[str, int] = {}
    for revision, repair in REPAIRS:
        if revision in done:
            continue
        try:
            with engine.begin() as conn:
                affected = int(repair(conn) or 0)
                conn.execute(
                    sa.text(
                        f"INSERT INTO {MARKER_TABLE} (revision, applied_at, affected) "
                        "VALUES (:revision, :applied_at, :affected)"
                    ),
                    {
                        "revision": revision,
                        "applied_at": datetime.now(UTC).isoformat(),
                        "affected": affected,
                    },
                )
        except Exception:
            logger.warning(
                "Untracked DB: data repair %s failed; will retry on next start",
                revision,
                exc_info=True,
            )
            continue
        applied[revision] = affected
        logger.info("Untracked DB: applied data repair %s (%d rows)", revision, affected)
    return applied
