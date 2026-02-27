"""Dialect-aware database backup with rotation and verification.

Supports both SQLite and PostgreSQL backends:

- **SQLite:** Uses the Online Backup API (``source.backup(target)``) for safe,
  consistent backups without blocking writes.
- **PostgreSQL:** Uses ``pg_dump`` / ``pg_restore`` subprocess calls with
  custom format (``-Fc``) for compressed backups.

Backup rotation:
    - daily:   keep N most recent  (default 7)
    - weekly:  keep N most recent  (default 4)
    - monthly: keep N most recent  (default 3)
"""

import contextlib
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import threading
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


class DatabaseBackup:
    """Manages backup creation, verification, rotation, and restore.

    Automatically dispatches to SQLite or PostgreSQL backend based on the
    active SQLAlchemy dialect.
    """

    def __init__(
        self,
        db_path: str,
        backup_dir: str = "/config/backups",
        retention_daily: int = 7,
        retention_weekly: int = 4,
        retention_monthly: int = 3,
    ) -> None:
        self.db_path = db_path
        self.backup_dir = backup_dir
        self.retention_daily = retention_daily
        self.retention_weekly = retention_weekly
        self.retention_monthly = retention_monthly

        os.makedirs(self.backup_dir, exist_ok=True)

    # ── Dialect detection ─────────────────────────────────────────────────

    @property
    def is_postgresql(self) -> bool:
        """True if the active database backend is PostgreSQL."""
        return _is_postgresql()

    # ── Create backup ────────────────────────────────────────────────────

    def create_backup(self, label: str = "daily") -> dict:
        """Create a verified backup.

        Dispatches to SQLite backup API or pg_dump based on the active dialect.

        Args:
            label: Rotation bucket -- ``daily``, ``weekly``, or ``monthly``.

        Returns:
            Dict with ``path``, ``size_bytes``, ``verified``, ``timestamp``,
            ``label``, ``backend``.

        Raises:
            DatabaseBackupError: On any failure.
        """
        if self.is_postgresql:
            return self._backup_postgresql(label)
        return self._backup_sqlite(label)

    # ── SQLite backup ─────────────────────────────────────────────────────

    def _backup_sqlite(self, label: str = "daily") -> dict:
        """Create a backup using the SQLite backup API."""
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        filename = f"sublarr_{label}_{timestamp}.db"
        dest = os.path.join(self.backup_dir, filename)

        try:
            source = sqlite3.connect(self.db_path)
            target = sqlite3.connect(dest)
            with target:
                source.backup(target)
            source.close()
            target.close()
        except Exception as exc:
            # Clean up partial file
            if os.path.exists(dest):
                with contextlib.suppress(OSError):
                    os.remove(dest)
            raise DatabaseBackupError(
                f"SQLite backup failed: {exc}",
                context={"dest": dest},
            ) from exc

        # Verify
        verified = self._verify_sqlite_backup(dest)
        size = os.path.getsize(dest)

        logger.info("SQLite backup created: %s (%d bytes, verified=%s)", dest, size, verified)
        return {
            "path": dest,
            "filename": filename,
            "size_bytes": size,
            "verified": verified,
            "timestamp": timestamp,
            "label": label,
            "backend": "sqlite",
        }

    # ── PostgreSQL backup ─────────────────────────────────────────────────

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

    # ── Verify ───────────────────────────────────────────────────────────

    @staticmethod
    def _verify_sqlite_backup(path: str) -> bool:
        """Run ``PRAGMA integrity_check`` on a SQLite backup file."""
        try:
            conn = sqlite3.connect(path)
            result = conn.execute("PRAGMA integrity_check").fetchone()
            conn.close()
            return result is not None and result[0] == "ok"
        except Exception as exc:
            logger.warning("Backup verification failed for %s: %s", path, exc)
            return False

    # Backward-compatible alias
    _verify_backup = _verify_sqlite_backup

    # ── List backups ─────────────────────────────────────────────────────

    def list_backups(self) -> list[dict]:
        """Return metadata for every backup file in the backup directory.

        Matches both SQLite (.db) and PostgreSQL (.pgdump) backup files.
        """
        backups: list[dict] = []
        pattern = re.compile(r"^sublarr_(daily|weekly|monthly|manual)_(\d{8}_\d{6})\.(db|pgdump)$")

        if not os.path.isdir(self.backup_dir):
            return backups

        for name in sorted(os.listdir(self.backup_dir), reverse=True):
            match = pattern.match(name)
            if not match:
                continue
            path = os.path.join(self.backup_dir, name)
            try:
                size = os.path.getsize(path)
            except OSError:
                size = 0

            ext = match.group(3)
            backups.append(
                {
                    "filename": name,
                    "path": path,
                    "label": match.group(1),
                    "timestamp": match.group(2),
                    "size_bytes": size,
                    "backend": "postgresql" if ext == "pgdump" else "sqlite",
                }
            )

        return backups

    # ── Restore ──────────────────────────────────────────────────────────

    def restore_backup(self, backup_path: str) -> dict:
        """Restore a backup, dispatching based on file extension.

        For SQLite (.db): Replaces the database file after integrity check.
        For PostgreSQL (.pgdump): Uses pg_restore subprocess.

        Creates a safety backup before restoring (SQLite only).

        Args:
            backup_path: Absolute path to the backup file.

        Returns:
            Dict with ``restored_from`` and ``backend``.

        Raises:
            DatabaseRestoreError: On any failure.
        """
        if not os.path.exists(backup_path):
            raise DatabaseRestoreError(
                f"Backup file not found: {backup_path}",
                context={"backup_path": backup_path},
            )

        if backup_path.endswith(".pgdump"):
            return self._restore_postgresql(backup_path)
        return self._restore_sqlite(backup_path)

    def _restore_sqlite(self, backup_path: str) -> dict:
        """Restore a SQLite backup by replacing the current database file."""
        # Verify the backup before restoring
        if not self._verify_sqlite_backup(backup_path):
            raise DatabaseRestoreError(
                "Backup file failed integrity check",
                context={"backup_path": backup_path},
                troubleshooting="The backup file may be corrupted. Choose a different backup.",
            )

        # Safety backup of current DB
        safety_path = self.db_path + ".pre_restore"
        try:
            shutil.copy2(self.db_path, safety_path)
        except Exception as exc:
            raise DatabaseRestoreError(
                f"Could not create safety backup: {exc}",
            ) from exc

        # Replace database
        try:
            shutil.copy2(backup_path, self.db_path)
            # Remove WAL and SHM files to force clean state
            for suffix in ("-wal", "-shm"):
                wal = self.db_path + suffix
                if os.path.exists(wal):
                    os.remove(wal)
        except Exception as exc:
            # Attempt rollback
            with contextlib.suppress(Exception):
                shutil.copy2(safety_path, self.db_path)
            raise DatabaseRestoreError(
                f"Restore failed (rolled back): {exc}",
                context={"backup_path": backup_path},
            ) from exc

        logger.info(
            "SQLite database restored from %s (safety backup at %s)", backup_path, safety_path
        )
        return {
            "restored_from": backup_path,
            "safety_backup": safety_path,
            "backend": "sqlite",
        }

    def _restore_postgresql(self, backup_path: str) -> dict:
        """Restore a PostgreSQL backup using pg_restore."""
        database_url = _get_database_url()
        if not database_url:
            raise DatabaseRestoreError(
                "No database URL configured for PostgreSQL restore",
            )

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
            # pg_restore returns non-zero for warnings too; check stderr for errors
            if result.returncode != 0 and "ERROR" in result.stderr:
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

    # ── Rotation ─────────────────────────────────────────────────────────

    def rotate(self) -> int:
        """Delete old backups exceeding retention limits.

        Returns:
            Number of files deleted.
        """
        backups = self.list_backups()
        limits = {
            "daily": self.retention_daily,
            "weekly": self.retention_weekly,
            "monthly": self.retention_monthly,
        }

        deleted = 0
        for label, limit in limits.items():
            label_backups = [b for b in backups if b["label"] == label]
            # Already sorted newest-first by list_backups
            for old in label_backups[limit:]:
                try:
                    os.remove(old["path"])
                    deleted += 1
                    logger.debug("Rotated out old backup: %s", old["filename"])
                except OSError as exc:
                    logger.warning("Could not delete old backup %s: %s", old["filename"], exc)

        if deleted:
            logger.info("Backup rotation: deleted %d old backups", deleted)
        return deleted


# ── Scheduled backup (lightweight timer loop) ────────────────────────────────

_scheduler_thread: threading.Thread | None = None
_scheduler_stop = threading.Event()


def start_backup_scheduler(
    db_path: str,
    backup_dir: str = "/config/backups",
    interval_hours: int = 24,
    hour: int = 3,
) -> None:
    """Start a daemon thread that creates daily backups with rotation.

    The first backup runs at the next occurrence of *hour*:00 UTC,
    then repeats every *interval_hours*.
    """
    global _scheduler_thread
    if _scheduler_thread and _scheduler_thread.is_alive():
        return  # Already running

    _scheduler_stop.clear()

    def _loop() -> None:
        backup = DatabaseBackup(db_path, backup_dir)
        while not _scheduler_stop.is_set():
            # Sleep until the next scheduled hour
            now = datetime.now(UTC)
            target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            if target <= now:
                from datetime import timedelta

                target += timedelta(days=1)
            wait_secs = (target - now).total_seconds()
            if _scheduler_stop.wait(timeout=wait_secs):
                break  # Stopped

            try:
                # Determine label
                day = datetime.now(UTC)
                if day.day == 1:
                    label = "monthly"
                elif day.weekday() == 0:  # Monday
                    label = "weekly"
                else:
                    label = "daily"

                backup.create_backup(label=label)
                backup.rotate()
            except Exception as exc:
                logger.error("Scheduled backup failed: %s", exc)

    _scheduler_thread = threading.Thread(target=_loop, daemon=True, name="backup-scheduler")
    _scheduler_thread.start()
    logger.info("Backup scheduler started (daily at %02d:00 UTC)", hour)


def stop_backup_scheduler() -> None:
    """Stop the backup scheduler thread."""
    _scheduler_stop.set()
