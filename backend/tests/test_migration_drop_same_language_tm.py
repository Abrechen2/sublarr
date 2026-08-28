"""The same-language translation-memory entries must go, and only those.

They come from the per-line quality retry passing the configured source
language instead of the real one, so a job targeting English was recorded as
``en -> en`` whatever the source was. On the reference install every one of the
5 302 such rows differs from its source — inspection shows French source text
stored against German output — and each is served verbatim on a cache hit,
putting German into an English subtitle.
"""

from __future__ import annotations

import sqlalchemy as sa

from db.migrations.versions.tm2_drop_same_language_entries import drop_same_language

_DDL = """
CREATE TABLE translation_memory (
    id INTEGER PRIMARY KEY,
    source_lang TEXT,
    target_lang TEXT,
    source_text_normalized TEXT,
    text_hash TEXT,
    translated_text TEXT,
    backend TEXT
)
"""


def _seed(conn, rows):
    for i, (src, tgt, text, translated) in enumerate(rows, start=1):
        conn.execute(
            sa.text(
                "INSERT INTO translation_memory "
                "(id, source_lang, target_lang, source_text_normalized, text_hash, translated_text) "
                "VALUES (:i, :s, :t, :x, :h, :y)"
            ),
            {"i": i, "s": src, "t": tgt, "x": text, "h": f"h{i}", "y": translated},
        )


def _engine(tmp_path):
    return sa.create_engine(f"sqlite:///{tmp_path / 'tm.db'}")


def test_removes_same_language_rows_and_keeps_the_rest(tmp_path):
    engine = _engine(tmp_path)
    with engine.begin() as conn:
        conn.execute(sa.text(_DDL))
        _seed(
            conn,
            [
                # the real shape of the damage: French in, German out, labelled en->en
                ("en", "en", "nous sommes au-dessus de jaku.", "Wir sind über Jaku."),
                ("en", "en", "tout ira bien.", "Alles wird gut."),
                ("en", "de", "we are above jaku.", "Wir sind über Jaku."),
                ("de", "en", "wir sind über jaku.", "We are above Jaku."),
                ("zh", "de", "我们在雅久上空", "Wir sind über Jaku."),
            ],
        )
        removed = drop_same_language(conn)

    assert removed == 2
    with engine.connect() as conn:
        pairs = sorted(
            (r[0], r[1])
            for r in conn.execute(
                sa.text("SELECT source_lang, target_lang FROM translation_memory")
            )
        )
    assert pairs == [("de", "en"), ("en", "de"), ("zh", "de")]


def test_case_differences_still_count_as_same_language(tmp_path):
    engine = _engine(tmp_path)
    with engine.begin() as conn:
        conn.execute(sa.text(_DDL))
        _seed(conn, [("EN", "en", "x", "y"), ("de", "DE", "a", "b")])
        assert drop_same_language(conn) == 2


def test_is_idempotent_and_safe_on_an_empty_table(tmp_path):
    engine = _engine(tmp_path)
    with engine.begin() as conn:
        conn.execute(sa.text(_DDL))
        assert drop_same_language(conn) == 0
        _seed(conn, [("en", "en", "x", "y")])
        assert drop_same_language(conn) == 1
        assert drop_same_language(conn) == 0


def test_missing_table_is_not_an_error(tmp_path):
    engine = _engine(tmp_path)
    with engine.begin() as conn:
        assert drop_same_language(conn) == 0
