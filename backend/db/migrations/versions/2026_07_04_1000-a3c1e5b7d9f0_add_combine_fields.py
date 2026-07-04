"""add_combine_fields

Adds the per-profile combined-subtitle config columns to language_profiles
(V1.6 Feature #1). Additive + idempotent so it coexists with a create_all()-
seeded schema (test fixtures create_all() then upgrade head) and is safe to
re-run.

Revision ID: a3c1e5b7d9f0
Revises: 9882235dacf6
Create Date: 2026-07-04 10:00:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a3c1e5b7d9f0"
down_revision = "9882235dacf6"
branch_labels = None
depends_on = None

_DEFAULT_POSITION = '{"primary": "bottom", "secondary": "top"}'


def upgrade():
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("language_profiles")}
    with op.batch_alter_table("language_profiles") as batch_op:
        if "combine_enabled" not in existing:
            batch_op.add_column(
                sa.Column("combine_enabled", sa.Integer(), nullable=False, server_default="0")
            )
        if "combine_format" not in existing:
            batch_op.add_column(
                sa.Column("combine_format", sa.Text(), nullable=False, server_default="ass")
            )
        if "combine_languages_json" not in existing:
            batch_op.add_column(
                sa.Column("combine_languages_json", sa.Text(), nullable=False, server_default="[]")
            )
        if "combine_position_json" not in existing:
            batch_op.add_column(
                sa.Column(
                    "combine_position_json",
                    sa.Text(),
                    nullable=False,
                    server_default=_DEFAULT_POSITION,
                )
            )


def downgrade():
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("language_profiles")}
    with op.batch_alter_table("language_profiles") as batch_op:
        if "combine_position_json" in existing:
            batch_op.drop_column("combine_position_json")
        if "combine_languages_json" in existing:
            batch_op.drop_column("combine_languages_json")
        if "combine_format" in existing:
            batch_op.drop_column("combine_format")
        if "combine_enabled" in existing:
            batch_op.drop_column("combine_enabled")
