"""sig1: profile switches for signs & songs, mapped from forced_scoring."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

_PATH = (
    Path(__file__).resolve().parent.parent / "db/migrations/versions/sig1_signs_songs_profile.py"
)


def _migration():
    spec = importlib.util.spec_from_file_location("sig1", _PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_forced_scoring_maps_onto_the_new_switches(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE language_profiles (id INTEGER PRIMARY KEY, name TEXT, "
                "forced_preference TEXT, forced_scoring TEXT)"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO language_profiles VALUES "
                "(1, 'only', 'disabled', 'only'), (2, 'prefer', 'auto', 'prefer'), "
                "(3, 'plain', 'disabled', 'include'), (4, 'kept', 'separate', 'exclude')"
            )
        )

    for _ in range(2):  # a second run changes nothing
        with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
            _migration().upgrade()

    with engine.connect() as conn:
        rows = {
            r[0]: r[1:]
            for r in conn.execute(
                sa.text(
                    "SELECT name, forced_preference, prefer_signs, download_full "
                    "FROM language_profiles"
                )
            )
        }
    assert rows == {
        "only": ("separate", 0, 0),
        "prefer": ("separate", 0, 1),
        "plain": ("disabled", 0, 1),
        "kept": ("separate", 0, 1),
    }
