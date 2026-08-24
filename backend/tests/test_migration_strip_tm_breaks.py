r"""The translation-memory repair must match the write-path fix exactly.

Two implementations of "remove a break the source never had" exist — the one
in translation.llm_utils that guards new writes, and the one in the migration
that repairs old rows. If they drift, the memory keeps serving text the live
path would never produce.
"""

import importlib.util
from pathlib import Path

import pytest

from translation.llm_utils import strip_invented_hard_breaks

HB = chr(92) + "N"

_spec = importlib.util.spec_from_file_location(
    "_tm_migration",
    Path(__file__).resolve().parents[1]
    / "db"
    / "migrations"
    / "versions"
    / "tm1_strip_invented_hard_breaks.py",
)
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)


@pytest.mark.parametrize(
    "translated",
    [
        f"Apropos, Mariabelle…{HB}",
        f"Das ist die Nachricht{HB}des Bezirksbürgermeisters.",
        f"Kurze{HB}Zeile{HB}hier.{HB}",
        "Nichts zu tun.",
    ],
)
def test_migration_cleanup_matches_the_write_path(translated):
    source = "a source line without any break"

    assert [_migration.clean(translated)] == strip_invented_hard_breaks([source], [translated])


def test_a_source_break_is_the_migration_s_stop_condition():
    """The migration skips those rows rather than cleaning them — pin the marker."""
    assert chr(92) + "n" == _migration.SOURCE_BREAK, "normalized source text is lower-cased"
    assert chr(92) + "N" == _migration.HARD_BREAK


# ---------------------------------------------------------------------------
# The repair itself, against a real database.
# ---------------------------------------------------------------------------

import sqlalchemy as sa

BS = chr(92)


def _seed(engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE translation_memory ("
                " id INTEGER PRIMARY KEY, source_lang TEXT, target_lang TEXT,"
                " source_text_normalized TEXT, text_hash TEXT, translated_text TEXT)"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO translation_memory"
                " (id, source_lang, target_lang, source_text_normalized, text_hash,"
                "  translated_text) VALUES (:i, 'en', 'de', :s, :h, :t)"
            ),
            [
                {"i": 1, "s": "a plain source line", "h": "a", "t": f"Erfunden hier.{HB}"},
                {
                    "i": 2,
                    "s": f"source asked for{BS}n a break",
                    "h": "b",
                    "t": f"Behalten{HB}bitte.",
                },
                {"i": 3, "s": "nothing to do here", "h": "c", "t": "Ganz sauber."},
                {"i": 4, "s": "an inner one", "h": "d", "t": f"Ein{HB}innerer Umbruch."},
            ],
        )


def test_the_repair_touches_exactly_the_damaged_rows(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'tm.db'}")
    _seed(engine)

    with engine.begin() as conn:
        fixed = _migration.strip_breaks(conn)

    with engine.begin() as conn:
        after = dict(
            conn.execute(sa.text("SELECT id, translated_text FROM translation_memory")).all()
        )

    assert fixed == 2
    assert after[1] == "Erfunden hier."
    assert after[2] == f"Behalten{HB}bitte.", "the source asked for this break"
    assert after[3] == "Ganz sauber."
    assert after[4] == "Ein innerer Umbruch."


def test_the_repair_is_idempotent(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'tm2.db'}")
    _seed(engine)

    with engine.begin() as conn:
        _migration.strip_breaks(conn)
    with engine.begin() as conn:
        second = _migration.strip_breaks(conn)

    assert second == 0
