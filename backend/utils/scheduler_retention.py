"""Scheduler history retention cleanup.

Registered as the ``scheduler_history_cleanup`` JobSpec. Reads
``settings.scheduler_history_retention_days`` at tick time so
runtime settings changes take effect on next fire without restart.
"""

import logging
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa

from config import get_settings
from db.models.scheduler import JobRun
from extensions import db

logger = logging.getLogger(__name__)


def delete_old_job_runs(retention_days: int | None = None) -> int:
    """Delete scheduler_job_runs rows older than retention_days.

    Returns the number of rows deleted.
    """
    if retention_days is None:
        retention_days = getattr(get_settings(), "scheduler_history_retention_days", 30)
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    with db.session.begin():
        result = db.session.execute(sa.delete(JobRun).where(JobRun.started_at < cutoff))
        deleted = result.rowcount or 0
    logger.info(
        "scheduler_history_cleanup: deleted %d rows older than %s",
        deleted,
        cutoff,
    )
    return deleted
