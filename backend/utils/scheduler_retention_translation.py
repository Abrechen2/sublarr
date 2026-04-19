"""translation_events retention cleanup.

Registered as the ``translation_events_cleanup`` JobSpec. Reads
``settings.translation_events_retention_days`` at tick time so runtime
settings changes take effect on next fire without a restart.
"""

import logging
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa

from config import get_settings
from db.models.translation import TranslationEvent
from extensions import db

logger = logging.getLogger(__name__)


def delete_old_translation_events(retention_days: int | None = None) -> int:
    """Delete translation_events rows older than retention_days.

    Returns the number of rows deleted.
    """
    if retention_days is None:
        retention_days = getattr(get_settings(), "translation_events_retention_days", 90)
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    with db.session.begin():
        result = db.session.execute(
            sa.delete(TranslationEvent).where(TranslationEvent.started_at < cutoff)
        )
        deleted = result.rowcount or 0
    logger.info(
        "translation_events_cleanup: deleted %d rows older than %s",
        deleted,
        cutoff,
    )
    return deleted
