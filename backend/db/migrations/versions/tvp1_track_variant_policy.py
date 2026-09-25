"""Track variant policy: override columns + per-track sweep verdicts (schema only).

Adds nullable columns and the ``sidecar_origins`` table; no existing data is
rewritten. Untracked databases receive the same columns through
app._patch_pre_alembic_columns, and the new table through create_all() (it
is a plain new table, not a column added to one that already exists).

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

_SIDECAR_ORIGINS_INDEX = "idx_sidecar_origins_video_lang"


def _has(table: str, column: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return column in {c["name"] for c in insp.get_columns(table)}


def _has_table(table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    for table in ("series_settings", "movie_settings"):
        with op.batch_alter_table(table) as batch:
            for name, type_ in _OVERRIDES:
                if not _has(table, name):
                    batch.add_column(sa.Column(name, type_, nullable=True))
    if not _has("foreign_track_scan", "track_verdicts"):
        with op.batch_alter_table("foreign_track_scan") as batch:
            batch.add_column(sa.Column("track_verdicts", sa.Text(), nullable=True))
    if not _has_table("sidecar_origins"):
        op.create_table(
            "sidecar_origins",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("video_path", sa.Text(), nullable=False),
            sa.Column("language", sa.String(8), nullable=False),
            sa.Column("origin", sa.String(20), nullable=False),
            sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(_SIDECAR_ORIGINS_INDEX, "sidecar_origins", ["video_path", "language"])


def downgrade() -> None:
    if _has_table("sidecar_origins"):
        op.drop_index(_SIDECAR_ORIGINS_INDEX, table_name="sidecar_origins")
        op.drop_table("sidecar_origins")
    with op.batch_alter_table("foreign_track_scan") as batch:
        batch.drop_column("track_verdicts")
    for table in ("series_settings", "movie_settings"):
        with op.batch_alter_table(table) as batch:
            for name, _ in reversed(_OVERRIDES):
                batch.drop_column(name)
