"""enc2: values of keys that became sensitive are encrypted on upgrade."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

_PATH = (
    Path(__file__).resolve().parent.parent
    / "db/migrations/versions/enc2_encrypt_newly_sensitive.py"
)


def _migration():
    spec = importlib.util.spec_from_file_location("enc2", _PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_plain_tvdb_pin_is_encrypted_and_still_reads_back(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBLARR_CONFIG_DIR", str(tmp_path))
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE config_entries (key TEXT PRIMARY KEY, value TEXT)"))
        conn.execute(
            sa.text(
                "INSERT INTO config_entries VALUES ('tvdb_pin', '1234'), ('target_language', 'de')"
            )
        )

    for _ in range(2):  # a second run changes nothing
        with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
            _migration().upgrade()

    from config_crypto import decrypt, is_encrypted

    with engine.connect() as conn:
        rows = dict(conn.execute(sa.text("SELECT key, value FROM config_entries")).fetchall())
    assert is_encrypted(rows["tvdb_pin"])
    assert decrypt(rows["tvdb_pin"]) == "1234"
    assert rows["target_language"] == "de"
