"""Phase 4a follow-up: re-add wanted_items.sonarr_series_id index.

Dropped in h1i2j3k4l5m6 as unused, but Phase 4a Task 6 now LEFT JOINs
series_settings on this column in get_items_for_scheduled_search. Without
the index the join degrades to a seq scan at prod scale.

Revision ID: p4a_readd_wanted_sonarr_idx
Revises: p4a_pools_and_overrides
Create Date: 2026-04-17 00:00:00
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect

revision = "p4a_readd_wanted_sonarr_idx"
down_revision = "p4a_pools_and_overrides"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    existing = {ix["name"] for ix in insp.get_indexes("wanted_items")}
    if "idx_wanted_sonarr_series" not in existing:
        op.create_index(
            "idx_wanted_sonarr_series",
            "wanted_items",
            ["sonarr_series_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    existing = {ix["name"] for ix in insp.get_indexes("wanted_items")}
    if "idx_wanted_sonarr_series" in existing:
        op.drop_index("idx_wanted_sonarr_series", table_name="wanted_items")
