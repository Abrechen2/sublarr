"""The quality-score column has to arrive on both routes into a database.

A column added by a migration reaches an Alembic-tracked install through that
migration, and an untracked one only through ``_patch_pre_alembic_columns``.
Both are exercised here through ``create_app`` rather than by calling the
migration directly, because the two routes are chosen inside ``create_app`` and
testing the function instead of the path is how this class of drift kept
reaching production.
"""

from __future__ import annotations

import os

import sqlalchemy as sa

_PRE_MIGRATION_DDL = """
CREATE TABLE translation_memory (
    id INTEGER NOT NULL,
    source_lang TEXT NOT NULL,
    target_lang TEXT NOT NULL,
    source_text_normalized TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    translated_text TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    backend VARCHAR(32),
    PRIMARY KEY (id),
    UNIQUE (source_lang, target_lang, text_hash)
)
"""


def _columns(path):
    engine = sa.create_engine(f"sqlite:///{path}")
    try:
        return {c["name"] for c in sa.inspect(engine).get_columns("translation_memory")}
    finally:
        engine.dispose()


def _boot(db_path):
    from config import reload_settings
    from db import close_db

    os.environ["SUBLARR_DB_PATH"] = str(db_path)
    os.environ["SUBLARR_API_KEY"] = ""
    os.environ["SUBLARR_LOG_LEVEL"] = "ERROR"
    reload_settings()
    try:
        from app import create_app

        create_app(testing=True)
    finally:
        close_db()
        for key in ("SUBLARR_DB_PATH", "SUBLARR_API_KEY", "SUBLARR_LOG_LEVEL"):
            os.environ.pop(key, None)


def test_a_fresh_database_has_the_column(tmp_path):
    db_path = tmp_path / "fresh.db"
    _boot(db_path)
    assert "quality_score" in _columns(db_path)


def test_an_alembic_untracked_database_gains_the_column(tmp_path):
    """No ``alembic_version`` row: create_all runs, and columns come from the patcher."""
    db_path = tmp_path / "untracked.db"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(sa.text(_PRE_MIGRATION_DDL))
    engine.dispose()

    assert "quality_score" not in _columns(db_path)
    _boot(db_path)
    assert "quality_score" in _columns(db_path)


def test_the_column_starts_empty_and_takes_a_score(tmp_path):
    """NULL means "not judged yet", which is what every existing row is."""
    from config import reload_settings
    from db import close_db

    db_path = tmp_path / "scores.db"
    os.environ["SUBLARR_DB_PATH"] = str(db_path)
    os.environ["SUBLARR_API_KEY"] = ""
    os.environ["SUBLARR_LOG_LEVEL"] = "ERROR"
    reload_settings()
    try:
        from app import create_app

        app = create_app(testing=True)
        with app.app_context():
            from db.translation import lookup_quality_scores, store_translation_cache

            store_translation_cache("en", "de", "Good morning.", "Guten Morgen.")
            assert lookup_quality_scores("en", "de", ["Good morning."]) == [("Guten Morgen.", None)]

            store_translation_cache("en", "de", "Good morning.", "Guten Morgen.", quality_score=91)
            assert lookup_quality_scores("en", "de", ["Good morning."]) == [("Guten Morgen.", 91)]

            # A different translation for the same source drops the old verdict.
            store_translation_cache("en", "de", "Good morning.", "Guten Tag.")
            assert lookup_quality_scores("en", "de", ["Good morning."]) == [("Guten Tag.", None)]
    finally:
        close_db()
        for key in ("SUBLARR_DB_PATH", "SUBLARR_API_KEY", "SUBLARR_LOG_LEVEL"):
            os.environ.pop(key, None)
