"""Add dubtitle_detections cache table (roadmap A4 / issue #146).

Caches the dubtitle-detection result per video (keyed by file_path,
invalidated by mtime) so the UI can render the flag without re-running
detection and a scheduled sweep skips files it has already seen.

Revision ID: f3a4b5c6d7e8
Revises: b8e3f2a1c5d6
Create Date: 2026-06-14
"""

import sqlalchemy as sa
from alembic import op

revision = "f3a4b5c6d7e8"
down_revision = "b8e3f2a1c5d6"
branch_labels = None
depends_on = None


def upgrade():
    # Idempotent: on a fresh DB create_all() already built the table from the
    # ORM model, so skip the CREATE rather than collide. On an existing DB
    # (the normal upgrade path) the table is absent and gets created here.
    if sa.inspect(op.get_bind()).has_table("dubtitle_detections"):
        return
    op.create_table(
        "dubtitle_detections",
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("mtime", sa.Float(), nullable=False),
        sa.Column("dubtitle_sub_index", sa.Integer(), nullable=True),
        sa.Column("method", sa.Text(), nullable=False, server_default="none"),
        sa.Column("result_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("file_path"),
    )


def downgrade():
    if not sa.inspect(op.get_bind()).has_table("dubtitle_detections"):
        return
    op.drop_table("dubtitle_detections")
