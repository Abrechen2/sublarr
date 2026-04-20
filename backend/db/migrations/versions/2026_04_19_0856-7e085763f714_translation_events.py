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


def _has_table(bind, table: str) -> bool:
    return sa.inspect(bind).has_table(table)


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    if not insp.has_table(table):
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def _has_index(bind, table: str, index: str) -> bool:
    insp = sa.inspect(bind)
    if not insp.has_table(table):
        return False
    return index in {i["name"] for i in insp.get_indexes(table)}


def upgrade():
    bind = op.get_bind()

    # Idempotent: skip create_table when create_all() already materialised it.
    if not _has_table(bind, "translation_events"):
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
    for index_name, columns in (
        ("ix_translation_events_backend_started_at", ["backend", "started_at"]),
        ("ix_translation_events_started_at", ["started_at"]),
        ("ix_translation_events_status", ["status"]),
        ("ix_translation_events_job_id", ["job_id"]),
    ):
        if not _has_index(bind, "translation_events", index_name):
            op.create_index(index_name, "translation_events", columns)

    # Add backend column to translation_memory (existing table)
    if not _has_column(bind, "translation_memory", "backend"):
        op.add_column(
            "translation_memory",
            sa.Column("backend", sa.String(32), nullable=True),
        )


def downgrade():
    bind = op.get_bind()
    if _has_column(bind, "translation_memory", "backend"):
        op.drop_column("translation_memory", "backend")
    for index_name in (
        "ix_translation_events_job_id",
        "ix_translation_events_status",
        "ix_translation_events_started_at",
        "ix_translation_events_backend_started_at",
    ):
        if _has_index(bind, "translation_events", index_name):
            op.drop_index(index_name, table_name="translation_events")
    if _has_table(bind, "translation_events"):
        op.drop_table("translation_events")
