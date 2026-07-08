"""ActivityLog ORM model — unified event log for subtitle operations."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from extensions import db

EVENT_DOWNLOAD = "download"
EVENT_EXTRACT = "extract"
EVENT_DELETE = "delete"
EVENT_SCAN = "scan"
EVENT_SEARCH = "search"
EVENT_TRANSLATE = "translate"


class ActivityLog(db.Model):
    """Unified log of subtitle-related operations."""

    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="success")
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Previously carried idx_activity_log_event_type and idx_activity_log_created_at.
    # Both were dropped in migration h1i2j3k4l5m6 after showing 0 index scans over
    # ~2 weeks in prod — activity_log has no reader queries that would use them.
