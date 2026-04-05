"""Add activity_log table for unified event tracking.

Revision ID: e4f5a6b7c8d9
Revises: merge_c6d7_f0e1
Create Date: 2026-04-05

"""

import sqlalchemy as sa
from alembic import op

revision = "e4f5a6b7c8d9"
down_revision = "merge_c6d7_f0e1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "activity_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="success"),
        sa.Column("details_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_activity_log_event_type", "activity_log", ["event_type"])
    op.create_index("idx_activity_log_created_at", "activity_log", ["created_at"])


def downgrade():
    op.drop_index("idx_activity_log_created_at", table_name="activity_log")
    op.drop_index("idx_activity_log_event_type", table_name="activity_log")
    op.drop_table("activity_log")
