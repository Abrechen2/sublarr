"""Hook and webhook repository using SQLAlchemy ORM.

Replaces the raw sqlite3 queries in db/hooks.py with SQLAlchemy ORM operations.
CRUD for hook_configs, webhook_configs, and hook_log tables.
Return types match the existing functions exactly.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, func, delete

from db.models.hooks import HookConfig, WebhookConfig, HookLog
from db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class HookRepository(BaseRepository):
    """Repository for hook_configs, webhook_configs, and hook_log tables."""

    # ---- Hook configs CRUD -------------------------------------------------------

    def create_hook(self, name: str, event_name: str, script_path: str,
                    timeout_seconds: int = 30, enabled: bool = True) -> dict:
        """Create a new hook configuration.

        Returns:
            Dict representing the created hook config.
        """
        now = self._now()
        hook = HookConfig(
            name=name,
            event_name=event_name,
            hook_type="script",
            enabled=1 if enabled else 0,
            script_path=script_path,
            timeout_seconds=timeout_seconds,
            last_triggered_at="",
            last_status="",
            trigger_count=0,
            created_at=now,
            updated_at=now,
        )
        self.session.add(hook)
        self._commit()

        return {
            "id": hook.id,
            "name": name,
            "event_name": event_name,
            "hook_type": "script",
            "enabled": 1 if enabled else 0,
            "script_path": script_path,
            "timeout_seconds": timeout_seconds,
            "last_triggered_at": "",
            "last_status": "",
            "trigger_count": 0,
            "created_at": now,
            "updated_at": now,
        }

    def get_hooks(self, event_name: str = None, enabled_only: bool = False) -> list:
        """Get all hook configs, optionally filtered by event name.

        Returns:
            List of hook config dicts.
        """
        stmt = select(HookConfig).order_by(HookConfig.id)
        if event_name:
            stmt = stmt.where(HookConfig.event_name == event_name)
        if enabled_only:
            stmt = stmt.where(HookConfig.enabled == 1)
        entries = self.session.execute(stmt).scalars().all()
        return [self._row_to_hook(e) for e in entries]

    def get_hook(self, hook_id: int) -> Optional[dict]:
        """Get a single hook config by ID."""
        entry = self.session.get(HookConfig, hook_id)
        if not entry:
            return None
        return self._row_to_hook(entry)

    def update_hook(self, hook_id: int, **kwargs) -> bool:
        """Update a hook config with arbitrary column values. Returns True if found."""
        entry = self.session.get(HookConfig, hook_id)
        if not entry:
            return False

        for key, value in kwargs.items():
            if hasattr(entry, key):
                setattr(entry, key, value)
        entry.updated_at = self._now()
        self._commit()
        return True

    def delete_hook(self, hook_id: int) -> bool:
        """Delete a hook config and associated log entries. Returns True if deleted."""
        entry = self.session.get(HookConfig, hook_id)
        if not entry:
            return False

        # Delete associated hook_log entries
        self.session.execute(
            delete(HookLog).where(HookLog.hook_id == hook_id)
        )
        self.session.delete(entry)
        self._commit()
        return True

    def record_hook_triggered(self, hook_id: int, success: bool):
        """Update hook trigger statistics after execution.

        Increments trigger_count, sets last_triggered_at and last_status.
        """
        entry = self.session.get(HookConfig, hook_id)
        if not entry:
            return

        now = self._now()
        status = "success" if success else "failed"
        entry.trigger_count = (entry.trigger_count or 0) + 1
        entry.last_triggered_at = now
        entry.last_status = status
        entry.updated_at = now
        self._commit()

    # ---- Webhook configs CRUD ----------------------------------------------------

    def create_webhook(self, name: str, event_name: str, url: str,
                       secret: str = "", retry_count: int = 3,
                       timeout_seconds: int = 10, enabled: bool = True) -> dict:
        """Create a new webhook configuration.

        Returns:
            Dict representing the created webhook config.
        """
        now = self._now()
        webhook = WebhookConfig(
            name=name,
            event_name=event_name,
            url=url,
            secret=secret,
            enabled=1 if enabled else 0,
            retry_count=retry_count,
            timeout_seconds=timeout_seconds,
            last_triggered_at="",
            last_status_code=0,
            last_error="",
            consecutive_failures=0,
            trigger_count=0,
            created_at=now,
            updated_at=now,
        )
        self.session.add(webhook)
        self._commit()

        return {
            "id": webhook.id,
            "name": name,
            "event_name": event_name,
            "url": url,
            "secret": secret,
            "enabled": 1 if enabled else 0,
            "retry_count": retry_count,
            "timeout_seconds": timeout_seconds,
            "last_triggered_at": "",
            "last_status_code": 0,
            "last_error": "",
            "consecutive_failures": 0,
            "trigger_count": 0,
            "created_at": now,
            "updated_at": now,
        }

    def get_webhooks(self, event_name: str = None,
                     enabled_only: bool = False) -> list:
        """Get all webhook configs, optionally filtered.

        Returns:
            List of webhook config dicts.
        """
        stmt = select(WebhookConfig).order_by(WebhookConfig.id)
        if event_name:
            stmt = stmt.where(WebhookConfig.event_name == event_name)
        if enabled_only:
            stmt = stmt.where(WebhookConfig.enabled == 1)
        entries = self.session.execute(stmt).scalars().all()
        return [self._row_to_webhook(e) for e in entries]

    def get_webhook(self, webhook_id: int) -> Optional[dict]:
        """Get a single webhook config by ID."""
        entry = self.session.get(WebhookConfig, webhook_id)
        if not entry:
            return None
        return self._row_to_webhook(entry)

    def update_webhook(self, webhook_id: int, **kwargs) -> bool:
        """Update a webhook config with arbitrary column values. Returns True if found."""
        entry = self.session.get(WebhookConfig, webhook_id)
        if not entry:
            return False

        for key, value in kwargs.items():
            if hasattr(entry, key):
                setattr(entry, key, value)
        entry.updated_at = self._now()
        self._commit()
        return True

    def delete_webhook(self, webhook_id: int) -> bool:
        """Delete a webhook config and associated log entries. Returns True if deleted."""
        entry = self.session.get(WebhookConfig, webhook_id)
        if not entry:
            return False

        # Delete associated hook_log entries
        self.session.execute(
            delete(HookLog).where(HookLog.webhook_id == webhook_id)
        )
        self.session.delete(entry)
        self._commit()
        return True

    def record_webhook_triggered(self, webhook_id: int, success: bool,
                                  status_code: int = 0, error: str = ""):
        """Update webhook trigger statistics after execution.

        Increments trigger_count, tracks consecutive_failures, sets
        last_triggered_at, last_status_code, and last_error.
        """
        entry = self.session.get(WebhookConfig, webhook_id)
        if not entry:
            return

        now = self._now()
        entry.trigger_count = (entry.trigger_count or 0) + 1
        entry.last_triggered_at = now
        entry.last_status_code = status_code

        if success:
            entry.last_error = ""
            entry.consecutive_failures = 0
        else:
            entry.last_error = error
            entry.consecutive_failures = (entry.consecutive_failures or 0) + 1

        entry.updated_at = now
        self._commit()

    # ---- Hook log ----------------------------------------------------------------

    def create_hook_log(self, hook_id: int = None, webhook_id: int = None,
                        event_name: str = "", hook_type: str = "",
                        success: bool = False, exit_code: int = None,
                        status_code: int = None, stdout: str = "",
                        stderr: str = "", error: str = "",
                        duration_ms: float = 0) -> dict:
        """Record a hook or webhook execution in the log.

        Returns:
            Dict representing the log entry.
        """
        now = self._now()
        log_entry = HookLog(
            hook_id=hook_id,
            webhook_id=webhook_id,
            event_name=event_name,
            hook_type=hook_type,
            success=int(success),
            exit_code=exit_code,
            status_code=status_code,
            stdout=stdout,
            stderr=stderr,
            error=error,
            duration_ms=duration_ms,
            triggered_at=now,
        )
        self.session.add(log_entry)
        self._commit()

        return {
            "id": log_entry.id,
            "hook_id": hook_id,
            "webhook_id": webhook_id,
            "event_name": event_name,
            "hook_type": hook_type,
            "success": success,
            "exit_code": exit_code,
            "status_code": status_code,
            "stdout": stdout,
            "stderr": stderr,
            "error": error,
            "duration_ms": duration_ms,
            "triggered_at": now,
        }

    def get_hook_logs(self, limit: int = 50, offset: int = 0,
                      hook_id: int = None, webhook_id: int = None) -> list:
        """Get hook execution logs, optionally filtered.

        Returns:
            List of log entry dicts, ordered by triggered_at descending.
        """
        stmt = select(HookLog).order_by(HookLog.triggered_at.desc()).limit(limit)
        if offset:
            stmt = stmt.offset(offset)
        if hook_id is not None:
            stmt = stmt.where(HookLog.hook_id == hook_id)
        elif webhook_id is not None:
            stmt = stmt.where(HookLog.webhook_id == webhook_id)
        entries = self.session.execute(stmt).scalars().all()
        return [self._row_to_log(e) for e in entries]

    def get_hook_log_count(self, hook_id: int = None,
                           webhook_id: int = None) -> int:
        """Get total count of hook logs, optionally filtered."""
        stmt = select(func.count()).select_from(HookLog)
        if hook_id is not None:
            stmt = stmt.where(HookLog.hook_id == hook_id)
        elif webhook_id is not None:
            stmt = stmt.where(HookLog.webhook_id == webhook_id)
        return self.session.execute(stmt).scalar() or 0

    def clear_hook_logs(self) -> int:
        """Delete all hook execution logs. Returns count deleted."""
        result = self.session.execute(delete(HookLog))
        self._commit()
        return result.rowcount

    def clear_old_hook_logs(self, days: int) -> int:
        """Delete hook logs older than N days. Returns count deleted."""
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        result = self.session.execute(
            delete(HookLog).where(HookLog.triggered_at < cutoff)
        )
        self._commit()
        return result.rowcount

    # ---- Helpers -----------------------------------------------------------------

    def _row_to_hook(self, entry: HookConfig) -> dict:
        """Convert a HookConfig model to a dict."""
        return self._to_dict(entry)

    def _row_to_webhook(self, entry: WebhookConfig) -> dict:
        """Convert a WebhookConfig model to a dict."""
        return self._to_dict(entry)

    def _row_to_log(self, entry: HookLog) -> dict:
        """Convert a HookLog model to a dict."""
        d = self._to_dict(entry)
        d["success"] = bool(d.get("success", 0))
        return d
