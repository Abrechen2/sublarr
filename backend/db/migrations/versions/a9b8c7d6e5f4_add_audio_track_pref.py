"""add_audio_track_pref

Revision ID: a9b8c7d6e5f4
Revises:
Create Date: 2026-03-13

Adds preferred_audio_track_index to series_settings for per-series
Whisper audio track pinning, and audio_track_index to whisper_jobs
for observability.
"""

import sqlalchemy as sa
from alembic import op

revision = "a9b8c7d6e5f4"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("series_settings") as batch_op:
        batch_op.add_column(sa.Column("preferred_audio_track_index", sa.Integer(), nullable=True))
    with op.batch_alter_table("whisper_jobs") as batch_op:
        batch_op.add_column(sa.Column("audio_track_index", sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table("whisper_jobs") as batch_op:
        batch_op.drop_column("audio_track_index")
    with op.batch_alter_table("series_settings") as batch_op:
        batch_op.drop_column("preferred_audio_track_index")
