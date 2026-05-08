"""add successful_searches column to provider_stats

Revision ID: b8e3f2a1c5d6
Revises: a7f2e1c9d3b4
Create Date: 2026-05-08 21:00:00+00:00

Background
----------
The 2026-05-08 functional audit found that ``success_rate`` exposed by
``/providers/health`` is computed from ``successful_downloads /
total_searches``. ``successful_downloads`` is only incremented after a
user actually downloads a sub from that provider — not when the
provider returned results. Providers like ``subdl`` showed 0% success
across 26482 searches, even though the engine was getting hits but
choosing a higher-ranked result from another provider.

This split the metric into two:

  * ``download_rate`` = successful_downloads / total_searches  (existing)
  * ``result_rate``   = successful_searches  / total_searches  (new)

``successful_searches`` is incremented by ``record_search(success=True)``
which fires whenever the provider returns at least one usable result.
Backfill leaves the column at 0 — historical data is unrecoverable, so
the new metric warms up over the next runtime window.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b8e3f2a1c5d6"
down_revision = "a7f2e1c9d3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("provider_stats")}
    if "successful_searches" not in cols:
        op.add_column(
            "provider_stats",
            sa.Column(
                "successful_searches",
                sa.Integer(),
                nullable=True,
                server_default="0",
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("provider_stats")}
    if "successful_searches" in cols:
        op.drop_column("provider_stats", "successful_searches")
