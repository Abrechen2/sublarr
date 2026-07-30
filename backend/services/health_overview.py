"""Library health overview — the data behind GET /api/v1/health/library.

Aggregates three "where does it hurt" views from data that already exists:

  * ``series``   — which series/movies have missing subtitles, and how many
                   of their wanted items are stuck in a failure state.
  * ``problems`` — the concrete wanted items that failed or were classified
                   with a ``failure_kind`` (no_result, provider_error,
                   unsourceable, ...), i.e. episodes the pipeline could not
                   satisfy or match.
  * ``providers``— per-provider health: circuit-breaker state merged with
                   the hit/failure counters from provider_stats.

Everything is read-only and bounded (top-N lists) so the endpoint stays
cheap enough for a dashboard poll.
"""

from __future__ import annotations

import logging

from sqlalchemy import case, func, select

logger = logging.getLogger(__name__)

# Bounded list sizes — a dashboard needs the worst offenders, not everything.
MAX_SERIES_ROWS = 50
MAX_PROBLEM_ROWS = 100

# Wanted statuses that mean "the user does not want this tracked".
_EXCLUDED_STATUSES = ("ignored",)


def _is_problem_clause(wanted_model):
    """Filter: item is stuck — failed outright or classified with a failure kind."""
    return (wanted_model.status == "failed") | (wanted_model.failure_kind.isnot(None))


def get_library_health() -> dict:
    from db.models.circuit_breaker import CircuitBreakerState
    from db.models.core import WantedItem
    from db.models.providers import ProviderStats
    from extensions import db

    session = db.session

    # ── series/movies with missing subtitles ────────────────────────────────
    problem_case = case((_is_problem_clause(WantedItem), 1), else_=0)
    series_rows = session.execute(
        select(
            WantedItem.title,
            WantedItem.item_type,
            func.count(WantedItem.id).label("missing"),
            func.sum(problem_case).label("problems"),
        )
        .where(WantedItem.status.notin_(_EXCLUDED_STATUSES))
        .group_by(WantedItem.title, WantedItem.item_type)
        .order_by(func.count(WantedItem.id).desc())
        .limit(MAX_SERIES_ROWS)
    ).all()
    series = [
        {
            "title": row[0] or "?",
            "item_type": row[1],
            "missing": int(row[2] or 0),
            "problems": int(row[3] or 0),
        }
        for row in series_rows
    ]

    # ── concrete problem items (failed / unmatched episodes) ────────────────
    problem_rows = (
        session.execute(
            select(WantedItem)
            .where(_is_problem_clause(WantedItem))
            .where(WantedItem.status.notin_(_EXCLUDED_STATUSES))
            .order_by(WantedItem.updated_at.desc())
            .limit(MAX_PROBLEM_ROWS)
        )
        .scalars()
        .all()
    )
    problems = [
        {
            "id": item.id,
            "title": item.title,
            "season_episode": item.season_episode or "",
            "item_type": item.item_type,
            "target_language": item.target_language or "",
            "status": item.status,
            "failure_kind": item.failure_kind,
            "error": item.error or "",
            "search_count": item.search_count or 0,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        }
        for item in problem_rows
    ]

    # ── provider health: circuit breaker ⋈ provider_stats ───────────────────
    breakers = {
        row.name: row for row in session.execute(select(CircuitBreakerState)).scalars().all()
    }
    stats_rows = session.execute(select(ProviderStats)).scalars().all()
    provider_names = sorted(set(breakers) | {r.provider_name for r in stats_rows})
    providers = []
    for name in provider_names:
        breaker = breakers.get(name)
        stats = next((r for r in stats_rows if r.provider_name == name), None)
        searches = (stats.total_searches or 0) if stats else 0
        hits = (stats.successful_searches or 0) if stats else 0
        breaker_state = (breaker.state if breaker else "closed") or "closed"
        auto_disabled = bool(stats.auto_disabled) if stats else False
        hit_rate = round(hits / searches, 3) if searches else None
        providers.append(
            {
                "provider": name,
                "breaker_state": breaker_state,
                "breaker_failures": int(breaker.failure_count or 0) if breaker else 0,
                "searches": int(searches),
                "hit_rate": hit_rate,
                "failed_downloads": int(stats.failed_downloads or 0) if stats else 0,
                "auto_disabled": auto_disabled,
                # A provider "hurts" when its breaker is not closed, it was
                # auto-disabled, or it answers searches but almost never hits.
                "degraded": (
                    breaker_state != "closed"
                    or auto_disabled
                    or (searches >= 10 and hit_rate is not None and hit_rate < 0.05)
                ),
            }
        )
    providers.sort(key=lambda p: (not p["degraded"], p["provider"]))

    # ── totals ──────────────────────────────────────────────────────────────
    wanted_total = (
        session.execute(
            select(func.count(WantedItem.id)).where(
                WantedItem.status.notin_(_EXCLUDED_STATUSES)
            )
        ).scalar_one()
        or 0
    )
    problems_total = (
        session.execute(
            select(func.count(WantedItem.id))
            .where(_is_problem_clause(WantedItem))
            .where(WantedItem.status.notin_(_EXCLUDED_STATUSES))
        ).scalar_one()
        or 0
    )
    unmatched_total = (
        session.execute(
            select(func.count(WantedItem.id)).where(WantedItem.failure_kind == "unsourceable")
        ).scalar_one()
        or 0
    )

    return {
        "totals": {
            "wanted": int(wanted_total),
            "problems": int(problems_total),
            "unmatched": int(unmatched_total),
            "series_affected": len(series),
            "providers_degraded": sum(1 for p in providers if p["degraded"]),
        },
        "series": series,
        "problems": problems,
        "providers": providers,
    }
