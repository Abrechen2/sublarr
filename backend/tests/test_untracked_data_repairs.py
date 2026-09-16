"""Data migrations reach databases Alembic does not track.

VM test of 1.14.3-rc.2 (2026-09-16): a database first created by
``create_all()`` never gets an ``alembic_version`` table, so app startup takes
the create_all branch on every start and never runs a migration. Data
migrations tm1..tm4 therefore never reached those installs — a poisoned
``ollama de -> en`` memory entry kept serving German for English after the
prompt fix. The existing migration tests call the cleanup functions directly
and so never exercised this startup path; these tests go through ``create_app``.

Each repair must run exactly once, like a migration: tm4's criterion would
otherwise delete correct English entries written after the fix on every start.
"""

import pytest
from sqlalchemy import text


def _start():
    from app import create_app

    return create_app(testing=True)


def _session():
    from extensions import db

    return db.session


def _store(source_lang, target_lang, source_text, translated, backend="ollama"):
    from db.translation import store_translation_cache

    store_translation_cache(source_lang, target_lang, source_text, translated, backend=backend)


def _lookup(source_lang, target_lang, source_text):
    from db.translation import lookup_translation_cache

    return lookup_translation_cache(source_lang, target_lang, source_text)


def _forget_repairs():
    """Simulate a database from before this release: no repair markers yet."""
    _session().execute(text("DROP TABLE IF EXISTS untracked_data_repairs"))
    _session().commit()


def test_the_database_under_test_is_untracked(temp_db):
    app = _start()
    with app.app_context():
        from sqlalchemy import inspect

        from extensions import db

        assert not inspect(db.engine).has_table("alembic_version")


def test_startup_removes_a_wrong_direction_entry_on_an_untracked_database(temp_db):
    app = _start()
    with app.app_context():
        _forget_repairs()
        _store("de", "en", "Guten Morgen, mein Freund.", "Guten Morgen, mein Freund.")
        assert _lookup("de", "en", "Guten Morgen, mein Freund.") is not None

    app = _start()
    with app.app_context():
        assert _lookup("de", "en", "Guten Morgen, mein Freund.") is None


def test_each_repair_runs_once_so_later_correct_entries_survive(temp_db):
    app = _start()
    with app.app_context():
        _store("de", "en", "Guten Morgen.", "Good morning.")  # written after the fix

    app = _start()
    with app.app_context():
        assert _lookup("de", "en", "Guten Morgen.") == "Good morning."
        applied = {
            row[0]
            for row in _session().execute(text("SELECT revision FROM untracked_data_repairs"))
        }
    assert {
        "tm1_strip_breaks",
        "tm2_drop_same_lang",
        "tm3_strip_soft",
        "tm4_wrong_direction",
    } <= applied


def test_a_failing_repair_is_retried_and_does_not_block_startup(temp_db, monkeypatch):
    import db.untracked_data_repairs as repairs

    def boom(conn):
        raise RuntimeError("disk full")

    app = _start()
    with app.app_context():
        _forget_repairs()
        _store("de", "en", "Hallo.", "Hallo.")

    original = list(repairs.REPAIRS)
    monkeypatch.setattr(
        repairs,
        "REPAIRS",
        [(name, boom if name == "tm4_wrong_direction" else fn) for name, fn in original],
    )
    app = _start()  # must not raise
    with app.app_context():
        assert _lookup("de", "en", "Hallo.") is not None

    monkeypatch.setattr(repairs, "REPAIRS", original)
    app = _start()
    with app.app_context():
        assert _lookup("de", "en", "Hallo.") is None


@pytest.mark.parametrize("revision", ["tm1_strip_breaks", "tm2_drop_same_lang", "tm3_strip_soft"])
def test_earlier_memory_repairs_are_registered_too(revision):
    import db.untracked_data_repairs as repairs

    assert revision in [name for name, _ in repairs.REPAIRS]
