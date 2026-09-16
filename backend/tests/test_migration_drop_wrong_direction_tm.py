"""Ollama memory entries for a target other than the configured one must go.

Until 2026-09-16 every Ollama request asked for the GLOBAL direction
(English -> German) whatever the job wanted, so an entry stored under any other
target holds text in the configured target language. Prod: 70 049 rows under
ollama de->en; of 2 000 sampled, 1 369 are German-only and 16 English-only.
Other backends named the requested direction all along and are kept.
"""

from __future__ import annotations

import sqlalchemy as sa

from db.migrations.versions.tm4_drop_wrong_direction_ollama import (
    configured_target_language,
    drop_wrong_direction,
)

_DDL_TM = """
CREATE TABLE translation_memory (
    id INTEGER PRIMARY KEY,
    source_lang TEXT, target_lang TEXT, source_text_normalized TEXT,
    text_hash TEXT, translated_text TEXT, backend TEXT
)
"""
_DDL_CONFIG = "CREATE TABLE config_entries (key TEXT PRIMARY KEY, value TEXT NOT NULL)"


def _engine(tmp_path):
    return sa.create_engine(f"sqlite:///{tmp_path / 'tm.db'}")


def _seed(conn, rows):
    for i, (src, tgt, backend, translated) in enumerate(rows, start=1):
        conn.execute(
            sa.text(
                "INSERT INTO translation_memory (id, source_lang, target_lang, "
                "source_text_normalized, text_hash, translated_text, backend) "
                "VALUES (:i, :s, :t, :x, :h, :y, :b)"
            ),
            {"i": i, "s": src, "t": tgt, "x": f"x{i}", "h": f"h{i}", "y": translated, "b": backend},
        )


def _pairs(conn):
    return sorted(
        tuple(r)
        for r in conn.execute(
            sa.text("SELECT source_lang, target_lang, backend FROM translation_memory")
        )
    )


def test_drops_ollama_rows_for_another_target_and_keeps_the_rest(tmp_path):
    engine = _engine(tmp_path)
    with engine.begin() as conn:
        conn.execute(sa.text(_DDL_TM))
        _seed(
            conn,
            [
                ("de", "en", "ollama", "Sag mir ehrlich, was du denkst"),  # the damage
                ("zh", "en", "ollama", "Wir sind über Jaku."),  # same prompt, same damage
                ("en", "de", "ollama", "Wir sind über Jaku."),  # configured direction
                ("ja", "de", "ollama", "Wir sind über Jaku."),  # right target language
                ("de", "en", "openai_compat", "Sag mir ehrlich"),  # same prompt builder
                ("de", "en", "deepl", "We are above Jaku."),  # named the direction
                ("id", "de", "deepl", "Wir sind über Jaku."),
            ],
        )
        removed = drop_wrong_direction(conn, "de")

    assert removed == 3
    with engine.connect() as conn:
        assert _pairs(conn) == [
            ("de", "en", "deepl"),
            ("en", "de", "ollama"),
            ("id", "de", "deepl"),
            ("ja", "de", "ollama"),
        ]


def test_language_and_backend_spelling_do_not_matter(tmp_path):
    engine = _engine(tmp_path)
    with engine.begin() as conn:
        conn.execute(sa.text(_DDL_TM))
        _seed(conn, [("de", "EN", "Ollama", "x"), ("en", "DE", "OLLAMA", "y")])
        assert drop_wrong_direction(conn, "de") == 1


def test_configured_target_comes_from_config_entries(tmp_path):
    engine = _engine(tmp_path)
    with engine.begin() as conn:
        conn.execute(sa.text(_DDL_CONFIG))
        conn.execute(sa.text("INSERT INTO config_entries VALUES ('target_language', 'en')"))
        assert configured_target_language(conn) == "en"


def test_configured_target_ignores_env_like_the_runtime(tmp_path, monkeypatch):
    """target_language is a DB-only UI setting; the runtime never reads the env var."""
    monkeypatch.setenv("SUBLARR_TARGET_LANGUAGE", "en")
    engine = _engine(tmp_path)
    with engine.begin() as conn:
        conn.execute(sa.text(_DDL_CONFIG))
        assert configured_target_language(conn) == "de"


def test_missing_table_is_a_no_op(tmp_path):
    engine = _engine(tmp_path)
    with engine.begin() as conn:
        assert drop_wrong_direction(conn, "de") == 0
