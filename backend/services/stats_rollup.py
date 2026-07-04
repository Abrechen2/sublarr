"""Daily statistics rollup service (V1.6 #9).

Computes per-date counts from subtitle_downloads / translation_events /
sync_job_runs and upserts them into ``stats_daily_rollup`` so trend charts read
pre-aggregated rows instead of scanning the raw tables. Idempotent — safe to
re-run for any date.

``stats_rollup_tick`` is a module-level, picklable callable registered as the
``stats_rollup`` scheduler JobSpec (SQLAlchemyJobStore pickles a textual ref).
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select

logger = logging.getLogger(__name__)


def _day_bounds(date_str: str) -> tuple[datetime, datetime]:
    """Return the [start, end) UTC datetime bounds for an ISO date string."""
    d = date.fromisoformat(date_str)
    start = datetime(d.year, d.month, d.day, tzinfo=UTC)
    return start, start + timedelta(days=1)


def compute_rollup_for_date(date_str: str) -> dict:
    """Compute the aggregated counts for one calendar date (no DB writes)."""
    from db.models.core import SyncJobRun
    from db.models.providers import SubtitleDownload
    from db.models.translation import TranslationEvent
    from extensions import db

    start, end = _day_bounds(date_str)
    session = db.session

    downloads = (
        session.execute(
            select(SubtitleDownload).where(
                SubtitleDownload.downloaded_at >= start,
                SubtitleDownload.downloaded_at < end,
            )
        )
        .scalars()
        .all()
    )

    by_source: Counter[str] = Counter()
    by_provider: Counter[str] = Counter()
    by_language: Counter[str] = Counter()
    for d in downloads:
        by_source[d.source or "unknown"] += 1
        by_provider[d.provider_name or "unknown"] += 1
        by_language[d.language or "unknown"] += 1

    translations = session.execute(
        select(
            func.count(TranslationEvent.id),
            func.coalesce(func.sum(TranslationEvent.chars_out), 0),
            func.coalesce(func.sum(TranslationEvent.cost_estimate_micro_usd), 0),
        ).where(
            TranslationEvent.started_at >= start,
            TranslationEvent.started_at < end,
            TranslationEvent.status == "ok",
        )
    ).one()
    translation_count = int(translations[0] or 0)
    translation_chars = int(translations[1] or 0)
    translation_cost = int(translations[2] or 0)

    syncs = session.execute(
        select(func.count(SyncJobRun.id)).where(
            SyncJobRun.created_at >= start,
            SyncJobRun.created_at < end,
            SyncJobRun.status == "ok",
        )
    ).scalar_one()

    return {
        "date": date_str,
        "downloads": len(downloads),
        "translations": translation_count,
        "syncs": int(syncs or 0),
        "translation_chars": translation_chars,
        "translation_cost_micro_usd": translation_cost,
        "by_source": dict(by_source),
        "by_provider": dict(by_provider),
        "by_language": dict(by_language),
    }


def upsert_rollup(date_str: str) -> None:
    """Compute and idempotently upsert the rollup row for ``date_str``."""
    from db.models.statistics import StatsDailyRollup
    from extensions import db

    data = compute_rollup_for_date(date_str)
    session = db.session
    row = session.get(StatsDailyRollup, date_str)
    if row is None:
        row = StatsDailyRollup(date=date_str)
        session.add(row)

    row.downloads = data["downloads"]
    row.translations = data["translations"]
    row.syncs = data["syncs"]
    row.translation_chars = data["translation_chars"]
    row.translation_cost_micro_usd = data["translation_cost_micro_usd"]
    row.by_source_json = json.dumps(data["by_source"])
    row.by_provider_json = json.dumps(data["by_provider"])
    row.by_language_json = json.dumps(data["by_language"])
    row.updated_at = datetime.now(UTC)
    session.commit()


def stats_rollup_tick() -> None:
    """Roll up the last two days (today + yesterday, to catch late writes).

    Module-level + picklable so APScheduler's SQLAlchemyJobStore can persist a
    textual reference. Runs inside the scheduler's app context.
    """
    today = datetime.now(UTC).date()
    for offset in (0, 1):
        day = (today - timedelta(days=offset)).isoformat()
        try:
            upsert_rollup(day)
        except Exception:
            logger.error("stats_rollup: failed to roll up %s", day, exc_info=True)
            try:
                from extensions import db

                db.session.rollback()
            except Exception:
                pass
