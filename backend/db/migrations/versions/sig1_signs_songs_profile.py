"""Language profile: prefer signs & songs, download full subtitles

Revision ID: sig1_signs_songs
Revises: enc2_newly_sensitive

Two switches replace forced_scoring for the regular item, which now only
takes full dialogue subtitles. A profile that said forced_scoring "only"
(forced instead of full) gets download_full off and [Forced] items on; one
that said "prefer" gets [Forced] items on. forced_scoring itself is kept,
unused, so a downgrade loses nothing.
"""

import sqlalchemy as sa
from alembic import op

revision = "sig1_signs_songs"
down_revision = "enc2_newly_sensitive"
branch_labels = None
depends_on = None


def upgrade():
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("language_profiles")}
    with op.batch_alter_table("language_profiles") as batch_op:
        if "prefer_signs" not in existing:
            batch_op.add_column(
                sa.Column("prefer_signs", sa.Integer(), nullable=False, server_default="0")
            )
        if "download_full" not in existing:
            batch_op.add_column(
                sa.Column("download_full", sa.Integer(), nullable=False, server_default="1")
            )

    profiles = sa.table(
        "language_profiles",
        sa.column("forced_scoring", sa.Text()),
        sa.column("forced_preference", sa.Text()),
        sa.column("download_full", sa.Integer()),
    )
    op.execute(profiles.update().where(profiles.c.forced_scoring == "only").values(download_full=0))
    op.execute(
        profiles.update()
        .where(profiles.c.forced_scoring.in_(("only", "prefer")))
        .where(
            sa.or_(
                profiles.c.forced_preference.is_(None),
                profiles.c.forced_preference.in_(("disabled", "auto")),
            )
        )
        .values(forced_preference="separate")
    )


def downgrade():
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("language_profiles")}
    with op.batch_alter_table("language_profiles") as batch_op:
        if "download_full" in existing:
            batch_op.drop_column("download_full")
        if "prefer_signs" in existing:
            batch_op.drop_column("prefer_signs")
