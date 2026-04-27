"""resurrect dead-end wanted items via slow-mode

Revision ID: f3d8e9c2a4b1
Revises: 506332eef4f7
Create Date: 2026-04-27 18:15:00+00:00

Background
----------
Items that hit ``wanted_max_search_attempts`` before the slow-mode landing
(commit history pre-0.71.x) are stuck with ``search_count >= 3``,
``retry_after IS NULL`` and ``failure_kind IS NULL``. ``_filter_eligible``
(post slow-mode fix) honours ``failure_kind='no_result_slow'`` + a populated
``retry_after`` to bypass the cap, so this migration retroactively converts
the legacy frozen items into the slow-mode contract.

The retry instants are spread over the next 30 days using ``id % 30`` so
the resurrected items don't all hit the providers in a single search-tick.

Idempotent: WHERE clause excludes anything already in slow-mode or with a
populated ``retry_after``.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "f3d8e9c2a4b1"
down_revision = "506332eef4f7"
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
        # SQLite (dev/test) — emulate the per-id spread.
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
    """Revert: only undoes the rows we marked here.

    We can't tell apart items that were already in slow-mode before this
    migration from items we just promoted, so the WHERE is intentionally
    narrow — it only clears the marker on rows whose retry_after is still
    in the future window we set (≤ 30 days from now). Newer slow-mode
    transitions stay untouched.
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
