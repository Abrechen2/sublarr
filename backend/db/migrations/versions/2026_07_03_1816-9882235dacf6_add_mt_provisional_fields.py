"""add_mt_provisional_fields

Revision ID: 9882235dacf6
Revises: c9d0e1f2a3b4
Create Date: 2026-07-03 18:16:28.020591+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "9882235dacf6"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade():
    # Idempotent: skip columns that already exist so this migration is safe to
    # re-run and coexists with a create_all()-seeded schema (test fixtures do
    # create_all() then upgrade head — see test_migrations_profiles_overrides).
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("language_profiles")}
    with op.batch_alter_table("language_profiles") as batch_op:
        if "mt_keep_seeking_original" not in existing:
            batch_op.add_column(
                sa.Column(
                    "mt_keep_seeking_original", sa.Integer(), nullable=False, server_default="0"
                )
            )
        if "mt_on_original_found" not in existing:
            batch_op.add_column(
                sa.Column(
                    "mt_on_original_found", sa.Text(), nullable=False, server_default="notify"
                )
            )
        if "mt_min_original_score" not in existing:
            batch_op.add_column(
                sa.Column("mt_min_original_score", sa.Integer(), nullable=False, server_default="1")
            )


def downgrade():
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("language_profiles")}
    with op.batch_alter_table("language_profiles") as batch_op:
        if "mt_min_original_score" in existing:
            batch_op.drop_column("mt_min_original_score")
        if "mt_on_original_found" in existing:
            batch_op.drop_column("mt_on_original_found")
        if "mt_keep_seeking_original" in existing:
            batch_op.drop_column("mt_keep_seeking_original")
