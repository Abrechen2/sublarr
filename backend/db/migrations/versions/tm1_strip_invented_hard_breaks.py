"""Strip hard line breaks the translation memory never got from its source.

Until 1.13.4 nothing removed a hard line break that a model appended on its
own, and every accepted batch was written to the translation memory. Measured
on one production install: 58 012 of 160 932 entries (36%) carry a break their
source line does not have, and each of those is re-served verbatim on every
cache hit — so fixing the write path alone would leave the damage in
circulation indefinitely.

Only entries whose source has no break at all are touched, so a break the
subtitle genuinely asked for survives. Irreversible by nature: the original
model output is not kept anywhere, and restoring a break we consider spurious
would be re-introducing the defect.

Revision ID: tm1_strip_breaks
Revises: b7e4d2c9a1f3
"""

import re

import sqlalchemy as sa
from alembic import op

revision = "tm1_strip_breaks"
down_revision = "b7e4d2c9a1f3"
branch_labels = None
depends_on = None

HARD_BREAK = chr(92) + "N"
# source_text_normalized is lower-cased on write, so a source break is "\n"
SOURCE_BREAK = chr(92) + "n"

_CHUNK = 2000


def clean(translated: str) -> str:
    """Mirror translation.llm_utils.strip_invented_hard_breaks for one line."""
    return re.sub(r"\s+", " ", translated.replace(HARD_BREAK, " ")).strip()


def strip_breaks(conn) -> int:
    """Repair every affected row on ``conn``; return how many were changed.

    Split out from ``upgrade`` so it can be exercised against a real database
    in a test — a migration that is only ever read is a migration nobody has
    run.
    """
    rows = conn.execute(
        sa.text("SELECT id, source_text_normalized, translated_text FROM translation_memory")
    )

    pending: list[dict] = []
    fixed = 0
    stmt = sa.text("UPDATE translation_memory SET translated_text = :t WHERE id = :i")

    for row_id, source, translated in rows:
        if not translated or HARD_BREAK not in translated:
            continue
        if source and SOURCE_BREAK in source:
            continue  # the subtitle asked for a break — leave it alone
        pending.append({"i": row_id, "t": clean(translated)})
        if len(pending) >= _CHUNK:
            conn.execute(stmt, pending)
            fixed += len(pending)
            pending = []

    if pending:
        conn.execute(stmt, pending)
        fixed += len(pending)

    return fixed


def upgrade() -> None:
    fixed = strip_breaks(op.get_bind())
    print(f"translation_memory: stripped invented hard breaks from {fixed} entries")


def downgrade() -> None:
    """Irreversible — the breaks were not recorded anywhere before removal."""
