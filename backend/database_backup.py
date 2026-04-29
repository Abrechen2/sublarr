"""Dialect-aware database backup with rotation and verification.

Supports both SQLite and PostgreSQL backends:

- **SQLite:** Uses the Online Backup API (``source.backup(target)``) for safe,
  consistent backups without blocking writes.
- **PostgreSQL:** Uses ``pg_dump`` / ``pg_restore`` subprocess calls with
  custom format (``-Fc``) for compressed backups — implemented in the
  ``_PostgresBackupMixin`` sibling module.

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
import threading
from datetime import UTC, datetime

from database_backup_postgres import (  # noqa: F401 — re-exported for back-compat
    _get_database_url,
    _is_postgresql,
    _parse_pg_url,
    _PostgresBackupMixin,
)
from error_handler import DatabaseBackupError, DatabaseRestoreError

logger = logging.getLogger(__name__)


class DatabaseBackup(_PostgresBackupMixin):
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

# Polling cadence used while auto-backup is disabled. Short enough that
# toggling `backup_auto_enabled` ON in the UI takes effect promptly without
# a restart, long enough to avoid wasted wakeups.
_DISABLED_POLL_SECS = 60


def _label_for(now: datetime) -> str:
    """Pick the rotation bucket for *now* (1st of month → monthly; Monday → weekly)."""
    if now.day == 1:
        return "monthly"
    if now.weekday() == 0:
        return "weekly"
    return "daily"


def _read_auto_backup_settings() -> tuple[bool, int, bool, bool]:
    """Read the four `backup_auto_*` config fields with safe defaults.

    Returns (enabled, interval_hours, on_startup, notify_on_failure).
    Default fallbacks match config_settings.Settings.
    """
    try:
        from config import get_settings

        s = get_settings()
        enabled = bool(getattr(s, "backup_auto_enabled", False))
        interval = max(1, int(getattr(s, "backup_auto_interval_hours", 24) or 24))
        on_startup = bool(getattr(s, "backup_auto_on_startup", False))
        notify = bool(getattr(s, "backup_notify_on_failure", True))
        return enabled, interval, on_startup, notify
    except Exception:
        # Settings unavailable (e.g. import-time race): pretend disabled.
        logger.debug("backup scheduler: settings unavailable", exc_info=True)
        return False, 24, False, True


def _emit_backup_failure_notification(exc: Exception) -> None:
    """Best-effort send of an `error` event to Apprise. Never raises."""
    try:
        from notifier import send_notification

        send_notification(
            title="Sublarr backup failed",
            body=f"Scheduled database backup failed: {exc}",
            event_type="error",
        )
    except Exception:
        logger.debug("backup scheduler: notify-on-failure emit failed", exc_info=True)


def _run_one_backup(backup: "DatabaseBackup", notify_on_failure: bool) -> None:
    """Run a single backup + rotation. Captures failures locally."""
    try:
        backup.create_backup(label=_label_for(datetime.now(UTC)))
        backup.rotate()
    except Exception as exc:
        logger.error("Scheduled backup failed: %s", exc, exc_info=True)
        if notify_on_failure:
            _emit_backup_failure_notification(exc)


def start_backup_scheduler(
    db_path: str,
    backup_dir: str = "/config/backups",
    app=None,
) -> None:
    """Start a daemon thread that runs auto-backups when configured.

    Honours four config fields (writable from the UI):
      - `backup_auto_enabled`        — if False, the loop polls and skips runs
      - `backup_auto_interval_hours` — sleep duration between runs (>=1)
      - `backup_auto_on_startup`     — run one backup immediately on start
      - `backup_notify_on_failure`   — emit an `error` notification when
                                       create_backup raises

    `app` is the Flask app; needed because `notifier.send_notification`
    writes to `notification_history` and other DB-touching helpers
    require an app context.
    """
    global _scheduler_thread
    if _scheduler_thread and _scheduler_thread.is_alive():
        return

    _scheduler_stop.clear()

    def _loop() -> None:
        backup = DatabaseBackup(db_path, backup_dir)
        ran_startup = False

        while not _scheduler_stop.is_set():
            enabled, interval_hours, on_startup, notify_on_failure = _read_auto_backup_settings()

            if not enabled:
                # Auto-backup turned off — poll the toggle without burning
                # CPU. Reset on_startup tracking so re-enabling re-fires.
                ran_startup = False
                if _scheduler_stop.wait(timeout=_DISABLED_POLL_SECS):
                    break
                continue

            if on_startup and not ran_startup:
                ran_startup = True
                if app is not None:
                    with app.app_context():
                        _run_one_backup(backup, notify_on_failure)
                else:
                    _run_one_backup(backup, notify_on_failure)
                # Fall through into the regular interval wait.

            wait_secs = max(1, interval_hours) * 3600
            if _scheduler_stop.wait(timeout=wait_secs):
                break

            # Re-read the gate *after* the long sleep so a user who turned
            # auto-backup OFF mid-sleep doesn't get one final stale run.
            enabled, _interval_hours, _on_startup, notify_on_failure = _read_auto_backup_settings()
            if not enabled:
                continue

            if app is not None:
                with app.app_context():
                    _run_one_backup(backup, notify_on_failure)
            else:
                _run_one_backup(backup, notify_on_failure)

    _scheduler_thread = threading.Thread(target=_loop, daemon=True, name="backup-scheduler")
    _scheduler_thread.start()
    logger.info("Backup scheduler started (config-driven)")


def stop_backup_scheduler() -> None:
    """Stop the backup scheduler thread."""
    _scheduler_stop.set()
