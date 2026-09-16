"""Drop Ollama translation-memory entries stored for a non-configured target.

Until 1.14.3 every Ollama request asked the model for the GLOBAL direction —
"Translate these anime subtitle lines from English to German" — whatever the
job wanted: ``translation.llm_utils.build_translation_prompt`` accepted the
request's languages and built the prompt from the global template anyway, and
the default chat system prompt was hard-coded to German. A job for any other
target language therefore got text in the configured target back, and the
cache stored it under the language pair that was requested.

Measured on the reference install on 2026-09-16: 70 049 rows under ollama
``de -> en``; of 2 000 sampled, 1 369 are German-only, 16 English-only and
1 478 identical to their (German) source. Each is served verbatim on a cache
hit, so fixing the prompt alone would keep writing German into English
subtitles for every line seen before.

Scope, deliberately narrow:
- only ``backend = ollama`` — every other backend named the requested
  direction all along;
- only rows whose target differs from the configured target language. Rows
  FOR the configured target are the right language whatever their source
  (a ``ja -> de`` row was asked "English to German" and still answered German).

The configured target is read the way the app resolves it: ``config_entries``
first, then ``SUBLARR_TARGET_LANGUAGE``, then the default ``de``.

Writer, closed in the same release: ``translator.cache._store_translations_in_cache``
stores whatever the backend returned under the requested pair; the backend now
asks for that pair (commit "fix(translation): ask the model for the direction
the caller requested").

Deleting rather than repairing: the correct translation was never produced.
What is lost is a cache entry, which the next translation regenerates — no
subtitle content lives only here. Irreversible.

Revision ID: tm4_wrong_direction
Revises: tm3_strip_soft
"""

import os

import sqlalchemy as sa
from alembic import op

revision = "tm4_wrong_direction"
down_revision = "tm3_strip_soft"
branch_labels = None
depends_on = None

_DEFAULT_TARGET = "de"


def configured_target_language(conn) -> str:
    """The target language the install is configured for."""
    inspector = sa.inspect(conn)
    if "config_entries" in inspector.get_table_names():
        value = conn.execute(
            sa.text("SELECT value FROM config_entries WHERE key = 'target_language'")
        ).scalar()
        if value and value.strip():
            return value.strip().strip('"').lower()
    env = os.environ.get("SUBLARR_TARGET_LANGUAGE", "").strip()
    return (env or _DEFAULT_TARGET).lower()


def drop_wrong_direction(conn, configured_target: str) -> int:
    """Delete Ollama rows stored for a target other than ``configured_target``.

    Split out from ``upgrade`` so a test can run it against a real database.
    """
    inspector = sa.inspect(conn)
    if "translation_memory" not in inspector.get_table_names():
        return 0
    result = conn.execute(
        sa.text(
            "DELETE FROM translation_memory "
            "WHERE lower(backend) = 'ollama' "
            "AND target_lang IS NOT NULL "
            "AND lower(target_lang) <> :target"
        ),
        {"target": configured_target.lower()},
    )
    return result.rowcount or 0


def upgrade() -> None:
    conn = op.get_bind()
    target = configured_target_language(conn)
    removed = drop_wrong_direction(conn, target)
    if removed:
        print(
            f"tm4_wrong_direction: removed {removed} Ollama memory entries "
            f"stored for a target other than '{target}'"
        )


def downgrade() -> None:
    """Not reversible — the deleted rows never held the requested language."""
