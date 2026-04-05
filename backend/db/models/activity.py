"""ActivityLog ORM model — unified event log for subtitle operations."""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from extensions import db

EVENT_DOWNLOAD = "download"
EVENT_EXTRACT = "extract"
EVENT_DELETE = "delete"
EVENT_SCAN = "scan"


class ActivityLog(db.Model):
    """Unified log of subtitle-related operations."""

    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="success")
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_activity_log_event_type", "event_type"),
        Index("idx_activity_log_created_at", "created_at"),
    )
