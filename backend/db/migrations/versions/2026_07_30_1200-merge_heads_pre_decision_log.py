"""merge all outstanding heads so `alembic upgrade head` works again

Nine branch heads had accumulated, which makes the automatic
``upgrade("head")`` in app.py fail with "Multiple head revisions are
present" (logged as a non-fatal warning, so pending migrations were
silently skipped on Alembic-tracked installs). This no-op merge unifies
the graph before the decision-log migration chains onto it.

Revision ID: merge_pre_decision_log
Revises: a9b8c7d6e5f4, d4e5f6a7b8c9, e7a1b2c3d4f5, d2e3f4a5b6c7,
         d5e6f7a8b9c0, c3d4e5f6a7b8, a1b2c3d4e5f6, e3f4a5b6c7d8,
         b1c2d3e4f5a6
Create Date: 2026-07-30

"""

# revision identifiers, used by Alembic.
revision = "merge_pre_decision_log"
down_revision = (
    "a9b8c7d6e5f4",
    "d4e5f6a7b8c9",
    "e7a1b2c3d4f5",
    "d2e3f4a5b6c7",
    "d5e6f7a8b9c0",
    "c3d4e5f6a7b8",
    "a1b2c3d4e5f6",
    "e3f4a5b6c7d8",
    "b1c2d3e4f5a6",
)
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
