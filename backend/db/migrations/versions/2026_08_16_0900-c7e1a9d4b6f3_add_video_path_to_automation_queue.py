"""Add video_path to subtitle_automation_queue.

Auto-sync moves off the search path onto this queue, and it is the first
task type that needs two paths: the sidecar to correct and the video to
correct it against. `file_path` carries the sidecar; this column carries
the video.

Snapshotted rather than resolved from `wanted_item_id` at drain time
because two of the four enqueue sites in `wanted_search/process.py` call
`delete_wanted_item(item_id)` on the very next line — a lookup would come
back empty in precisely the case where the sync is wanted.

Nullable, with no backfill: every row that predates this migration is an
`embedded_extract` or a `sidecar_translate`, and neither has a video to
record. The runner treats a missing `video_path` on an `auto_sync` row as
a terminal failure rather than guessing one.

Revision ID: c7e1a9d4b6f3
Revises: f3a9c1e7b5d4
Create Date: 2026-08-16

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision = "c7e1a9d4b6f3"
down_revision = "f3a9c1e7b5d4"
branch_labels = None
depends_on = None

_TABLE = "subtitle_automation_queue"
_COLUMN = "video_path"


def _existing_columns(bind) -> set[str]:
    return {c["name"] for c in sa.inspect(bind).get_columns(_TABLE)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return
    # A fresh install builds its schema from the model metadata rather than
    # by replaying migrations, so the column can already be here.
    if _COLUMN in _existing_columns(bind):
        return
    op.add_column(_TABLE, sa.Column(_COLUMN, sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return
    if _COLUMN not in _existing_columns(bind):
        return
    # Rows that only this column made sense of go with it — an auto_sync row
    # without a video path is unrunnable, and leaving it would have the
    # downgraded runner fail it once per drain forever.
    op.execute(
        f"DELETE FROM {_TABLE} WHERE task_type = 'auto_sync'"  # noqa: S608 — constant table name
    )
    if bind.dialect.name == "postgresql":
        op.drop_column(_TABLE, _COLUMN)
    else:
        with op.batch_alter_table(_TABLE) as batch:
            batch.drop_column(_COLUMN)
