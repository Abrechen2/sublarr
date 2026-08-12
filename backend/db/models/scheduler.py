"""JobRun ORM model — one row per scheduled job execution."""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from extensions import db


class JobRun(db.Model):
    """One row per scheduled job execution.

    Populated by SublarrScheduler event listeners in services/scheduler.py.
    Retention controlled by ``scheduler_history_retention_days`` setting
    and swept by the ``scheduler_history_cleanup`` cron job.
    """

    __tablename__ = "scheduler_job_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 32, not 16: "timeout_abandoned" is 17 characters and silently failed to
    # write on PostgreSQL while SQLite accepted it, so the status that marks a
    # runaway job was the one status that never reached history.
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    triggered_by: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="schedule", default="schedule"
    )
    error_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_scheduler_job_runs_job_id_started_at", "job_id", "started_at"),
        Index("ix_scheduler_job_runs_started_at", "started_at"),
        Index("ix_scheduler_job_runs_status", "status"),
    )
