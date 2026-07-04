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


def upsert_rollup(date_str: str, *, skip_if_empty: bool = False) -> bool:
    """Compute and idempotently upsert the rollup row for ``date_str``.

    Returns True if a row was written. With ``skip_if_empty`` a day with no
    activity (0 downloads / translations / syncs) is skipped — used by the
    backfill so a fresh install doesn't create long runs of empty rows.
    """
    from db.models.statistics import StatsDailyRollup
    from extensions import db

    data = compute_rollup_for_date(date_str)
    if skip_if_empty and not (data["downloads"] or data["translations"] or data["syncs"]):
        return False

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
    return True


# Days of history the rollup keeps warm — covers the FE "30d"/"all" ranges plus
# self-heals downtime gaps. First tick on an existing library backfills this far.
_BACKFILL_DAYS = 90


def _existing_dates(cutoff: str) -> set[str]:
    from db.models.statistics import StatsDailyRollup
    from extensions import db

    rows = db.session.execute(
        select(StatsDailyRollup.date).where(StatsDailyRollup.date >= cutoff)
    ).all()
    return {r[0] for r in rows}


def _safe_upsert(date_str: str, *, skip_if_empty: bool = False) -> None:
    try:
        upsert_rollup(date_str, skip_if_empty=skip_if_empty)
    except Exception:
        logger.error("stats_rollup: failed to roll up %s", date_str, exc_info=True)
        try:
            from extensions import db

            db.session.rollback()
        except Exception:
            pass


def stats_rollup_tick() -> None:
    """Refresh recent rollups and self-heal any missing historical day.

    Always rewrites today + yesterday (late writes). Then, for the last
    ``_BACKFILL_DAYS`` days, computes any day that has activity but no row yet —
    which both **backfills history on first run** (the trend chart is otherwise
    blank for weeks) and **fills gaps** left by multi-day scheduler downtime
    (H1/H2). Days that already have a row are skipped, so steady-state runs are
    cheap. Module-level + picklable for APScheduler; runs in the app context.
    """
    today = datetime.now(UTC).date()
    _safe_upsert(today.isoformat())
    _safe_upsert((today - timedelta(days=1)).isoformat())

    cutoff = (today - timedelta(days=_BACKFILL_DAYS)).isoformat()
    try:
        existing = _existing_dates(cutoff)
    except Exception:
        logger.error("stats_rollup: could not read existing rollup dates", exc_info=True)
        return
    for offset in range(2, _BACKFILL_DAYS + 1):
        day = (today - timedelta(days=offset)).isoformat()
        if day not in existing:
            _safe_upsert(day, skip_if_empty=True)
