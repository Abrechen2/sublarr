"""resurrect legacy_frozen wanted items (v2)

Revision ID: a7f2e1c9d3b4
Revises: f3d8e9c2a4b1
Create Date: 2026-05-06 18:30:00+00:00

Background
----------
The 2026-04-27 migration ``f3d8e9c2a4b1`` retroactively converted the
legacy "freeze forever" cohort into slow-mode. A 2026-05-06 production
audit found 2005 fresh wanted_items in the same state — items that
reached ``search_count = wanted_max_search_attempts`` between
2026-05-02 and 2026-05-04 with ``failure_kind=NULL`` and
``retry_after=NULL``. Cause: ``process_wanted_item`` bumped
``search_count`` via ``update_wanted_search`` at the start of every run
but the ``_fallback_translate_file`` ``auto_translate=False`` branch
never funnelled through ``record_search_outcome`` to set the
slow-mode markers.

The companion code fix routes that branch through
``record_search_outcome("no_result")``, which sets ``failure_kind`` and
``retry_after`` correctly. This migration reapplies the same UPDATE as
``f3d8e9c2a4b1`` to the rows that already slipped through.

Idempotent: the WHERE clause excludes anything already in slow-mode or
with a populated ``retry_after``. Re-running on a healthy database is a
no-op.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a7f2e1c9d3b4"
down_revision = "f3d8e9c2a4b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.execute(
            sa.text(
                """
                UPDATE wanted_items
                SET failure_kind = 'no_result_slow',
                    retry_after = NOW() + ((id % 30) * INTERVAL '1 day')
                WHERE status = 'wanted'
                  AND search_count >= 3
                  AND retry_after IS NULL
                  AND failure_kind IS NULL
                """
            )
        )
    else:
        op.execute(
            sa.text(
                """
                UPDATE wanted_items
                SET failure_kind = 'no_result_slow',
                    retry_after = datetime('now', '+' || (id % 30) || ' days')
                WHERE status = 'wanted'
                  AND search_count >= 3
                  AND retry_after IS NULL
                  AND failure_kind IS NULL
                """
            )
        )


def downgrade() -> None:
    """Mirror of ``f3d8e9c2a4b1``: only undo rows we marked here.

    We can't tell apart items already in slow-mode before this migration
    from items we just promoted, so the WHERE is intentionally narrow —
    it only clears the marker on rows whose retry_after is still in the
    future window we set (≤ 30 days from now).
    """
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.execute(
            sa.text(
                """
                UPDATE wanted_items
                SET failure_kind = NULL,
                    retry_after = NULL
                WHERE status = 'wanted'
                  AND search_count >= 3
                  AND failure_kind = 'no_result_slow'
                  AND retry_after IS NOT NULL
                  AND retry_after <= NOW() + INTERVAL '30 days'
                """
            )
        )
    else:
        op.execute(
            sa.text(
                """
                UPDATE wanted_items
                SET failure_kind = NULL,
                    retry_after = NULL
                WHERE status = 'wanted'
                  AND search_count >= 3
                  AND failure_kind = 'no_result_slow'
                  AND retry_after IS NOT NULL
                  AND retry_after <= datetime('now', '+30 days')
                """
            )
        )
