"""Strip SOFT line breaks the translation memory never got from its source.

The 1.13.4 cleanup (``tm1_strip_breaks``) and the guard behind it only ever
looked at the hard break. ASS has a second spelling, the soft break, and the
models emit that one too — it went into the memory unfiltered and is re-served
verbatim on every cache hit. Measured on production on 2026-09-03 against
1.14.0-rc.4: 0 entries carry an invented hard break, 459 of 254 196 carry an
invented soft one, and they were still accumulating daily (125, 120, 15, 52,
29, 3 over 08-29..09-03) — i.e. produced by the release under test, not by
some older version.

Same rule as tm1, now applied to both spellings: only entries whose source has
no break **at all** are touched, so a break the subtitle genuinely asked for
survives — including one the model merely re-spelled. Mirrors
``translation.llm_utils.strip_invented_hard_breaks`` as it now stands, which
is the point: the migration cleans exactly what the write path stops.

Irreversible by nature: the original model output is not kept anywhere, and
restoring a break we consider spurious would be re-introducing the defect.

Revision ID: tm3_strip_soft
Revises: i201_failure_kind
"""

import re

import sqlalchemy as sa
from alembic import op

revision = "tm3_strip_soft"
down_revision = "i201_failure_kind"
branch_labels = None
depends_on = None

HARD_BREAK = chr(92) + "N"
SOFT_BREAK = chr(92) + "n"
BREAKS = (HARD_BREAK, SOFT_BREAK)
# source_text_normalized is lower-cased on write, so a source break of EITHER
# spelling is stored as the lower-case one. Its presence means "the subtitle
# asked for a break", whichever way it was originally written.
SOURCE_BREAK = SOFT_BREAK

_CHUNK = 2000


def clean(translated: str) -> str:
    """Mirror translation.llm_utils.strip_invented_hard_breaks for one line."""
    without = translated
    for marker in BREAKS:
        without = without.replace(marker, " ")
    return re.sub(r"\s+", " ", without).strip()


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
        if not translated or not any(marker in translated for marker in BREAKS):
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
    print(f"translation_memory: stripped invented soft breaks from {fixed} entries")


def downgrade() -> None:
    """Irreversible — the breaks were not recorded anywhere before removal."""
