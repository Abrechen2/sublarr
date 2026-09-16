"""PostgreSQL-specific backup/restore helpers for DatabaseBackup.

Extracted from database_backup.py. Provides:

- _is_postgresql / _parse_pg_url / _get_database_url — dialect probes
  and URL helpers used by the main class.
- _PostgresBackupMixin — methods _backup_postgresql / _restore_postgresql
  consumed by ``DatabaseBackup`` via multiple inheritance. They shell out
  to ``pg_dump`` / ``pg_restore`` with a custom (``-Fc``) format.
"""

import contextlib
import logging
import os
import re
import subprocess
from datetime import UTC, datetime
from urllib.parse import urlparse

from error_handler import DatabaseBackupError, DatabaseRestoreError

logger = logging.getLogger(__name__)


def _is_postgresql() -> bool:
    """Detect if the current database backend is PostgreSQL."""
    try:
        from extensions import db

        return db.engine.dialect.name == "postgresql"
    except Exception:
        return False


def _parse_pg_url(database_url: str) -> dict:
    """Parse a PostgreSQL URL into connection components.

    Returns dict with host, port, dbname, user, password.
    """
    parsed = urlparse(database_url)
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "dbname": (parsed.path or "/sublarr").lstrip("/"),
        "user": parsed.username or "sublarr",
        "password": parsed.password or "",
    }


def _get_database_url() -> str:
    """Get the current database URL from config."""
    try:
        from config import get_settings

        return get_settings().get_database_url()
    except Exception:
        return ""


def _server_major_version() -> int | None:
    """Major version of the connected PostgreSQL server, or None if unknown."""
    try:
        from sqlalchemy import text

        from extensions import db

        with db.engine.connect() as conn:
            return int(conn.execute(text("SHOW server_version_num")).scalar()) // 10000
    except Exception as exc:  # noqa: BLE001 — unknown version skips only the version check
        logger.debug("Could not read PostgreSQL server version: %s", exc)
        return None


_DUMPED_BY = re.compile(r"Dumped by pg_dump version:\s*(\d+)")


class _PostgresBackupMixin:
    """pg_dump / pg_restore methods mixed into DatabaseBackup."""

    # These attributes are provided by the host class; declared here only for
    # static analysers — no runtime effect.
    backup_dir: str

    def _backup_postgresql(self, label: str = "daily") -> dict:
        """Create a backup using pg_dump (custom format for compression)."""
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        filename = f"sublarr_{label}_{timestamp}.pgdump"
        dest = os.path.join(self.backup_dir, filename)

        database_url = _get_database_url()
        if not database_url:
            raise DatabaseBackupError(
                "No database URL configured for PostgreSQL backup",
            )

        pg = _parse_pg_url(database_url)
        env = os.environ.copy()
        env["PGPASSWORD"] = pg["password"]

        cmd = [
            "pg_dump",
            "-h",
            pg["host"],
            "-p",
            pg["port"],
            "-U",
            pg["user"],
            "-Fc",  # Custom format (compressed)
            "-f",
            dest,
            pg["dbname"],
        ]

        try:
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )
            if result.returncode != 0:
                raise DatabaseBackupError(
                    f"pg_dump failed (exit {result.returncode}): {result.stderr}",
                    context={"dest": dest, "stderr": result.stderr},
                )
        except subprocess.TimeoutExpired:
            if os.path.exists(dest):
                with contextlib.suppress(OSError):
                    os.remove(dest)
            raise DatabaseBackupError(
                "pg_dump timed out after 300 seconds",
                context={"dest": dest},
            )
        except DatabaseBackupError:
            raise
        except Exception as exc:
            if os.path.exists(dest):
                with contextlib.suppress(OSError):
                    os.remove(dest)
            raise DatabaseBackupError(
                f"PostgreSQL backup failed: {exc}",
                context={"dest": dest},
            ) from exc

        size = os.path.getsize(dest) if os.path.exists(dest) else 0

        logger.info("PostgreSQL backup created: %s (%d bytes)", dest, size)
        return {
            "path": dest,
            "filename": filename,
            "size_bytes": size,
            "verified": True,  # pg_dump exit 0 is sufficient verification
            "timestamp": timestamp,
            "label": label,
            "backend": "postgresql",
        }

    def _check_pg_archive(self, backup_path: str) -> None:
        """Refuse an archive that cannot be restored here — before anything changes.

        ``pg_restore --list`` reads only the archive, so a corrupt dump fails
        here instead of half-way through a restore. A dump written by a newer
        pg_dump than the server's major version carries settings the server
        does not know (pg_dump 17 against PostgreSQL 16: ``SET
        transaction_timeout``), so it is rejected with the versions named.
        """
        try:
            listing = subprocess.run(
                ["pg_restore", "--list", backup_path],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise DatabaseRestoreError(
                f"Could not read PostgreSQL backup: {exc}",
                context={"backup_path": backup_path},
            ) from exc
        if listing.returncode != 0:
            raise DatabaseRestoreError(
                "Backup file is not a readable PostgreSQL archive — nothing was changed",
                context={"backup_path": backup_path, "stderr": listing.stderr.strip()},
            )
        match = _DUMPED_BY.search(listing.stdout or "")
        server_major = _server_major_version()
        if match and server_major is not None and int(match.group(1)) > server_major:
            raise DatabaseRestoreError(
                f"Backup was written by pg_dump {match.group(1)} and cannot be restored into "
                f"PostgreSQL {server_major} — nothing was changed",
                context={"backup_path": backup_path},
                troubleshooting=(
                    "Restore it with pg_restore from the same PostgreSQL major version as the "
                    "server, or upgrade the server."
                ),
            )

    def _restore_postgresql(self, backup_path: str) -> dict:
        """Restore a PostgreSQL backup using pg_restore, atomically."""
        database_url = _get_database_url()
        if not database_url:
            raise DatabaseRestoreError(
                "No database URL configured for PostgreSQL restore",
            )

        self._check_pg_archive(backup_path)

        pg = _parse_pg_url(database_url)
        env = os.environ.copy()
        env["PGPASSWORD"] = pg["password"]

        cmd = [
            "pg_restore",
            "-h",
            pg["host"],
            "-p",
            pg["port"],
            "-U",
            pg["user"],
            "-d",
            pg["dbname"],
            "--clean",
            "--if-exists",
            # One transaction, stop at the first error: a failing restore
            # leaves the database exactly as it was.
            "--single-transaction",
            "--exit-on-error",
            backup_path,
        ]

        try:
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=300,
            )
            # With --exit-on-error any non-zero exit is a failure. Matching an
            # upper-case "ERROR" missed pg_restore's lower-case "error:" and
            # reported a corrupt dump as restored.
            if result.returncode != 0:
                raise DatabaseRestoreError(
                    f"pg_restore failed (exit {result.returncode}): {result.stderr}",
                    context={"backup_path": backup_path, "stderr": result.stderr},
                )
        except DatabaseRestoreError:
            raise
        except subprocess.TimeoutExpired:
            raise DatabaseRestoreError(
                "pg_restore timed out after 300 seconds",
                context={"backup_path": backup_path},
            )
        except Exception as exc:
            raise DatabaseRestoreError(
                f"PostgreSQL restore failed: {exc}",
                context={"backup_path": backup_path},
            ) from exc

        logger.info("PostgreSQL database restored from %s", backup_path)
        return {
            "restored_from": backup_path,
            "backend": "postgresql",
        }
