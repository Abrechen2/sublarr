"""add post_processing_runs table

Revision ID: fc4d6e530cb1
Revises: 9e36be515063
Create Date: 2026-04-19 21:42:00
"""

from alembic import op
import sqlalchemy as sa

revision = "fc4d6e530cb1"
down_revision = "9e36be515063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "post_processing_runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("trigger", sa.String(length=32), nullable=False),
        sa.Column("ops_executed", sa.JSON, nullable=False),
        sa.Column("duration_ms", sa.Integer, nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_pp_runs_created_at",
        "post_processing_runs",
        ["created_at"],
        if_not_exists=True,
    )
    op.create_index(
        "idx_pp_runs_trigger",
        "post_processing_runs",
        ["trigger"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("idx_pp_runs_trigger", table_name="post_processing_runs")
    op.drop_index("idx_pp_runs_created_at", table_name="post_processing_runs")
    op.drop_table("post_processing_runs")
