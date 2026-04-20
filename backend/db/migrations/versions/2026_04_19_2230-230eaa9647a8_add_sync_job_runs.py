"""add sync_job_runs table

Revision ID: 230eaa9647a8
Revises: fc4d6e530cb1
Create Date: 2026-04-19 22:30:00
"""

import sqlalchemy as sa
from alembic import op

revision = "230eaa9647a8"
down_revision = "fc4d6e530cb1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("sync_job_runs"):
        op.create_table(
            "sync_job_runs",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("engine", sa.String(length=32), nullable=False),
            sa.Column("offset_ms", sa.Integer, nullable=True),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("duration_ms", sa.Integer, nullable=False),
            sa.Column("subtitle_path", sa.Text, nullable=True),
            sa.Column("video_path", sa.Text, nullable=True),
            sa.Column("reason", sa.String(length=64), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
    op.create_index(
        "idx_sync_runs_created_at",
        "sync_job_runs",
        ["created_at"],
        if_not_exists=True,
    )
    op.create_index(
        "idx_sync_runs_engine",
        "sync_job_runs",
        ["engine"],
        if_not_exists=True,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("sync_job_runs"):
        op.drop_index("idx_sync_runs_engine", table_name="sync_job_runs")
        op.drop_index("idx_sync_runs_created_at", table_name="sync_job_runs")
        op.drop_table("sync_job_runs")
