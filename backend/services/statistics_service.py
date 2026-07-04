"""Grouped statistics aggregation (V1.6 #9).

Powers the Statistics page's six sections (library / subtitles / translation /
providers / system / trends). Snapshot groups query the live tables (cached at
the route layer ~5 min); ``trends`` reads the pre-aggregated
``stats_daily_rollup`` written by ``services.stats_rollup``.
"""

from __future__ import annotations

import logging
import os
from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

logger = logging.getLogger(__name__)

_RANGE_DAYS: dict[str, int | None] = {"24h": 1, "7d": 7, "30d": 30, "all": None}


def _range_start(range_key: str) -> datetime | None:
    days = _RANGE_DAYS.get(range_key, 7)
    if days is None:
        return None
    return datetime.now(UTC) - timedelta(days=days)


# ── subtitles ────────────────────────────────────────────────────────────────


def get_subtitles_stats(range_key: str = "30d") -> dict:
    from db.models.providers import SubtitleDownload
    from extensions import db

    start = _range_start(range_key)
    stmt = select(SubtitleDownload)
    if start is not None:
        stmt = stmt.where(SubtitleDownload.downloaded_at >= start)
    rows = db.session.execute(stmt).scalars().all()

    by_source: Counter[str] = Counter()
    by_provider: Counter[str] = Counter()
    by_language: Counter[str] = Counter()
    scores: list[int] = []
    for r in rows:
        by_source[r.source or "unknown"] += 1
        by_provider[r.provider_name or "unknown"] += 1
        by_language[r.language or "unknown"] += 1
        if r.score:
            scores.append(r.score)

    return {
        "range": range_key,
        "total": len(rows),
        "by_source": dict(by_source),
        "by_provider": dict(by_provider),
        "by_language": dict(by_language),
        "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
    }


# ── translation ──────────────────────────────────────────────────────────────


def get_translation_stats(range_key: str = "30d") -> dict:
    from db.models.core import WantedItem
    from db.models.translation import TranslationEvent
    from extensions import db

    start = _range_start(range_key)
    stmt = select(TranslationEvent)
    if start is not None:
        stmt = stmt.where(TranslationEvent.started_at >= start)
    events = db.session.execute(stmt).scalars().all()

    total = len(events)
    ok = [e for e in events if e.status == "ok"]
    by_backend: Counter[str] = Counter(e.backend for e in ok)
    total_chars = sum(e.chars_out or 0 for e in ok)
    total_cost = sum(e.cost_estimate_micro_usd or 0 for e in ok)
    latencies = [e.latency_ms for e in ok if e.latency_ms]
    avg_latency = round(sum(latencies) / len(latencies)) if latencies else 0

    mt_awaiting = (
        db.session.execute(
            select(func.count(WantedItem.id)).where(WantedItem.status == "provisional")
        ).scalar_one()
        or 0
    )

    return {
        "range": range_key,
        "total": total,
        "by_backend": dict(by_backend),
        "total_chars": total_chars,
        "total_cost_micro_usd": total_cost,
        "avg_latency_ms": avg_latency,
        "pass_rate": round(len(ok) / total, 3) if total else 0,
        "mt_awaiting_original": int(mt_awaiting),
    }


# ── providers ────────────────────────────────────────────────────────────────


def get_providers_stats() -> dict:
    from db.models.providers import ProviderStats
    from extensions import db

    rows = db.session.execute(select(ProviderStats)).scalars().all()
    providers = []
    for r in rows:
        searches = r.total_searches or 0
        hits = r.successful_searches or 0
        providers.append(
            {
                "provider": r.provider_name,
                "searches": searches,
                "hit_rate": round(hits / searches, 3) if searches else 0,
                "downloads": r.successful_downloads or 0,
                "failures": r.failed_downloads or 0,
                "avg_score": round(r.avg_score or 0, 1),
                "avg_response_ms": round(r.avg_response_time_ms or 0),
                "auto_disabled": bool(r.auto_disabled),
            }
        )
    providers.sort(key=lambda p: p["downloads"], reverse=True)
    return {"providers": providers}


# ── system ───────────────────────────────────────────────────────────────────


def _db_size_bytes() -> int:
    try:
        from config import get_settings

        db_path = getattr(get_settings(), "db_path", "") or ""
        if db_path and os.path.exists(db_path):
            return os.path.getsize(db_path)
    except Exception:
        pass
    return 0


def get_system_stats() -> dict:
    result: dict = {
        "cpu_percent": 0.0,
        "memory_percent": 0.0,
        "disk_percent": 0.0,
        "uptime_seconds": 0,
        "db_size_bytes": _db_size_bytes(),
        "scheduler_runs": [],
    }
    try:
        import psutil

        result["cpu_percent"] = psutil.cpu_percent(interval=None)
        result["memory_percent"] = psutil.virtual_memory().percent
        result["disk_percent"] = psutil.disk_usage(os.path.abspath(os.sep)).percent
        result["uptime_seconds"] = int(
            datetime.now(UTC).timestamp() - psutil.Process().create_time()
        )
    except Exception as exc:
        logger.debug("system stats: psutil unavailable: %s", exc)

    try:
        from db.models.scheduler import JobRun
        from extensions import db

        recent = (
            db.session.execute(select(JobRun).order_by(JobRun.started_at.desc()).limit(10))
            .scalars()
            .all()
        )
        result["scheduler_runs"] = [
            {"job_id": r.job_id, "status": r.status, "duration_ms": r.duration_ms} for r in recent
        ]
    except Exception as exc:
        logger.debug("system stats: scheduler runs unavailable: %s", exc)

    return result


# ── library ──────────────────────────────────────────────────────────────────


def get_library_stats() -> dict:
    from db.models.core import WantedItem
    from db.models.providers import SubtitleDownload
    from extensions import db

    session = db.session
    subtitle_files = session.execute(select(func.count(SubtitleDownload.id))).scalar_one() or 0
    languages = [
        row[0]
        for row in session.execute(select(SubtitleDownload.language).distinct()).all()
        if row[0]
    ]
    wanted = session.execute(select(func.count(WantedItem.id))).scalar_one() or 0

    return {
        "subtitle_files": int(subtitle_files),
        "languages": sorted(languages),
        "wanted_items": int(wanted),
    }


# ── trends ───────────────────────────────────────────────────────────────────


def get_trends(range_key: str = "30d") -> dict:
    from db.models.statistics import StatsDailyRollup
    from extensions import db

    start = _range_start(range_key)
    rows = (
        db.session.execute(select(StatsDailyRollup).order_by(StatsDailyRollup.date)).scalars().all()
    )
    if start is not None:
        cutoff = start.date().isoformat()
        rows = [r for r in rows if r.date >= cutoff]

    return {
        "range": range_key,
        "dates": [r.date for r in rows],
        "downloads": [r.downloads for r in rows],
        "translations": [r.translations for r in rows],
        "syncs": [r.syncs for r in rows],
    }
