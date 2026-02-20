"""Hook/Webhook ORM models: hook configs, webhook configs, hook logs.

All column types and defaults match the existing SCHEMA DDL in db/__init__.py exactly.
"""

from typing import Optional

from sqlalchemy import Index, Integer, Float, Text, String
from sqlalchemy.orm import Mapped, mapped_column

from extensions import db


class HookConfig(db.Model):
    """Script hook configuration for event-driven automation."""

    __tablename__ = "hook_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    event_name: Mapped[str] = mapped_column(Text, nullable=False)
    hook_type: Mapped[Optional[str]] = mapped_column(String(20), default="script")
    enabled: Mapped[Optional[int]] = mapped_column(Integer, default=1)
    script_path: Mapped[Optional[str]] = mapped_column(Text, default="")
    timeout_seconds: Mapped[Optional[int]] = mapped_column(Integer, default=30)
    last_triggered_at: Mapped[Optional[str]] = mapped_column(Text, default="")
    last_status: Mapped[Optional[str]] = mapped_column(Text, default="")
    trigger_count: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (Index("idx_hook_configs_event", "event_name"),)


class WebhookConfig(db.Model):
    """HTTP webhook configuration for event-driven notifications."""

    __tablename__ = "webhook_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    event_name: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    secret: Mapped[Optional[str]] = mapped_column(Text, default="")
    enabled: Mapped[Optional[int]] = mapped_column(Integer, default=1)
    retry_count: Mapped[Optional[int]] = mapped_column(Integer, default=3)
    timeout_seconds: Mapped[Optional[int]] = mapped_column(Integer, default=10)
    last_triggered_at: Mapped[Optional[str]] = mapped_column(Text, default="")
    last_status_code: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text, default="")
    consecutive_failures: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    trigger_count: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (Index("idx_webhook_configs_event", "event_name"),)


class HookLog(db.Model):
    """Execution log for hooks and webhooks."""

    __tablename__ = "hook_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hook_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    webhook_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    event_name: Mapped[str] = mapped_column(Text, nullable=False)
    hook_type: Mapped[str] = mapped_column(Text, nullable=False)
    success: Mapped[int] = mapped_column(Integer, nullable=False)
    exit_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    stdout: Mapped[Optional[str]] = mapped_column(Text, default="")
    stderr: Mapped[Optional[str]] = mapped_column(Text, default="")
    error: Mapped[Optional[str]] = mapped_column(Text, default="")
    duration_ms: Mapped[Optional[float]] = mapped_column(Float, default=0)
    triggered_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("idx_hook_log_hook_id", "hook_id"),
        Index("idx_hook_log_webhook_id", "webhook_id"),
        Index("idx_hook_log_triggered_at", "triggered_at"),
    )


__all__ = [
    "HookConfig",
    "WebhookConfig",
    "HookLog",
]
