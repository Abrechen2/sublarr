"""SQLite database backup with rotation and verification.

Uses the SQLite Online Backup API (``source.backup(target)``) for safe,
consistent backups without blocking writes.

Backup rotation:
    - daily:   keep N most recent  (default 7)
    - weekly:  keep N most recent  (default 4)
    - monthly: keep N most recent  (default 3)
"""

import os
import re
import time
import shutil
import sqlite3
import logging
import threading
from datetime import datetime, timezone
from typing import Optional

from error_handler import DatabaseBackupError, DatabaseRestoreError

logger = logging.getLogger(__name__)


class DatabaseBackup:
    """Manages backup creation, verification, rotation, and restore."""

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

    # ── Create backup ────────────────────────────────────────────────────

    def create_backup(self, label: str = "daily") -> dict:
        """Create a verified backup using the SQLite backup API.

        Args:
            label: Rotation bucket — ``daily``, ``weekly``, or ``monthly``.

        Returns:
            Dict with ``path``, ``size_bytes``, ``verified``, ``timestamp``.

        Raises:
            DatabaseBackupError: On any failure.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
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
                try:
                    os.remove(dest)
                except OSError:
                    pass
            raise DatabaseBackupError(
                f"Backup failed: {exc}",
                context={"dest": dest},
            ) from exc

        # Verify
        verified = self._verify_backup(dest)
        size = os.path.getsize(dest)

        logger.info(
            "Backup created: %s (%d bytes, verified=%s)", dest, size, verified
        )
        return {
            "path": dest,
            "filename": filename,
            "size_bytes": size,
            "verified": verified,
            "timestamp": timestamp,
            "label": label,
        }

    # ── Verify ───────────────────────────────────────────────────────────

    @staticmethod
    def _verify_backup(path: str) -> bool:
        """Run ``PRAGMA integrity_check`` on a backup file."""
        try:
            conn = sqlite3.connect(path)
            result = conn.execute("PRAGMA integrity_check").fetchone()
            conn.close()
            return result is not None and result[0] == "ok"
        except Exception as exc:
            logger.warning("Backup verification failed for %s: %s", path, exc)
            return False

    # ── List backups ─────────────────────────────────────────────────────

    def list_backups(self) -> list[dict]:
        """Return metadata for every backup file in the backup directory."""
        backups: list[dict] = []
        pattern = re.compile(r"^sublarr_(daily|weekly|monthly)_(\d{8}_\d{6})\.db$")

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
            backups.append({
                "filename": name,
                "path": path,
                "label": match.group(1),
                "timestamp": match.group(2),
                "size_bytes": size,
            })

        return backups

    # ── Restore ──────────────────────────────────────────────────────────

    def restore_backup(self, backup_path: str) -> dict:
        """Restore a backup by replacing the current database file.

        Creates a safety backup of the current DB before restoring.

        Args:
            backup_path: Absolute path to the backup file.

        Returns:
            Dict with ``restored_from``, ``safety_backup``.

        Raises:
            DatabaseRestoreError: On any failure.
        """
        if not os.path.exists(backup_path):
            raise DatabaseRestoreError(
                f"Backup file not found: {backup_path}",
                context={"backup_path": backup_path},
            )

        # Verify the backup before restoring
        if not self._verify_backup(backup_path):
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
            try:
                shutil.copy2(safety_path, self.db_path)
            except Exception:
                pass
            raise DatabaseRestoreError(
                f"Restore failed (rolled back): {exc}",
                context={"backup_path": backup_path},
            ) from exc

        logger.info("Database restored from %s (safety backup at %s)", backup_path, safety_path)
        return {
            "restored_from": backup_path,
            "safety_backup": safety_path,
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

_scheduler_thread: Optional[threading.Thread] = None
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
            now = datetime.now(timezone.utc)
            target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            if target <= now:
                from datetime import timedelta
                target += timedelta(days=1)
            wait_secs = (target - now).total_seconds()
            if _scheduler_stop.wait(timeout=wait_secs):
                break  # Stopped

            try:
                # Determine label
                day = datetime.now(timezone.utc)
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
