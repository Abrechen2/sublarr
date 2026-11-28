"""An Alembic-untracked DB must end up with every column the models declare.

``_patch_pre_alembic_columns`` listed the columns by hand, and each release
that forgot one broke untracked installs: 1.19-1.21 added
``language_profiles.prefer_signs``/``download_full``,
``subtitle_downloads.quality_accepted`` and ``glossary_entries.target_language``
without repeating them there. In the Codex VM (1.14 DB upgraded to 1.22-dev,
2026-11-28) every Sonarr and Radarr wanted scan then died with
``column language_profiles.prefer_signs does not exist``. The patcher now adds
any model column a table lacks; these tests build every table with only its
primary key, so a forgotten column fails here instead of on users' installs.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql, sqlite


def _metadata():
    import db.models  # noqa: F401 - registers every model
    from extensions import db

    return db.metadata


def _bare_tables(engine) -> None:
    """Every model table with only its primary-key columns."""
    bare = sa.MetaData()
    for table in _metadata().sorted_tables:
        sa.Table(
            table.name,
            bare,
            *[sa.Column(c.name, c.type, primary_key=True) for c in table.primary_key.columns],
        )
    bare.create_all(engine)


def test_untracked_db_gains_every_model_column(tmp_path):
    from app import _patch_pre_alembic_columns

    engine = sa.create_engine(f"sqlite:///{tmp_path / 'untracked.db'}")
    _bare_tables(engine)

    _patch_pre_alembic_columns(engine, sa.inspect)

    insp = sa.inspect(engine)
    missing = {
        f"{t.name}.{c.name}"
        for t in _metadata().sorted_tables
        for c in t.columns
        if c.name not in {col["name"] for col in insp.get_columns(t.name)}
    }
    assert not missing, f"untracked DB still misses model columns: {sorted(missing)}"


def test_existing_rows_get_the_model_default(tmp_path):
    from app import _patch_pre_alembic_columns

    engine = sa.create_engine(f"sqlite:///{tmp_path / 'untracked.db'}")
    _bare_tables(engine)
    with engine.begin() as conn:
        conn.execute(sa.text("INSERT INTO language_profiles (id) VALUES (1)"))

    _patch_pre_alembic_columns(engine, sa.inspect)

    with engine.connect() as conn:
        row = conn.execute(
            sa.text("SELECT prefer_signs, download_full FROM language_profiles WHERE id = 1")
        ).one()
    assert tuple(row) == (0, 1)


def test_second_run_changes_nothing(tmp_path):
    from app import _patch_pre_alembic_columns

    engine = sa.create_engine(f"sqlite:///{tmp_path / 'untracked.db'}")
    _bare_tables(engine)
    _patch_pre_alembic_columns(engine, sa.inspect)

    from db.untracked_columns import missing_column_ddl

    assert missing_column_ddl(sa.inspect(engine), _metadata(), engine.dialect) == []


def test_ddl_renders_defaults_per_dialect():
    from db.untracked_columns import column_ddl

    flag = sa.Column("enabled", sa.Boolean, nullable=False, default=True)
    count = sa.Column("prefer_signs", sa.Integer, nullable=False, default=0)
    label = sa.Column("label", sa.String(8), nullable=False, default="de")
    sa.Table("t", sa.MetaData(), flag, count, label)

    assert column_ddl("t", flag, postgresql.dialect()) == (
        "ALTER TABLE t ADD COLUMN enabled BOOLEAN NOT NULL DEFAULT true"
    )
    assert column_ddl("t", flag, sqlite.dialect()) == (
        "ALTER TABLE t ADD COLUMN enabled BOOLEAN NOT NULL DEFAULT 1"
    )
    assert column_ddl("t", count, sqlite.dialect()) == (
        "ALTER TABLE t ADD COLUMN prefer_signs INTEGER NOT NULL DEFAULT 0"
    )
    assert column_ddl("t", label, sqlite.dialect()) == (
        "ALTER TABLE t ADD COLUMN label VARCHAR(8) NOT NULL DEFAULT 'de'"
    )


def test_not_null_without_any_default_is_added_nullable():
    """SQLite refuses NOT NULL without a default, and Postgres fails on existing rows."""
    from db.untracked_columns import column_ddl

    col = sa.Column("target_language", sa.String(8), nullable=False)
    sa.Table("t", sa.MetaData(), col)

    assert column_ddl("t", col, sqlite.dialect()) == (
        "ALTER TABLE t ADD COLUMN target_language VARCHAR(8)"
    )


def test_callable_default_is_not_rendered():
    from db.untracked_columns import column_ddl

    col = sa.Column("created_at", sa.String(32), nullable=False, default=lambda: "now")
    sa.Table("t", sa.MetaData(), col)

    assert column_ddl("t", col, sqlite.dialect()) == (
        "ALTER TABLE t ADD COLUMN created_at VARCHAR(32)"
    )
