"""A restore either happens completely and is reported truthfully, or not at all.

VM test of 1.14.3-rc.4 (2026-09-16), all reproduced against the released image:

1. SQLite: the restore route called ``db.close_db()`` — a no-op since the move to
   SQLAlchemy — and swapped the database file under open pooled connections. The
   API answered ``db_restored: true``; afterwards a deleted profile was still
   missing and a fresh SQLite connection failed with "disk I/O error".
2. PostgreSQL: a dump written by pg_dump 17 against a PostgreSQL 16 server failed
   on ``SET transaction_timeout`` — after the restore had already changed data.
3. PostgreSQL: a corrupt ``sublarr.pgdump`` was reported as restored, because
   failure was only recognised when stderr contained upper-case "ERROR".
4. ``GET /config`` kept serving the pre-restore values from its 60 s cache.

Also covered: a full ZIP restore no longer imports config.json before the
database restore it belongs to, and a restore is refused while jobs run.
"""

import io
import sqlite3
import subprocess
import zipfile
from unittest.mock import patch

import pytest

from error_handler import DatabaseRestoreError

# ── helpers ──────────────────────────────────────────────────────────────────


@pytest.fixture
def keep_encryption_key():
    """Put the real key file back after a test that swaps it.

    The key lives in the shared config dir, so a test that leaves a broken key
    behind poisons every other test in the run ("Fernet key must be 32 url-safe
    base64-encoded bytes").
    """
    import config_crypto

    config_crypto.encrypt("seed")  # make sure the file exists
    path = config_crypto._key_path()
    with open(path, "rb") as fh:
        original = fh.read()
    try:
        yield path
    finally:
        with open(path, "wb") as fh:
            fh.write(original)
        config_crypto.reset_cipher_cache()


@pytest.fixture
def backups(client, tmp_path):
    """backup_dir is a DB-only UI setting: set it the way the UI does, so it
    survives the settings reload every PUT /config performs — and so no test
    writes to the default /config/backups (a real directory on a dev machine)."""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    response = client.put("/api/v1/config", json={"backup_dir": str(backup_dir)})
    assert response.status_code == 200, response.get_json()
    return backup_dir


def _page_size(client):
    return client.get("/api/v1/config").get_json()["items_per_page"]


def _set_page_size(client, value):
    assert client.put("/api/v1/config", json={"items_per_page": value}).status_code == 200


def _profile_names(client):
    with client.application.app_context():
        from db.repositories.profiles import ProfileRepository

        return {p["name"] for p in ProfileRepository().get_profiles()}


def _create_profile(client, name):
    with client.application.app_context():
        from db.repositories.profiles import ProfileRepository

        return ProfileRepository().create_profile(
            name=name,
            source_lang="en",
            source_name="English",
            target_langs=["de"],
            target_names=["German"],
        )


def _delete_profile(client, profile_id):
    with client.application.app_context():
        from db.repositories.profiles import ProfileRepository

        ProfileRepository().delete_profile(profile_id)


def _full_backup_zip(client):
    created = client.post("/api/v1/backup/full")
    assert created.status_code == 201, created.get_json()
    download = client.get(f"/api/v1/backup/full/download/{created.get_json()['filename']}")
    assert download.status_code == 200
    return download.data


def _restore_zip(client, data):
    return client.post(
        "/api/v1/backup/full/restore",
        data={"file": (io.BytesIO(data), "backup.zip")},
        content_type="multipart/form-data",
    )


def _fresh_sqlite_count(table):
    from config import get_settings

    conn = sqlite3.connect(get_settings().db_path)
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


# ── 1 + 4: SQLite full restore through the real routes ───────────────────────


def test_full_sqlite_restore_brings_data_back_and_leaves_the_database_usable(client, backups):
    _set_page_size(client, 25)
    profile_id = _create_profile(client, "Restore me")
    zip_bytes = _full_backup_zip(client)

    _delete_profile(client, profile_id)
    _set_page_size(client, 47)
    assert _page_size(client) == 47  # primes the 60 s response cache
    assert "Restore me" not in _profile_names(client)

    response = _restore_zip(client, zip_bytes)

    assert response.status_code == 200, response.get_json()
    assert response.get_json()["db_restored"] is True
    assert "Restore me" in _profile_names(client)
    assert _page_size(client) == 25
    assert _fresh_sqlite_count("language_profiles") >= 1


def test_plain_sqlite_restore_invalidates_the_config_cache(client, backups):
    _set_page_size(client, 25)
    created = client.post("/api/v1/database/backup", json={"label": "manual"})
    assert created.status_code in (200, 201), created.get_json()
    filename = created.get_json()["filename"]

    _set_page_size(client, 47)
    assert _page_size(client) == 47

    response = client.post("/api/v1/database/restore", json={"filename": filename, "confirm": True})

    assert response.status_code == 200, response.get_json()
    assert _page_size(client) == 25
    assert _fresh_sqlite_count("config_entries") >= 1


# ── full restore: nothing changes when the database part is unusable ─────────


def test_corrupt_database_in_zip_leaves_config_untouched(client, backups):
    import json

    _set_page_size(client, 25)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "manifest.json",
            json.dumps({"schema_version": 1, "db_backend": "sqlite", "contents": ["config", "db"]}),
        )
        zf.writestr("config.json", json.dumps({"items_per_page": 99}))
        zf.writestr("sublarr.db", b"this is not a sqlite database")

    response = _restore_zip(client, buf.getvalue())

    assert response.status_code >= 400
    with client.application.app_context():
        from db.config import get_config_entry

        assert str(get_config_entry("items_per_page")) == "25"


def test_sqlite_restore_under_a_connection_held_by_another_thread(client, backups):
    """VM test of 1.14.4-rc.2: a second thread holding an ordinary pooled
    connection (having read a setting) survived release_db_connections(), the
    file was swapped under it, the restore returned 500 and a fresh SQLite
    connection failed with "disk I/O error". No running job was needed."""
    import threading

    _set_page_size(client, 25)
    created = client.post("/api/v1/database/backup", json={"label": "manual"})
    filename = created.get_json()["filename"]
    _set_page_size(client, 47)

    holding = threading.Event()
    release = threading.Event()
    seen_after = {}

    def hold_connection():
        from sqlalchemy import text

        with client.application.app_context():
            from extensions import db

            with db.engine.connect() as conn:
                conn.execute(text("SELECT value FROM config_entries LIMIT 1")).fetchall()
                holding.set()
                release.wait(30)
            with db.engine.connect() as conn:
                row = conn.execute(
                    text("SELECT value FROM config_entries WHERE key = 'items_per_page'")
                ).fetchone()
                seen_after["items_per_page"] = row[0] if row else None

    worker = threading.Thread(target=hold_connection)
    worker.start()
    assert holding.wait(10)
    try:
        response = client.post(
            "/api/v1/database/restore", json={"filename": filename, "confirm": True}
        )
    finally:
        release.set()
        worker.join(30)

    assert response.status_code == 200, response.get_json()
    assert _page_size(client) == 25
    assert _fresh_sqlite_count("config_entries") >= 1  # no "disk I/O error"
    assert seen_after["items_per_page"] == "25"


def _replace_zip_member(zip_bytes, name, content):
    """Rewrite ``name`` inside the archive, adding it when it is not there yet."""
    src = zipfile.ZipFile(io.BytesIO(zip_bytes))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as dst:
        for info in src.infolist():
            data = content if info.filename == name else src.read(info.filename)
            dst.writestr(info.filename, data)
        if name not in src.namelist():
            dst.writestr(name, content)
    return buf.getvalue()


@pytest.mark.parametrize("config_json", ["[]", '"text"', "42"])
def test_config_json_that_is_not_an_object_changes_nothing(client, backups, config_json):
    """VM test of 1.14.4-rc.2: config.json = [] parsed fine, the database was
    replaced, and only then did ``.items()`` fail — HTTP 500 with the setting
    changed and a deleted profile restored."""
    _set_page_size(client, 25)
    profile_id = _create_profile(client, "Partial restore")
    zip_bytes = _replace_zip_member(_full_backup_zip(client), "config.json", config_json)

    _delete_profile(client, profile_id)
    _set_page_size(client, 47)

    response = _restore_zip(client, zip_bytes)

    assert response.status_code == 400, response.get_json()
    assert _page_size(client) == 47
    assert "Partial restore" not in _profile_names(client)


def test_a_full_backup_larger_than_the_global_upload_limit_can_be_restored(client, backups):
    """RC 2026-09-17: a production-sized full backup is 64 MB, but every request
    body is capped at 16 MB, so restoring it answered 413 — Sublarr offered a
    backup it could not take back."""
    import os

    zip_bytes = _full_backup_zip(client)
    padded = _replace_zip_member(zip_bytes, "padding.bin", os.urandom(17 * 1024 * 1024))
    assert len(padded) > 16 * 1024 * 1024, "the upload must exceed the global limit"

    response = _restore_zip(client, padded)

    assert response.status_code == 200, f"HTTP {response.status_code}"


def test_manifest_that_is_not_an_object_is_rejected(client, backups):
    zip_bytes = _replace_zip_member(_full_backup_zip(client), "manifest.json", "[1]")

    response = _restore_zip(client, zip_bytes)

    assert response.status_code == 400, response.get_json()


# ── restore refused while jobs run ───────────────────────────────────────────


def test_restore_is_refused_while_a_job_is_running(client, backups):
    created = client.post("/api/v1/database/backup", json={"label": "manual"})
    filename = created.get_json()["filename"]
    with client.application.app_context():
        from db.jobs import create_job, update_job

        job = create_job("/media/running.mkv")
        update_job(job["id"], "running")

    response = client.post("/api/v1/database/restore", json={"filename": filename, "confirm": True})

    assert response.status_code == 409
    assert "running" in response.get_json()["error"].lower()


# ── 2 + 3: PostgreSQL restore (pg tools mocked at the subprocess boundary) ───


class _Run:
    """Stand-in for subprocess.run that answers per pg_restore invocation."""

    def __init__(self, list_result, restore_result=None):
        self.list_result = list_result
        self.restore_result = restore_result or subprocess.CompletedProcess([], 0, "", "")
        self.calls = []

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        if "--list" in cmd:
            return self.list_result
        return self.restore_result


def _header(dumped_by="16.15", dumped_from="16.15"):
    return (
        ";\n; Archive created at 2026-09-16 21:09:00 UTC\n"
        f";     Dumped from database version: {dumped_from}\n"
        f";     Dumped by pg_dump version: {dumped_by}\n;\n"
    )


@pytest.fixture
def pg_backup(tmp_path, monkeypatch):
    import database_backup_postgres as pgmod
    from database_backup import DatabaseBackup

    monkeypatch.setattr(
        pgmod, "_get_database_url", lambda: "postgresql://sublarr:secret@pg:5432/sublarr"
    )
    monkeypatch.setattr(pgmod, "_server_major_version", lambda: 16)
    dump = tmp_path / "sublarr.pgdump"
    dump.write_bytes(b"PGDMP fake")
    backup = DatabaseBackup(db_path=str(tmp_path / "x.db"), backup_dir=str(tmp_path / "b"))
    return backup, str(dump)


def _restores(run):
    return [c for c in run.calls if "--list" not in c]


def test_corrupt_pgdump_is_rejected_before_anything_changes(pg_backup, monkeypatch):
    backup, dump = pg_backup
    run = _Run(
        subprocess.CompletedProcess(
            [], 1, "", "pg_restore: error: input file does not appear to be a valid archive"
        )
    )
    monkeypatch.setattr(subprocess, "run", run)

    with pytest.raises(DatabaseRestoreError):
        backup.restore_backup(dump)

    assert _restores(run) == []


def test_dump_from_a_newer_pg_dump_than_the_server_is_rejected_up_front(pg_backup, monkeypatch):
    backup, dump = pg_backup
    run = _Run(subprocess.CompletedProcess([], 0, _header(dumped_by="17.11"), ""))
    monkeypatch.setattr(subprocess, "run", run)

    with pytest.raises(DatabaseRestoreError) as exc:
        backup.restore_backup(dump)

    assert "17" in str(exc.value) and "16" in str(exc.value)
    assert _restores(run) == []


def test_restore_runs_in_one_transaction_and_stops_at_the_first_error(pg_backup, monkeypatch):
    backup, dump = pg_backup
    run = _Run(subprocess.CompletedProcess([], 0, _header(), ""))
    monkeypatch.setattr(subprocess, "run", run)

    backup.restore_backup(dump)

    (restore_cmd,) = _restores(run)
    assert "--single-transaction" in restore_cmd
    assert "--exit-on-error" in restore_cmd


def test_restore_releases_this_processs_connections_before_pg_restore_runs(pg_backup, monkeypatch):
    """RC 2026-09-17, prod-sized dump: pg_restore waited 300 s on DROP INDEX
    idx_jobs_status. The lock was held by this very request's session, left
    "idle in transaction" by the running-jobs check, so the restore could never
    proceed and timed out. The session must be released before pg_restore starts.
    """
    import services.database_restore as restore_mod

    backup, dump = pg_backup
    events = []
    monkeypatch.setattr(restore_mod, "release_db_connections", lambda: events.append("release"))
    inner = _Run(subprocess.CompletedProcess([], 0, _header(), ""))

    def run(cmd, **kwargs):
        events.append("list" if "--list" in cmd else "restore")
        return inner(cmd, **kwargs)

    monkeypatch.setattr(subprocess, "run", run)

    backup.restore_backup(dump)

    assert events.index("release") < events.index("restore")
    assert events.index("release") > events.index("list")


def test_restore_cancelled_by_the_lock_watchdog_says_the_database_is_in_use(pg_backup, monkeypatch):
    """A lock held by another session must fail the restore and say why.

    PGOPTIONS lock_timeout was tried first and did nothing: the dump itself runs
    ``SET lock_timeout = 0`` (VM test of 1.14.4-rc.2 waited 47.7 s on a 45 s
    lock). The watchdog cancels pg_restore's backend instead.
    """
    import database_backup_postgres as pgmod

    backup, dump = pg_backup
    seen_env = {}

    class _Cancelled:
        cancelled = True

        def stop(self):
            pass

    monkeypatch.setattr(pgmod, "_start_lock_watchdog", lambda url, app_name: _Cancelled())
    inner = _Run(
        subprocess.CompletedProcess([], 0, _header(), ""),
        subprocess.CompletedProcess(
            [], 1, "", "pg_restore: error: canceling statement due to user request"
        ),
    )

    def run(cmd, **kwargs):
        if "--list" not in cmd:
            seen_env.update(kwargs.get("env") or {})
        return inner(cmd, **kwargs)

    monkeypatch.setattr(subprocess, "run", run)

    with pytest.raises(DatabaseRestoreError) as exc:
        backup.restore_backup(dump)

    assert seen_env.get("PGAPPNAME", "").startswith("sublarr-restore")
    assert "nothing was changed" in str(exc.value)
    assert "in use" in str(exc.value)


def test_a_locked_jobs_table_answers_instead_of_hanging(client, backups):
    """RC 2026-09-17: with the jobs table locked by another connection, the
    request hung in its own "are jobs running?" check for the whole 120 s the
    lock was held — before pg_restore, so the lock watchdog never saw it."""
    from sqlalchemy.exc import OperationalError

    created = client.post("/api/v1/database/backup", json={"label": "manual"})
    filename = created.get_json()["filename"]

    def blocked(*_args, **_kwargs):
        raise OperationalError("SELECT jobs", {}, Exception("canceling statement due to timeout"))

    with patch("services.database_restore._count_running_jobs", side_effect=blocked):
        response = client.post(
            "/api/v1/database/restore", json={"filename": filename, "confirm": True}
        )

    assert response.status_code == 409
    assert "busy" in response.get_json()["error"].lower()


# The watchdog's own unit tests live in tests/test_pg_restore_watchdog.py.


def test_any_nonzero_pg_restore_exit_is_a_failure(pg_backup, monkeypatch):
    backup, dump = pg_backup
    run = _Run(
        subprocess.CompletedProcess([], 0, _header(), ""),
        subprocess.CompletedProcess(
            [], 1, "", 'pg_restore: error: could not execute query: relation "x" does not exist'
        ),
    )
    monkeypatch.setattr(subprocess, "run", run)

    with pytest.raises(DatabaseRestoreError):
        backup.restore_backup(dump)


# ── PostgreSQL client matching the server's major version (owner option B) ───


@pytest.fixture
def pg_lib(tmp_path, monkeypatch):
    """A fake /usr/lib/postgresql with clients 15, 16 and 17 installed."""
    import database_backup_postgres as pgmod

    root = tmp_path / "pglib"
    for major in (15, 16, 17):
        bindir = root / str(major) / "bin"
        bindir.mkdir(parents=True)
        for tool in ("pg_dump", "pg_restore"):
            (bindir / tool).write_text("#!/bin/sh\n")
    monkeypatch.setattr(pgmod, "PG_LIB_ROOT", str(root))
    return root


def test_backup_uses_pg_dump_of_the_servers_major_version(pg_backup, pg_lib, monkeypatch):
    backup, _dump = pg_backup
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        dest = cmd[cmd.index("-f") + 1]
        open(dest, "wb").close()
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", run)
    import os

    os.makedirs(backup.backup_dir, exist_ok=True)
    backup._backup_postgresql("manual")

    assert calls[0][0] == str(pg_lib / "16" / "bin" / "pg_dump")


def test_restore_uses_pg_restore_of_the_servers_major_version(pg_backup, pg_lib, monkeypatch):
    backup, dump = pg_backup
    run = _Run(subprocess.CompletedProcess([], 0, _header(), ""))
    monkeypatch.setattr(subprocess, "run", run)

    backup.restore_backup(dump)

    (listing,) = [c for c in run.calls if "--list" in c]
    (restore,) = _restores(run)
    assert listing[0] == str(pg_lib / "17" / "bin" / "pg_restore")  # newest reads any archive
    assert restore[0] == str(pg_lib / "16" / "bin" / "pg_restore")


def test_next_newer_client_is_used_when_the_exact_major_is_missing(pg_lib, monkeypatch):
    import database_backup_postgres as pgmod

    assert pgmod._pg_binary("pg_dump", 14) == str(pg_lib / "15" / "bin" / "pg_dump")
    assert pgmod._pg_binary("pg_dump", 18) == str(pg_lib / "17" / "bin" / "pg_dump")


def test_without_versioned_clients_the_path_tool_is_used(tmp_path, monkeypatch):
    import database_backup_postgres as pgmod

    monkeypatch.setattr(pgmod, "PG_LIB_ROOT", str(tmp_path / "missing"))

    assert pgmod._pg_binary("pg_restore", 16) == "pg_restore"


# ── cold-review findings (Codex, 2026-09-17) ─────────────────────────────────


def test_a_failure_after_the_database_restore_keeps_its_matching_key(
    client, backups, keep_encryption_key
):
    """The rollback put the OLD encryption key back even when the database had
    already been replaced, leaving the restored rows undecryptable. When the
    database is in, its key must stay with it."""
    zip_bytes = _full_backup_zip(client)
    key_path = keep_encryption_key
    with open(key_path, "rb") as fh:
        key_in_backup = fh.read()
    with open(key_path, "wb") as fh:  # a different key is live now
        fh.write(b"0" * len(key_in_backup))

    with patch("db.config.save_config_entry", side_effect=RuntimeError("disk full")):
        response = _restore_zip(client, zip_bytes)

    assert response.status_code >= 400
    with open(key_path, "rb") as fh:
        assert fh.read() == key_in_backup, "the key of the restored database must be kept"


def test_a_failure_before_the_database_restore_rolls_the_key_back(
    client, backups, keep_encryption_key
):
    """The other direction is unchanged: nothing was replaced, so the old key stays."""
    zip_bytes = _replace_zip_member(_full_backup_zip(client), "sublarr.db", b"not a database")
    key_path = keep_encryption_key
    with open(key_path, "wb") as fh:
        fh.write(b"1" * 44)

    response = _restore_zip(client, zip_bytes)

    assert response.status_code >= 400
    with open(key_path, "rb") as fh:
        assert fh.read() == b"1" * 44, "an untouched database must keep the old key"


def test_a_sqlite_restore_gives_up_instead_of_waiting_forever(tmp_path, monkeypatch):
    """timeout= only configures SQLite's busy handler; the backup API retries
    SQLITE_BUSY indefinitely, so a destination held by a writer could occupy the
    restore thread for good."""
    import sqlite3

    import database_backup

    source = tmp_path / "source.db"
    sqlite3.connect(source).executescript("CREATE TABLE t(x); INSERT INTO t VALUES (1);")
    target = tmp_path / "live.db"
    sqlite3.connect(target).executescript("CREATE TABLE t(x);")

    blocker = sqlite3.connect(target, isolation_level=None)
    blocker.execute("BEGIN EXCLUSIVE")
    monkeypatch.setattr(database_backup, "_SQLITE_RESTORE_DEADLINE_S", 2)
    try:
        with pytest.raises(Exception) as exc:
            database_backup._sqlite_copy(str(source), str(target))
    finally:
        blocker.rollback()
        blocker.close()

    assert "busy" in str(exc.value).lower() or "lock" in str(exc.value).lower(), str(exc.value)
    assert sqlite3.connect(target).execute("SELECT count(*) FROM t").fetchone()[0] == 0


def test_a_backup_with_a_different_page_size_still_restores(tmp_path):
    """SQLite refuses a backup into a WAL database when the page sizes differ."""
    import sqlite3

    from database_backup import _sqlite_copy

    source = tmp_path / "source.db"
    conn = sqlite3.connect(source, isolation_level=None)
    conn.execute("PRAGMA page_size=8192")
    conn.execute("VACUUM")
    conn.execute("CREATE TABLE t(x)")
    conn.execute("INSERT INTO t VALUES (7)")
    conn.close()

    target = tmp_path / "live.db"
    conn = sqlite3.connect(target, isolation_level=None)
    conn.execute("PRAGMA page_size=4096")
    conn.execute("VACUUM")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE t(x)")
    conn.close()

    _sqlite_copy(str(source), str(target))

    assert sqlite3.connect(target).execute("SELECT x FROM t").fetchone()[0] == 7


def test_the_uploaded_archive_is_not_read_into_memory(client, backups):
    """A 4 GiB allowance plus file.read() is a memory-exhaustion risk: the whole
    archive was materialised before the database member was even looked at.
    Werkzeug spools the upload to disk, so the archive is opened on that stream."""
    import routes.system.backup_full as mod

    zip_bytes = _full_backup_zip(client)
    opened_with = []
    real_zipfile = mod.zipfile.ZipFile

    def spy(source, *args, **kwargs):
        opened_with.append(type(source).__name__)
        return real_zipfile(source, *args, **kwargs)

    with patch.object(mod.zipfile, "ZipFile", spy):
        response = _restore_zip(client, zip_bytes)

    assert response.status_code == 200, response.get_json()
    assert opened_with, "the route must open the archive itself"
    assert "BytesIO" not in opened_with, opened_with


def test_a_second_restore_is_refused_while_one_runs(client, backups):
    """Cold review (Codex, 2026-09-17): the running-jobs check is a snapshot and
    said nothing about another restore already replacing the database."""
    import threading

    from services.database_restore import restore_guard

    created = client.post("/api/v1/database/backup", json={"label": "manual"})
    filename = created.get_json()["filename"]

    holding = threading.Event()
    release = threading.Event()

    def hold():
        with restore_guard():
            holding.set()
            release.wait(30)

    worker = threading.Thread(target=hold)
    worker.start()
    assert holding.wait(10)
    try:
        response = client.post(
            "/api/v1/database/restore", json={"filename": filename, "confirm": True}
        )
    finally:
        release.set()
        worker.join(30)

    assert response.status_code == 409
    assert "restore" in response.get_json()["error"].lower()


def test_the_guard_is_released_again(client, backups):
    from services.database_restore import restore_guard

    with restore_guard():
        pass
    created = client.post("/api/v1/database/backup", json={"label": "manual"})
    response = client.post(
        "/api/v1/database/restore",
        json={"filename": created.get_json()["filename"], "confirm": True},
    )
    assert response.status_code == 200, response.get_json()
