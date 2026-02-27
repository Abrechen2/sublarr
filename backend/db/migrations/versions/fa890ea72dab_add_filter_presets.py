"""add_filter_presets

Revision ID: fa890ea72dab
Revises:
Create Date: 2026-02-19

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "fa890ea72dab"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "filter_presets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("scope", sa.String(length=50), nullable=False),
        sa.Column("conditions", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("is_default", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_filter_presets_scope", "filter_presets", ["scope"])


def downgrade():
    op.drop_index("idx_filter_presets_scope", table_name="filter_presets")
    op.drop_table("filter_presets")
