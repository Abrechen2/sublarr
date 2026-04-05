"""Repository for ActivityLog — writes and paginated reads."""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import desc

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
                created_at=datetime.now(timezone.utc),
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
        rows = (
            query.order_by(desc(ActivityLog.created_at))
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
                    "details_json": r.details_json,
                    "created_at": r.created_at.isoformat(),
                }
                for r in rows
            ],
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": max(1, -(-total // per_page)),
        }
