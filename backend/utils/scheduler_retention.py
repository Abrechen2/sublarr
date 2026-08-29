"""Internal history retention cleanup.

``internal_history_cleanup`` is registered as the ``scheduler_history_cleanup``
JobSpec and covers both internal history tables: ``scheduler_job_runs`` and
the finished rows of ``subtitle_automation_queue``. Reads
``settings.scheduler_history_retention_days`` at tick time so runtime
settings changes take effect on next fire without restart.
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


def internal_history_cleanup() -> None:
    """Tick body for the ``scheduler_history_cleanup`` job.

    Chains the two internal history purges. Each half is guarded on its
    own: losing the queue purge to an error must not cost the job-run
    purge, and vice versa.
    """
    try:
        delete_old_job_runs()
    except Exception:
        logger.exception("scheduler_history_cleanup: job-run purge failed")
    try:
        from db.repositories.subtitle_automation_queue import (
            SubtitleAutomationQueueRepository,
        )

        removed = SubtitleAutomationQueueRepository().purge_finished()
        if removed:
            logger.info(
                "scheduler_history_cleanup: purged %d finished automation queue row(s)",
                removed,
            )
    except Exception:
        logger.exception("scheduler_history_cleanup: automation queue purge failed")
