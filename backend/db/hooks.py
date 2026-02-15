"""Hook and webhook database operations.

CRUD operations for hook_configs, webhook_configs, and hook_log tables.
Follows the same _db_lock pattern used throughout the db package.
"""

import logging
from datetime import datetime
from typing import Optional

from db import get_db, _db_lock

logger = logging.getLogger(__name__)


def _row_to_dict(row) -> Optional[dict]:
    """Convert a sqlite3.Row to a dict, or return None."""
    if row is None:
        return None
    return dict(row)


# ---- Hook configs CRUD --------------------------------------------------------

def create_hook_config(name: str, event_name: str, script_path: str,
                       timeout_seconds: int = 30) -> dict:
    """Create a new hook configuration.

    Args:
        name: Human-readable hook name
        event_name: Event to trigger on (must be in EVENT_CATALOG)
        script_path: Path to the script to execute
        timeout_seconds: Max execution time before kill

    Returns:
        Dict representing the created hook config
    """
    now = datetime.utcnow().isoformat()
    db = get_db()
    with _db_lock:
        cursor = db.execute(
            """INSERT INTO hook_configs
               (name, event_name, script_path, timeout_seconds, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name, event_name, script_path, timeout_seconds, now, now),
        )
        db.commit()
        hook_id = cursor.lastrowid

    return {
        "id": hook_id,
        "name": name,
        "event_name": event_name,
        "hook_type": "script",
        "enabled": 1,
        "script_path": script_path,
        "timeout_seconds": timeout_seconds,
        "last_triggered_at": "",
        "last_status": "",
        "trigger_count": 0,
        "created_at": now,
        "updated_at": now,
    }


def get_hook_configs(event_name: str = None) -> list[dict]:
    """Get all hook configs, optionally filtered by event name.

    Args:
        event_name: Optional event name filter

    Returns:
        List of hook config dicts
    """
    db = get_db()
    with _db_lock:
        if event_name:
            rows = db.execute(
                "SELECT * FROM hook_configs WHERE event_name=? ORDER BY id",
                (event_name,),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM hook_configs ORDER BY id"
            ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_hook_config(hook_id: int) -> Optional[dict]:
    """Get a single hook config by ID.

    Args:
        hook_id: Hook config ID

    Returns:
        Hook config dict or None
    """
    db = get_db()
    with _db_lock:
        row = db.execute(
            "SELECT * FROM hook_configs WHERE id=?", (hook_id,)
        ).fetchone()
    return _row_to_dict(row)


def update_hook_config(hook_id: int, **kwargs) -> None:
    """Update a hook config with arbitrary column values.

    Args:
        hook_id: Hook config to update
        **kwargs: Column name-value pairs
    """
    if not kwargs:
        return

    kwargs["updated_at"] = datetime.utcnow().isoformat()
    columns = []
    values = []
    for key, value in kwargs.items():
        columns.append(f"{key}=?")
        values.append(value)
    values.append(hook_id)

    db = get_db()
    with _db_lock:
        db.execute(
            f"UPDATE hook_configs SET {', '.join(columns)} WHERE id=?",
            values,
        )
        db.commit()


def delete_hook_config(hook_id: int) -> None:
    """Delete a hook config by ID.

    Args:
        hook_id: Hook config to delete
    """
    db = get_db()
    with _db_lock:
        db.execute("DELETE FROM hook_configs WHERE id=?", (hook_id,))
        db.commit()


# ---- Webhook configs CRUD -----------------------------------------------------

def create_webhook_config(name: str, event_name: str, url: str,
                          secret: str = "", retry_count: int = 3,
                          timeout_seconds: int = 10) -> dict:
    """Create a new webhook configuration.

    Args:
        name: Human-readable webhook name
        event_name: Event to trigger on
        url: Webhook endpoint URL
        secret: Optional HMAC secret for payload signing
        retry_count: Number of retry attempts on failure
        timeout_seconds: HTTP request timeout

    Returns:
        Dict representing the created webhook config
    """
    now = datetime.utcnow().isoformat()
    db = get_db()
    with _db_lock:
        cursor = db.execute(
            """INSERT INTO webhook_configs
               (name, event_name, url, secret, retry_count, timeout_seconds,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, event_name, url, secret, retry_count, timeout_seconds, now, now),
        )
        db.commit()
        webhook_id = cursor.lastrowid

    return {
        "id": webhook_id,
        "name": name,
        "event_name": event_name,
        "url": url,
        "secret": secret,
        "enabled": 1,
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


def get_webhook_configs(event_name: str = None) -> list[dict]:
    """Get all webhook configs, optionally filtered by event name.

    Args:
        event_name: Optional event name filter

    Returns:
        List of webhook config dicts
    """
    db = get_db()
    with _db_lock:
        if event_name:
            rows = db.execute(
                "SELECT * FROM webhook_configs WHERE event_name=? ORDER BY id",
                (event_name,),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM webhook_configs ORDER BY id"
            ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_webhook_config(webhook_id: int) -> Optional[dict]:
    """Get a single webhook config by ID.

    Args:
        webhook_id: Webhook config ID

    Returns:
        Webhook config dict or None
    """
    db = get_db()
    with _db_lock:
        row = db.execute(
            "SELECT * FROM webhook_configs WHERE id=?", (webhook_id,)
        ).fetchone()
    return _row_to_dict(row)


def update_webhook_config(webhook_id: int, **kwargs) -> None:
    """Update a webhook config with arbitrary column values.

    Args:
        webhook_id: Webhook config to update
        **kwargs: Column name-value pairs
    """
    if not kwargs:
        return

    kwargs["updated_at"] = datetime.utcnow().isoformat()
    columns = []
    values = []
    for key, value in kwargs.items():
        columns.append(f"{key}=?")
        values.append(value)
    values.append(webhook_id)

    db = get_db()
    with _db_lock:
        db.execute(
            f"UPDATE webhook_configs SET {', '.join(columns)} WHERE id=?",
            values,
        )
        db.commit()


def delete_webhook_config(webhook_id: int) -> None:
    """Delete a webhook config by ID.

    Args:
        webhook_id: Webhook config to delete
    """
    db = get_db()
    with _db_lock:
        db.execute("DELETE FROM webhook_configs WHERE id=?", (webhook_id,))
        db.commit()


# ---- Hook log ------------------------------------------------------------------

def log_hook_execution(hook_id: int = None, webhook_id: int = None,
                       event_name: str = "", hook_type: str = "",
                       success: bool = False, exit_code: int = None,
                       status_code: int = None, stdout: str = "",
                       stderr: str = "", error: str = "",
                       duration_ms: float = 0) -> dict:
    """Record a hook or webhook execution in the log.

    Args:
        hook_id: Hook config ID (for script hooks)
        webhook_id: Webhook config ID (for webhooks)
        event_name: The event that triggered execution
        hook_type: 'script' or 'webhook'
        success: Whether execution succeeded
        exit_code: Process exit code (script hooks)
        status_code: HTTP status code (webhooks)
        stdout: Captured stdout (script hooks)
        stderr: Captured stderr (script hooks)
        error: Error message if failed
        duration_ms: Execution duration in milliseconds

    Returns:
        Dict representing the log entry
    """
    now = datetime.utcnow().isoformat()
    db = get_db()
    with _db_lock:
        cursor = db.execute(
            """INSERT INTO hook_log
               (hook_id, webhook_id, event_name, hook_type, success,
                exit_code, status_code, stdout, stderr, error,
                duration_ms, triggered_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (hook_id, webhook_id, event_name, hook_type, int(success),
             exit_code, status_code, stdout, stderr, error,
             duration_ms, now),
        )
        db.commit()
        log_id = cursor.lastrowid

    return {
        "id": log_id,
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


def get_hook_logs(hook_id: int = None, webhook_id: int = None,
                  limit: int = 50) -> list[dict]:
    """Get hook execution logs, optionally filtered.

    Args:
        hook_id: Filter by hook config ID
        webhook_id: Filter by webhook config ID
        limit: Maximum number of results

    Returns:
        List of log entry dicts, ordered by triggered_at descending
    """
    db = get_db()
    with _db_lock:
        if hook_id is not None:
            rows = db.execute(
                "SELECT * FROM hook_log WHERE hook_id=? ORDER BY triggered_at DESC LIMIT ?",
                (hook_id, limit),
            ).fetchall()
        elif webhook_id is not None:
            rows = db.execute(
                "SELECT * FROM hook_log WHERE webhook_id=? ORDER BY triggered_at DESC LIMIT ?",
                (webhook_id, limit),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM hook_log ORDER BY triggered_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [_row_to_dict(r) for r in rows]


# ---- Trigger stats helpers -----------------------------------------------------

def update_hook_trigger_stats(hook_id: int, success: bool) -> None:
    """Update hook trigger statistics after execution.

    Increments trigger_count, sets last_triggered_at and last_status.

    Args:
        hook_id: Hook config to update
        success: Whether execution succeeded
    """
    now = datetime.utcnow().isoformat()
    status = "success" if success else "failed"
    db = get_db()
    with _db_lock:
        db.execute(
            """UPDATE hook_configs
               SET trigger_count = trigger_count + 1,
                   last_triggered_at = ?,
                   last_status = ?,
                   updated_at = ?
               WHERE id = ?""",
            (now, status, now, hook_id),
        )
        db.commit()


def update_webhook_trigger_stats(webhook_id: int, success: bool,
                                 status_code: int = 0,
                                 error: str = "") -> None:
    """Update webhook trigger statistics after execution.

    Increments trigger_count, tracks consecutive_failures, sets
    last_triggered_at, last_status_code, and last_error.

    Args:
        webhook_id: Webhook config to update
        success: Whether the HTTP request succeeded
        status_code: HTTP response status code
        error: Error message if failed
    """
    now = datetime.utcnow().isoformat()
    db = get_db()
    with _db_lock:
        if success:
            db.execute(
                """UPDATE webhook_configs
                   SET trigger_count = trigger_count + 1,
                       last_triggered_at = ?,
                       last_status_code = ?,
                       last_error = '',
                       consecutive_failures = 0,
                       updated_at = ?
                   WHERE id = ?""",
                (now, status_code, now, webhook_id),
            )
        else:
            db.execute(
                """UPDATE webhook_configs
                   SET trigger_count = trigger_count + 1,
                       last_triggered_at = ?,
                       last_status_code = ?,
                       last_error = ?,
                       consecutive_failures = consecutive_failures + 1,
                       updated_at = ?
                   WHERE id = ?""",
                (now, status_code, error, now, webhook_id),
            )
        db.commit()
