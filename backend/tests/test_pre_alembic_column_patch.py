"""Regression: an Alembic-untracked DB must gain the columns migrations added.

``create_all()`` adds missing *tables* but never missing *columns*, so a
database that was first built that way never gets an ``alembic_version`` and
takes the create_all branch on every start for the rest of its life. Its only
route to a column a later migration introduced is
``_patch_pre_alembic_columns``.

app.py states the rule outright — "A column added by a migration MUST be
repeated here" — but nothing enforced it. The three columns the automation
queue gained on 2026-08-14/16 (``task_type``, ``source_language``,
``video_path``) were never added, so every untracked install ran 1.13.x with a
queue table the ORM could not query: the drain worker died at boot with
``no such column: subtitle_automation_queue.task_type``. Observed on the beta
instance on 2026-08-28, the second time this class of drift took it down.
"""

from __future__ import annotations

import sqlalchemy as sa

# The shape the table had before the 2026-08-14 migration, taken verbatim from
# an install that predates it.
_PRE_MIGRATION_QUEUE_DDL = """
CREATE TABLE subtitle_automation_queue (
    id INTEGER NOT NULL,
    wanted_item_id INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    target_language VARCHAR(8) NOT NULL,
    state VARCHAR(10) NOT NULL,
    attempt_count INTEGER NOT NULL,
    next_retry_at DATETIME,
    last_error TEXT,
    last_started_at DATETIME,
    last_finished_at DATETIME,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (wanted_item_id)
)
"""


# The shape ``translation_memory`` had before tm5_quality_score, taken from the
# model as it stood in 1.14.4-rc.15.
_PRE_MIGRATION_MEMORY_DDL = """
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


# The shapes ``series_settings``, ``movie_settings`` and ``foreign_track_scan``
# had before tvp1_track_variant_policy, taken verbatim from the models at
# v1.14.5 (``git show v1.14.5:backend/db/models/core.py`` /
# ``foreign_tracks.py``) — i.e. an install that predates the 1.15.0 track
# variant policy feature.
_PRE_TVP_SERIES_SETTINGS_DDL = """
CREATE TABLE series_settings (
    sonarr_series_id INTEGER NOT NULL,
    absolute_order INTEGER NOT NULL,
    preferred_audio_track_index INTEGER,
    processing_config TEXT,
    priority_override VARCHAR(20),
    min_attempts_per_day INTEGER NOT NULL,
    cleanup_foreign_tracks BOOLEAN,
    forced_preference_override TEXT,
    hi_preference_override TEXT,
    forced_scoring_override TEXT,
    target_languages_override TEXT,
    cutoff_language_override TEXT,
    must_contain_override TEXT,
    must_not_contain_override TEXT,
    audio_exclude_languages_override TEXT,
    subtitle_format_requirement TEXT,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (sonarr_series_id)
)
"""

_PRE_TVP_MOVIE_SETTINGS_DDL = """
CREATE TABLE movie_settings (
    radarr_movie_id INTEGER NOT NULL,
    preferred_audio_track_index INTEGER,
    cleanup_foreign_tracks BOOLEAN,
    priority_override VARCHAR(20),
    min_attempts_per_day INTEGER NOT NULL,
    forced_preference_override TEXT,
    hi_preference_override TEXT,
    forced_scoring_override TEXT,
    target_languages_override TEXT,
    cutoff_language_override TEXT,
    must_contain_override TEXT,
    must_not_contain_override TEXT,
    audio_exclude_languages_override TEXT,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (radarr_movie_id)
)
"""

_PRE_TVP_FOREIGN_TRACK_SCAN_DDL = """
CREATE TABLE foreign_track_scan (
    id INTEGER NOT NULL,
    path TEXT NOT NULL,
    size_bytes BIGINT NOT NULL,
    mtime FLOAT NOT NULL,
    state VARCHAR(16) NOT NULL,
    foreign_langs TEXT,
    track_count INTEGER NOT NULL,
    probed_at DATETIME,
    processed_at DATETIME,
    error TEXT,
    error_class VARCHAR(16),
    attempts INTEGER NOT NULL,
    generation INTEGER NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (path)
)
"""


def _model_columns(table_name: str) -> set[str]:
    import db.models  # noqa: F401  — registers the models on the metadata
    from extensions import db as sa_db

    return {c.name for c in sa_db.metadata.tables[table_name].columns}


def test_patcher_restores_columns_migrations_added(tmp_path):
    from app import _patch_pre_alembic_columns

    engine = sa.create_engine(f"sqlite:///{tmp_path / 'untracked.db'}")
    with engine.begin() as conn:
        conn.execute(sa.text(_PRE_MIGRATION_QUEUE_DDL))

    _patch_pre_alembic_columns(engine, sa.inspect)

    present = {c["name"] for c in sa.inspect(engine).get_columns("subtitle_automation_queue")}
    missing = _model_columns("subtitle_automation_queue") - present
    assert not missing, f"untracked DB still misses columns the ORM queries: {sorted(missing)}"


def test_patcher_is_idempotent(tmp_path):
    """Running twice must not fail — it runs on every start of an untracked DB."""
    from app import _patch_pre_alembic_columns

    engine = sa.create_engine(f"sqlite:///{tmp_path / 'untracked.db'}")
    with engine.begin() as conn:
        conn.execute(sa.text(_PRE_MIGRATION_QUEUE_DDL))

    _patch_pre_alembic_columns(engine, sa.inspect)
    _patch_pre_alembic_columns(engine, sa.inspect)

    present = {c["name"] for c in sa.inspect(engine).get_columns("subtitle_automation_queue")}
    assert "task_type" in present


def test_patcher_adds_the_translation_memory_quality_score(tmp_path):
    """The quality pass reads this column on every translated file.

    Without it an untracked install raises ``no such column:
    translation_memory.quality_score`` the first time it scores a line — the
    same shape of failure that took the beta instance down twice.
    """
    from app import _patch_pre_alembic_columns

    engine = sa.create_engine(f"sqlite:///{tmp_path / 'untracked-memory.db'}")
    with engine.begin() as conn:
        conn.execute(sa.text(_PRE_MIGRATION_MEMORY_DDL))

    _patch_pre_alembic_columns(engine, sa.inspect)

    present = {c["name"] for c in sa.inspect(engine).get_columns("translation_memory")}
    missing = _model_columns("translation_memory") - present
    assert not missing, f"untracked DB still misses columns the ORM queries: {sorted(missing)}"


def test_patcher_adds_track_variant_policy_columns_to_series_settings(tmp_path):
    """1.15.0's per-series track variant overrides (migration tvp1_track_variant_policy).

    Without these an untracked install raises ``no such column:
    series_settings.cleanup_track_variant_mode`` the first time a series
    settings row is read — the same shape of failure that has taken the beta
    instance down before.
    """
    from app import _patch_pre_alembic_columns

    engine = sa.create_engine(f"sqlite:///{tmp_path / 'untracked-series-settings.db'}")
    with engine.begin() as conn:
        conn.execute(sa.text(_PRE_TVP_SERIES_SETTINGS_DDL))

    _patch_pre_alembic_columns(engine, sa.inspect)

    present = {c["name"] for c in sa.inspect(engine).get_columns("series_settings")}
    missing = _model_columns("series_settings") - present
    assert not missing, f"untracked DB still misses columns the ORM queries: {sorted(missing)}"


def test_patcher_adds_track_variant_policy_columns_to_movie_settings(tmp_path):
    """1.15.0's per-movie track variant overrides (migration tvp1_track_variant_policy).

    Same rule as the series_settings counterpart: a migration-added column
    must be repeated in the patcher or an untracked install queries a column
    it does not have.
    """
    from app import _patch_pre_alembic_columns

    engine = sa.create_engine(f"sqlite:///{tmp_path / 'untracked-movie-settings.db'}")
    with engine.begin() as conn:
        conn.execute(sa.text(_PRE_TVP_MOVIE_SETTINGS_DDL))

    _patch_pre_alembic_columns(engine, sa.inspect)

    present = {c["name"] for c in sa.inspect(engine).get_columns("movie_settings")}
    missing = _model_columns("movie_settings") - present
    assert not missing, f"untracked DB still misses columns the ORM queries: {sorted(missing)}"


def test_patcher_adds_track_verdicts_to_foreign_track_scan(tmp_path):
    """1.15.0's per-track sweep verdicts (migration tvp1_track_variant_policy).

    Without ``track_verdicts`` an untracked install raises ``no such column:
    foreign_track_scan.track_verdicts`` the first time the per-track preview
    reads a scan row.
    """
    from app import _patch_pre_alembic_columns

    engine = sa.create_engine(f"sqlite:///{tmp_path / 'untracked-foreign-track-scan.db'}")
    with engine.begin() as conn:
        conn.execute(sa.text(_PRE_TVP_FOREIGN_TRACK_SCAN_DDL))

    _patch_pre_alembic_columns(engine, sa.inspect)

    present = {c["name"] for c in sa.inspect(engine).get_columns("foreign_track_scan")}
    missing = _model_columns("foreign_track_scan") - present
    assert not missing, f"untracked DB still misses columns the ORM queries: {sorted(missing)}"


def test_untracked_db_creates_sidecar_origins_table(tmp_path):
    """The untracked branch's ``create_all()`` must add the plain new table.

    ``sidecar_origins`` (migration tvp1_track_variant_policy) is not a column
    bolted onto an existing table, it is a table the migration introduces
    outright. An untracked DB never runs that migration, but app.py's
    create_all() branch (``create_app`` -> ``not
    _inspect(engine).has_table("alembic_version")`` -> ``sa_db.create_all()``)
    adds any missing table unconditionally — that is the mechanism that gives
    an untracked install the new table, not ``_patch_pre_alembic_columns``
    (which only ever adds columns to tables that already exist).

    This drives ``create_app(testing=True)`` itself, the same way
    ``test_foreign_track_scan_model.py`` and ``test_database.py`` do, rather
    than calling ``create_all()`` on the metadata directly — that exercises
    the real startup path (including the ``has_table("alembic_version")``
    branch decision) instead of merely asserting the ORM can describe the
    table.
    """
    import os

    db_path = str(tmp_path / "untracked-sidecar-origins.db")

    # Pre-populate with an old-shape table so the DB "already has tables but
    # not this one" — a bare empty file would not distinguish create_all()
    # adding sidecar_origins from create_all() building the whole schema from
    # scratch on a brand new file.
    engine = sa.create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(sa.text(_PRE_MIGRATION_QUEUE_DDL))
    engine.dispose()

    os.environ["SUBLARR_DB_PATH"] = db_path
    os.environ["SUBLARR_API_KEY"] = ""
    os.environ["SUBLARR_LOG_LEVEL"] = "ERROR"
    try:
        from config import reload_settings

        reload_settings()

        from app import create_app

        app = create_app(testing=True)
        with app.app_context():
            from extensions import db as sa_db

            tables = sa.inspect(sa_db.engine).get_table_names()
            assert "sidecar_origins" in tables
    finally:
        os.environ.pop("SUBLARR_DB_PATH", None)
        os.environ.pop("SUBLARR_API_KEY", None)
        os.environ.pop("SUBLARR_LOG_LEVEL", None)
        from config import reload_settings

        reload_settings()
