r"""Drop translation-memory entries whose source and target language are equal.

A same-language entry cannot be a translation. These were produced by the
per-line quality retry, which until this release passed the globally configured
source language instead of the language the subtitle was actually in: a job
whose target was English was recorded as ``en -> en`` no matter what the source
really was.

The rows are not harmless no-ops. On the reference install all 5 302 of them
differ from their source, and inspection shows what they are — French source
text stored against German output:

    nous sommes au-dessus de jaku.  ->  Wir sind über Jaku.\NViehst du, was ...

Every one of those is served verbatim on a cache hit, so an English subtitle
line gets replaced with German. Fixing the write path leaves the damage in
circulation, exactly as with tm1_strip_breaks.

Deleting rather than repairing: there is nothing to repair to. The stored pair
says "this English text translates to this English text" and the payload is
neither. What is lost is a cache entry, which the next translation regenerates
correctly — no subtitle content lives only here.

Revision ID: tm2_drop_same_lang
Revises: tm1_strip_breaks
"""

import sqlalchemy as sa
from alembic import op

revision = "tm2_drop_same_lang"
down_revision = "tm1_strip_breaks"
branch_labels = None
depends_on = None


def drop_same_language(conn) -> int:
    """Delete every same-language row on ``conn``; return how many went.

    Split out from ``upgrade`` so a test can run it against a real database —
    a migration that is only ever read is a migration nobody has run.
    """
    inspector = sa.inspect(conn)
    if "translation_memory" not in inspector.get_table_names():
        return 0
    result = conn.execute(
        sa.text(
            "DELETE FROM translation_memory "
            "WHERE source_lang IS NOT NULL "
            "AND target_lang IS NOT NULL "
            "AND lower(source_lang) = lower(target_lang)"
        )
    )
    return result.rowcount or 0


def upgrade() -> None:
    conn = op.get_bind()
    removed = drop_same_language(conn)
    if removed:
        print(f"tm2_drop_same_lang: removed {removed} same-language memory entries")


def downgrade() -> None:
    """Not reversible — the deleted rows were never valid translations."""
