"""resurrect terminal 'failed' wanted items

Revision ID: b7e4d2c9a1f3
Revises: d5b3c8a1f742
Create Date: 2026-08-21 10:30:00+00:00

Background
----------
The scheduled search selector only ever fetches ``status='wanted'`` rows,
so any wanted item written to ``status='failed'`` was dead forever. Three
automatic writers did exactly that: the Step-5 translate fallback on a
failed translation (prod 2026-08-04: 21 rows buried during an Ollama
outage), its generic exception handler, and the forced-subtitle path when
no provider had a forced sub. The companion code fix routes all three
through ``record_search_outcome`` (``translation_error`` backoff for the
first two, the ``no_result`` tri-state escalation for the forced miss), so
nothing automatic writes ``'failed'`` any more.

This migration resurrects the rows that already died:

- ``search_count >= 3`` (at/over the default attempt cap): slow-mode, same
  treatment as the legacy_frozen resurrections (``a7f2e1c9d3b4``) —
  ``failure_kind='no_result_slow'`` with the retry staggered over 30 days
  so a large cohort does not stampede one tick.
- everything else: ``failure_kind='translation_error'`` on the error-side
  backoff, retry staggered over 48 hours, ``error_count`` at least 1.

Rows a user set to ``'failed'`` manually via the API are indistinguishable
from the buried ones and are resurrected too — after the code fix that
status is manual-only, and a resurrected row simply re-enters the search
rotation with backoff instead of sitting dead. The error text is kept.

Idempotent: the WHERE clause only matches ``status='failed'``; re-running
on a healthy database is a no-op.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b7e4d2c9a1f3"
down_revision = "d5b3c8a1f742"
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
                SET status = 'wanted',
                    failure_kind = 'no_result_slow',
                    retry_after = NOW() + ((id % 30) * INTERVAL '1 day')
                WHERE status = 'failed'
                  AND search_count >= 3
                """
            )
        )
        op.execute(
            sa.text(
                """
                UPDATE wanted_items
                SET status = 'wanted',
                    failure_kind = 'translation_error',
                    error_count = CASE
                        WHEN error_count IS NULL OR error_count = 0 THEN 1
                        ELSE error_count
                    END,
                    retry_after = NOW() + ((id % 48) * INTERVAL '1 hour')
                WHERE status = 'failed'
                """
            )
        )
    else:
        op.execute(
            sa.text(
                """
                UPDATE wanted_items
                SET status = 'wanted',
                    failure_kind = 'no_result_slow',
                    retry_after = datetime('now', '+' || (id % 30) || ' days')
                WHERE status = 'failed'
                  AND search_count >= 3
                """
            )
        )
        op.execute(
            sa.text(
                """
                UPDATE wanted_items
                SET status = 'wanted',
                    failure_kind = 'translation_error',
                    error_count = CASE
                        WHEN error_count IS NULL OR error_count = 0 THEN 1
                        ELSE error_count
                    END,
                    retry_after = datetime('now', '+' || (id % 48) || ' hours')
                WHERE status = 'failed'
                """
            )
        )


def downgrade() -> None:
    """Deliberate no-op.

    Rows resurrected here are indistinguishable from rows the new code path
    marks with the same ``failure_kind`` afterwards — flipping either group
    back to ``'failed'`` would re-bury live items, which is strictly worse
    than leaving a formerly-dead row in the search rotation.
    """
