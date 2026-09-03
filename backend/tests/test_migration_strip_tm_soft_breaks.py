r"""The soft-break repair must match the write-path fix exactly.

Same reason as the hard-break one: two implementations of "remove a break the
source never had" exist — the guard in translation.llm_utils and the migration
that repairs old rows. If they drift, the memory keeps serving text the live
path would never produce.
"""

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa

from translation.llm_utils import strip_invented_hard_breaks

HB = chr(92) + "N"
SB = chr(92) + "n"

_spec = importlib.util.spec_from_file_location(
    "_tm3_migration",
    Path(__file__).resolve().parents[1]
    / "db"
    / "migrations"
    / "versions"
    / "tm3_strip_invented_soft_breaks.py",
)
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)


@pytest.mark.parametrize(
    "translated",
    [
        f"Apropos, Mariabelle…{SB}",
        f"Das ist die Nachricht{SB}des Bezirksbürgermeisters.",
        f"Kurze{SB}Zeile{SB}hier.{SB}",
        f"Beide{HB}Schreibweisen{SB}gemischt.",
        f"Nur die harte{HB}Form.",
        "Nichts zu tun.",
    ],
)
def test_migration_cleanup_matches_the_write_path(translated):
    source = "a source line without any break"

    assert [_migration.clean(translated)] == strip_invented_hard_breaks([source], [translated])


def test_the_stop_condition_is_the_lower_cased_source_break():
    """Both source spellings land as the lower-case one — pin that."""
    assert _migration.SOURCE_BREAK == SB, "normalized source text is lower-cased"
    assert _migration.BREAKS == (HB, SB)


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
                {"i": 1, "s": "a plain source line", "h": "a", "t": f"Erfunden hier.{SB}"},
                {
                    "i": 2,
                    "s": f"source asked for{SB} a break",
                    "h": "b",
                    "t": f"Behalten{SB}bitte.",
                },
                {"i": 3, "s": "nothing to do here", "h": "c", "t": "Ganz sauber."},
                {"i": 4, "s": "an inner one", "h": "d", "t": f"Ein{SB}innerer Umbruch."},
                {"i": 5, "s": "still the hard kind", "h": "e", "t": f"Harte{HB}Form."},
                {
                    "i": 6,
                    "s": f"the source wanted{SB} one",
                    "h": "f",
                    "t": f"Nur anders{HB}geschrieben.",
                },
            ],
        )


def test_the_repair_touches_exactly_the_damaged_rows(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'tm3.db'}")
    _seed(engine)

    with engine.begin() as conn:
        fixed = _migration.strip_breaks(conn)

    with engine.begin() as conn:
        after = dict(
            conn.execute(sa.text("SELECT id, translated_text FROM translation_memory")).all()
        )

    assert fixed == 3
    assert after[1] == "Erfunden hier."
    assert after[2] == f"Behalten{SB}bitte.", "the source asked for this break"
    assert after[3] == "Ganz sauber."
    assert after[4] == "Ein innerer Umbruch."
    assert after[5] == "Harte Form.", "an invented break in either spelling goes"
    assert after[6] == f"Nur anders{HB}geschrieben.", "re-spelled, but the source wanted it"


def test_the_repair_is_idempotent(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'tm3b.db'}")
    _seed(engine)

    with engine.begin() as conn:
        _migration.strip_breaks(conn)
    with engine.begin() as conn:
        second = _migration.strip_breaks(conn)

    assert second == 0
