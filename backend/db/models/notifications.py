"""Notification ORM models: templates, history, and quiet hours.

Supports Jinja2 template rendering, notification history tracking,
and quiet hours suppression for the notification management system.
"""

from sqlalchemy import Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from extensions import db


class NotificationTemplate(db.Model):
    """User-defined notification template with Jinja2 syntax."""

    __tablename__ = "notification_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    title_template: Mapped[str] = mapped_column(Text, nullable=False, default="")
    body_template: Mapped[str] = mapped_column(Text, nullable=False, default="")
    event_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    service_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class NotificationHistory(db.Model):
    """Record of sent notifications for audit and re-send."""

    __tablename__ = "notification_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    template_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    service_urls: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="sent")
    error: Mapped[str | None] = mapped_column(Text, default="")
    sent_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("idx_notification_history_event_type", "event_type"),
        Index("idx_notification_history_sent_at", "sent_at"),
    )


class QuietHoursConfig(db.Model):
    """Quiet hours window configuration for notification suppression."""

    __tablename__ = "quiet_hours_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    start_time: Mapped[str] = mapped_column(String(5), nullable=False)
    end_time: Mapped[str] = mapped_column(String(5), nullable=False)
    days_of_week: Mapped[str] = mapped_column(Text, default="[0,1,2,3,4,5,6]")
    exception_events: Mapped[str] = mapped_column(Text, default='["error"]')
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


__all__ = [
    "NotificationTemplate",
    "NotificationHistory",
    "QuietHoursConfig",
]
