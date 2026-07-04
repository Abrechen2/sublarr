"""add_stats_daily_rollup

Creates the stats_daily_rollup table (V1.6 #9). Idempotent so it coexists with a
create_all()-seeded schema (test fixtures create_all() then upgrade head) and is
safe to re-run.

Revision ID: b7e2f4a1c8d3
Revises: a3c1e5b7d9f0
Create Date: 2026-07-04 12:00:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b7e2f4a1c8d3"
down_revision = "a3c1e5b7d9f0"
branch_labels = None
depends_on = None


def upgrade():
    if "stats_daily_rollup" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "stats_daily_rollup",
        sa.Column("date", sa.String(length=10), primary_key=True),
        sa.Column("downloads", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("translations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("syncs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("translation_chars", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "translation_cost_micro_usd", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column("by_source_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("by_provider_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("by_language_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    if "stats_daily_rollup" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("stats_daily_rollup")
