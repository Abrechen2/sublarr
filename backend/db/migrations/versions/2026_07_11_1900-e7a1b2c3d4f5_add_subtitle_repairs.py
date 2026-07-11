"""add subtitle_repairs — record of subtitles restored after the HI-removal data loss

Repair rewrites a damaged sidecar back to its provider original, so afterwards it
no longer matches the pristine hash in subtitle_hashes — which is the very signal
the scanner uses to detect damage. Without this table every repaired file would
look damaged again on the next scan and be re-downloaded forever, burning the
provider's daily quota. Storing the post-repair hash also lets a hand edit made
*after* a repair be told apart from damage.

Guarded with has_table/has_index: the schema is also created straight from the
models via create_all() (fresh installs, the test harness), so the migration must
be a no-op when the table is already there.

Revision ID: e7a1b2c3d4f5
Revises: 3c4b1a2d5e6f
Create Date: 2026-07-11
"""

import sqlalchemy as sa
from alembic import op

revision = "e7a1b2c3d4f5"
down_revision = "3c4b1a2d5e6f"
branch_labels = None
depends_on = None


def _has_table(bind, table: str) -> bool:
    return sa.inspect(bind).has_table(table)


def _has_index(bind, table: str, index: str) -> bool:
    insp = sa.inspect(bind)
    if not insp.has_table(table):
        return False
    return index in {i["name"] for i in insp.get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_table(bind, "subtitle_repairs"):
        op.create_table(
            "subtitle_repairs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("file_path", sa.Text(), nullable=False),
            sa.Column("original_hash", sa.String(length=64), nullable=False),
            sa.Column("repaired_hash", sa.String(length=64), nullable=False),
            sa.Column("provider_name", sa.String(length=50), nullable=True),
            sa.Column("subtitle_id", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="repaired"),
            sa.Column("repaired_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("file_path"),
        )

    if not _has_index(bind, "subtitle_repairs", "idx_subtitle_repairs_status"):
        op.create_index("idx_subtitle_repairs_status", "subtitle_repairs", ["status"])


def downgrade() -> None:
    bind = op.get_bind()

    if _has_index(bind, "subtitle_repairs", "idx_subtitle_repairs_status"):
        op.drop_index("idx_subtitle_repairs_status", table_name="subtitle_repairs")
    if _has_table(bind, "subtitle_repairs"):
        op.drop_table("subtitle_repairs")
