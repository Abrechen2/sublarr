"""Re-add an index on subtitle_downloads.file_path.

h1i2j3k4l5m6 dropped it as unused. Since then every scan and every wanted
cleanup asks per file whether its subtitle is our own translation
(``is_machine_translated``): a seq scan of the whole table each time, 6.5 ms
on prod's 24,600 rows and ~1,800 calls per cleanup — and far slower on a
Raspberry Pi with SQLite or on a longer download history.

Revision ID: sdp1_subtitle_downloads_path_idx
Revises: sig1_signs_songs
"""

from alembic import op
from sqlalchemy import inspect

revision = "sdp1_subtitle_downloads_path_idx"
down_revision = "sig1_signs_songs"
branch_labels = None
depends_on = None

_NAME = "idx_subtitle_downloads_file_path"


def _existing() -> set[str]:
    return {ix["name"] for ix in inspect(op.get_bind()).get_indexes("subtitle_downloads")}


def upgrade() -> None:
    if _NAME not in _existing():
        op.create_index(_NAME, "subtitle_downloads", ["file_path"])


def downgrade() -> None:
    if _NAME in _existing():
        op.drop_index(_NAME, table_name="subtitle_downloads")
