"""translation events

Revision ID: 7e085763f714
Revises: dc8da0c509a8
Create Date: 2026-04-19

"""

import sqlalchemy as sa
from alembic import op

revision = "7e085763f714"
down_revision = "dc8da0c509a8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "translation_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("backend", sa.String(32), nullable=False),
        sa.Column("source_lang", sa.String(16), nullable=False),
        sa.Column("target_lang", sa.String(16), nullable=False),
        sa.Column("lines_count", sa.Integer, nullable=False),
        sa.Column("chars_in", sa.Integer, nullable=False),
        sa.Column("chars_out", sa.Integer, nullable=True),
        sa.Column("tokens_in", sa.Integer, nullable=True),
        sa.Column("tokens_out", sa.Integer, nullable=True),
        sa.Column(
            "cost_estimate_micro_usd",
            sa.BigInteger,
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "cache_hit",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_type", sa.String(128), nullable=True),
        sa.Column("error_msg", sa.Text, nullable=True),
        sa.Column("job_id", sa.String(32), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_translation_events_backend_started_at",
        "translation_events",
        ["backend", "started_at"],
    )
    op.create_index(
        "ix_translation_events_started_at",
        "translation_events",
        ["started_at"],
    )
    op.create_index(
        "ix_translation_events_status",
        "translation_events",
        ["status"],
    )
    op.create_index(
        "ix_translation_events_job_id",
        "translation_events",
        ["job_id"],
    )

    # Add backend column to translation_memory (existing table)
    op.add_column(
        "translation_memory",
        sa.Column("backend", sa.String(32), nullable=True),
    )


def downgrade():
    op.drop_column("translation_memory", "backend")
    op.drop_index(
        "ix_translation_events_job_id", table_name="translation_events"
    )
    op.drop_index(
        "ix_translation_events_status", table_name="translation_events"
    )
    op.drop_index(
        "ix_translation_events_started_at", table_name="translation_events"
    )
    op.drop_index(
        "ix_translation_events_backend_started_at",
        table_name="translation_events",
    )
    op.drop_table("translation_events")
