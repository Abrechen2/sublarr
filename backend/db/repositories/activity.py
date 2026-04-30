"""Repository for ActivityLog — writes and paginated reads."""

import json
import logging
from datetime import UTC, datetime

from db.models.activity import ActivityLog
from extensions import db

logger = logging.getLogger(__name__)


class ActivityLogRepository:
    def log_event(
        self,
        event_type: str,
        *,
        file_path: str | None = None,
        status: str = "success",
        details: dict | None = None,
    ) -> None:
        """Insert a new activity_log row. Rolls back on error."""
        try:
            row = ActivityLog(
                event_type=event_type,
                file_path=file_path,
                status=status,
                details_json=json.dumps(details) if details else None,
                created_at=datetime.now(UTC),
            )
            db.session.add(row)
            db.session.commit()
        except Exception:
            logger.exception("Failed to log activity event %s", event_type)
            db.session.rollback()

    def get_activity(
        self,
        page: int = 1,
        per_page: int = 50,
        event_type: str | None = None,
    ) -> dict:
        """Return paginated activity log entries, newest first."""
        query = db.session.query(ActivityLog)
        if event_type:
            query = query.filter(ActivityLog.event_type == event_type)
        total = query.count()
        # Order by the PK rather than created_at: log_event() is the only
        # writer and stamps ``created_at=datetime.now(UTC)`` immediately
        # before the INSERT, so id-desc and created_at-desc agree to within
        # microseconds. The PK is automatically indexed; the dedicated
        # ``idx_activity_log_created_at`` was dropped in migration
        # h1i2j3k4l5m6 (2026-04-14, "0 scans" — measured BEFORE the
        # activity page was restored on 2026-04-05). On a busy install
        # the un-indexed ORDER BY became a full sort on every page load.
        rows = (
            query.order_by(ActivityLog.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        return {
            "data": [
                {
                    "id": r.id,
                    "event_type": r.event_type,
                    "file_path": r.file_path,
                    "status": r.status,
                    "details": json.loads(r.details_json) if r.details_json else None,
                    "created_at": r.created_at.isoformat(),
                }
                for r in rows
            ],
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": max(1, -(-total // per_page)),
        }
