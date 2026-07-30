"""add enabled_providers_json + scoring_preset to language_profiles

Provider profiles (feature request "Regel-Engine und Profile"): a language
profile can now carry its own provider selection and its own scoring preset.
NULL in either column means "inherit the global setting", so existing rows
keep today's behaviour unchanged.

Guarded with column inspection: the schema is also created straight from the
models via create_all() (fresh installs, the test harness), so the migration
must be a no-op when the columns are already there.

Revision ID: f8b2c3d4e5a6
Revises: e7a1b2c3d4f5
Create Date: 2026-07-30
"""

import sqlalchemy as sa
from alembic import op

revision = "f8b2c3d4e5a6"
down_revision = "e7a1b2c3d4f5"
branch_labels = None
depends_on = None

_TABLE = "language_profiles"


def _existing_columns(bind) -> set[str]:
    insp = sa.inspect(bind)
    if not insp.has_table(_TABLE):
        return set()
    return {c["name"] for c in insp.get_columns(_TABLE)}


def upgrade() -> None:
    bind = op.get_bind()
    cols = _existing_columns(bind)
    if not cols:
        return  # table created by create_all() with the new columns already

    to_add = []
    if "enabled_providers_json" not in cols:
        to_add.append(sa.Column("enabled_providers_json", sa.Text(), nullable=True))
    if "scoring_preset" not in cols:
        to_add.append(sa.Column("scoring_preset", sa.Text(), nullable=True))
    if not to_add:
        return

    with op.batch_alter_table(_TABLE) as batch_op:
        for col in to_add:
            batch_op.add_column(col)


def downgrade() -> None:
    bind = op.get_bind()
    cols = _existing_columns(bind)

    with op.batch_alter_table(_TABLE) as batch_op:
        if "scoring_preset" in cols:
            batch_op.drop_column("scoring_preset")
        if "enabled_providers_json" in cols:
            batch_op.drop_column("enabled_providers_json")
