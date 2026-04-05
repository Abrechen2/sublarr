"""Unified activity log DB operations — delegates to ActivityLogRepository."""

import logging

from db.repositories.activity import ActivityLogRepository

logger = logging.getLogger(__name__)

_repo: ActivityLogRepository | None = None


def _get_repo() -> ActivityLogRepository:
    global _repo
    if _repo is None:
        _repo = ActivityLogRepository()
    return _repo


def log_activity(
    event_type: str,
    *,
    file_path: str | None = None,
    status: str = "success",
    details: dict | None = None,
) -> None:
    """Log an activity event. Safe to call anywhere — never raises."""
    _get_repo().log_event(event_type, file_path=file_path, status=status, details=details)


def get_activity(
    page: int = 1,
    per_page: int = 50,
    event_type: str | None = None,
) -> dict:
    """Return paginated activity log entries."""
    return _get_repo().get_activity(page=page, per_page=per_page, event_type=event_type)
