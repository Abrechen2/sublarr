"""add_marketplace_tables

Revision ID: a2b3c4d5e6f7
Revises: d1e2f3a4b5c6
Create Date: 2026-03-11

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a2b3c4d5e6f7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "marketplace_cache",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("author", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("version", sa.String(length=50), nullable=False, server_default="0.0.0"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("github_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("zip_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("sha256", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("capabilities", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("min_sublarr_version", sa.String(length=50), nullable=False, server_default=""),
        sa.Column("is_official", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_fetched", sa.Text(), nullable=False, server_default=sa.text("current_timestamp")),
        sa.PrimaryKeyConstraint("name"),
    )

    op.create_table(
        "installed_plugins",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("version", sa.String(length=50), nullable=False, server_default="0.0.0"),
        sa.Column("plugin_dir", sa.Text(), nullable=False, server_default=""),
        sa.Column("sha256", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("capabilities", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("enabled", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("installed_at", sa.Text(), nullable=False, server_default=sa.text("current_timestamp")),
        sa.PrimaryKeyConstraint("name"),
    )


def downgrade():
    op.drop_table("installed_plugins")
    op.drop_table("marketplace_cache")
