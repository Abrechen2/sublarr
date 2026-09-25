"""Track variant policy: override columns + per-track sweep verdicts (schema only).

Adds nullable columns; no data is rewritten. Untracked databases receive the
same columns through app._patch_pre_alembic_columns.

Revision ID: tvp1_track_variant_policy
Revises: wq1_refund_unanswered
"""

import sqlalchemy as sa
from alembic import op

revision = "tvp1_track_variant_policy"
down_revision = "wq1_refund_unanswered"
branch_labels = None
depends_on = None

_OVERRIDES = (
    ("cleanup_track_variant_mode", sa.String(20)),
    ("cleanup_keep_forced", sa.Boolean()),
    ("cleanup_keep_sdh", sa.Boolean()),
    ("cleanup_sidecar_policy", sa.String(24)),
)


def _has(table: str, column: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    for table in ("series_settings", "movie_settings"):
        with op.batch_alter_table(table) as batch:
            for name, type_ in _OVERRIDES:
                if not _has(table, name):
                    batch.add_column(sa.Column(name, type_, nullable=True))
    if not _has("foreign_track_scan", "track_verdicts"):
        with op.batch_alter_table("foreign_track_scan") as batch:
            batch.add_column(sa.Column("track_verdicts", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("foreign_track_scan") as batch:
        batch.drop_column("track_verdicts")
    for table in ("series_settings", "movie_settings"):
        with op.batch_alter_table(table) as batch:
            for name, _ in reversed(_OVERRIDES):
                batch.drop_column(name)
