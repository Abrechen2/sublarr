"""add score_breakdown column to subtitle_downloads

Revision ID: b2c3d4e5f6a8
Revises: e7a1b2c3d4f5
Create Date: 2026-07-30

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b2c3d4e5f6a8"
down_revision = "e7a1b2c3d4f5"
branch_labels = None
depends_on = None


_TABLE = "subtitle_downloads"
_COLUMN = "score_breakdown"


def _columns() -> set[str]:
    """Existing columns of the target table (empty if the table is absent).

    Guarded with column inspection: the schema is also created straight from
    the models via create_all() on fresh installs, so the column can already
    exist when this migration runs — the add must be idempotent.
    """
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(_TABLE):
        return set()
    return {c["name"] for c in insp.get_columns(_TABLE)}


def upgrade():
    if _COLUMN in _columns():
        return
    with op.batch_alter_table(_TABLE) as batch_op:
        batch_op.add_column(sa.Column(_COLUMN, sa.Text(), nullable=True))


def downgrade():
    if _COLUMN not in _columns():
        return
    with op.batch_alter_table(_TABLE) as batch_op:
        batch_op.drop_column(_COLUMN)
