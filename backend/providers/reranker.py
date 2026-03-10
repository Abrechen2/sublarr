"""Provider result re-ranking engine.

Automatically adjusts per-provider score modifiers based on download history
statistics. Providers with high success rates and above-average subtitle
quality receive a bonus; consistently failing providers get penalized.

Usage:
    # Compute preview (read-only)
    preview = compute_reranking_preview()

    # Apply modifiers to DB
    apply_auto_reranking()

Throttling:
    apply_auto_reranking() is a no-op if called more than once per hour
    (unless force=True). The last-run timestamp is kept in memory.
"""

import logging
import time

logger = logging.getLogger(__name__)

# In-memory throttle: skip re-rank if last run < _RERANK_INTERVAL_SECS ago
_RERANK_INTERVAL_SECS = 3600  # 1 hour
_last_rerank_ts: float = 0.0


# ---------------------------------------------------------------------------
# Core formula
# ---------------------------------------------------------------------------

#: Success-rate baseline. Providers above this get a bonus, below get a penalty.
_BASELINE_SUCCESS_RATE = 0.65

#: Multiplier for success-rate component (scales ±1.0 deviation → ±this many pts).
_SUCCESS_RATE_SCALE = 40

#: Max absolute contribution from the score-delta component.
_SCORE_DELTA_CAP = 15

#: Consecutive-failure threshold that triggers a hard penalty.
_CONSECUTIVE_FAILURE_THRESHOLD = 5
_CONSECUTIVE_FAILURE_PENALTY = -30


def compute_modifier_from_stats(
    stats: dict,
    global_avg_score: float,
    min_downloads: int,
    max_modifier: int,
) -> int | None:
    """Compute a score modifier for one provider based on its stats.

    Args:
        stats: Dict from ProviderRepository.get_all_provider_stats()
               Keys: successful_downloads, failed_downloads, avg_score,
                     success_rate, consecutive_failures
        global_avg_score: Mean avg_score across all providers (for relative comparison).
        min_downloads:    Minimum successful downloads required before applying modifier.
        max_modifier:     Absolute cap on the returned modifier value.

    Returns:
        Integer modifier, or None if not enough data to make a decision.
    """
    n_success = stats.get("successful_downloads") or 0
    if n_success < min_downloads:
        return None  # not enough data

    consecutive_failures = stats.get("consecutive_failures") or 0
    if consecutive_failures >= _CONSECUTIVE_FAILURE_THRESHOLD:
        penalty = max(-max_modifier, _CONSECUTIVE_FAILURE_PENALTY)
        return penalty

    success_rate = stats.get("success_rate") or 0.0
    avg_score = stats.get("avg_score") or 0.0

    # Success-rate component: deviation from baseline, scaled
    sr_modifier = int((success_rate - _BASELINE_SUCCESS_RATE) * _SUCCESS_RATE_SCALE)

    # Score-quality component: how this provider's avg score compares to the field
    if global_avg_score > 0 and avg_score > 0:
        delta = avg_score - global_avg_score
        # +/- 100 score delta → approx +/- _SCORE_DELTA_CAP pts
        score_modifier = int(delta / (100 / _SCORE_DELTA_CAP))
        score_modifier = max(-_SCORE_DELTA_CAP, min(_SCORE_DELTA_CAP, score_modifier))
    else:
        score_modifier = 0

    total = sr_modifier + score_modifier
    return max(-max_modifier, min(max_modifier, total))


def _compute_global_avg_score(all_stats: list[dict]) -> float:
    """Weighted average of avg_score across providers with enough downloads."""
    scores = [
        (s["avg_score"] or 0.0, s["successful_downloads"] or 0)
        for s in all_stats
        if (s.get("avg_score") or 0) > 0 and (s.get("successful_downloads") or 0) > 0
    ]
    if not scores:
        return 0.0
    total_weight = sum(w for _, w in scores)
    if total_weight == 0:
        return 0.0
    return sum(v * w for v, w in scores) / total_weight


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_reranking_preview(
    min_downloads: int | None = None,
    max_modifier: int | None = None,
) -> dict:
    """Compute what modifiers would be applied without writing anything.

    Returns:
        {
            "global_avg_score": float,
            "providers": {
                "<name>": {
                    "current_modifier": int,
                    "proposed_modifier": int | None,
                    "stats": { successful_downloads, success_rate, avg_score, ... },
                    "reason": str,
                }
            }
        }
    """
    from config import get_settings
    from db import get_db
    from db.repositories.providers import ProviderRepository
    from db.repositories.scoring import ScoringRepository

    settings = get_settings()
    if min_downloads is None:
        min_downloads = settings.provider_reranking_min_downloads
    if max_modifier is None:
        max_modifier = settings.provider_reranking_max_modifier

    with get_db() as db:
        provider_repo = ProviderRepository(db)
        scoring_repo = ScoringRepository(db)

        all_stats = provider_repo.get_all_provider_stats()
        current_modifiers = scoring_repo.get_all_provider_modifiers()

    global_avg = _compute_global_avg_score(all_stats)

    result: dict = {"global_avg_score": round(global_avg, 1), "providers": {}}

    for stats in all_stats:
        name = stats["provider_name"]
        proposed = compute_modifier_from_stats(stats, global_avg, min_downloads, max_modifier)
        current = current_modifiers.get(name, 0)

        if proposed is None:
            reason = f"insufficient data ({stats.get('successful_downloads', 0)} < {min_downloads} downloads)"
        elif stats.get("consecutive_failures", 0) >= _CONSECUTIVE_FAILURE_THRESHOLD:
            reason = f"consecutive failure penalty ({stats['consecutive_failures']} failures)"
        else:
            sr = stats.get("success_rate", 0.0)
            reason = (
                f"success_rate={sr:.0%} "
                f"avg_score={stats.get('avg_score', 0):.0f} "
                f"global_avg={global_avg:.0f}"
            )

        result["providers"][name] = {
            "current_modifier": current,
            "proposed_modifier": proposed,
            "stats": {
                "successful_downloads": stats.get("successful_downloads", 0),
                "failed_downloads": stats.get("failed_downloads", 0),
                "success_rate": round(stats.get("success_rate", 0.0), 3),
                "avg_score": round(stats.get("avg_score", 0.0), 1),
                "consecutive_failures": stats.get("consecutive_failures", 0),
            },
            "reason": reason,
        }

    return result


def apply_auto_reranking(force: bool = False) -> dict:
    """Compute and write provider score modifiers based on download history.

    Throttled to at most once per hour unless force=True.

    Returns:
        {"applied": int, "skipped": int, "reason": str}
        Where applied = number of modifiers written, skipped = not enough data.
    """
    global _last_rerank_ts

    from config import get_settings

    settings = get_settings()
    if not settings.provider_reranking_enabled and not force:
        return {"applied": 0, "skipped": 0, "reason": "reranking disabled"}

    now = time.monotonic()
    if not force and (now - _last_rerank_ts) < _RERANK_INTERVAL_SECS:
        remaining = int(_RERANK_INTERVAL_SECS - (now - _last_rerank_ts))
        return {"applied": 0, "skipped": 0, "reason": f"throttled (next in {remaining}s)"}

    _last_rerank_ts = now

    from db import get_db
    from db.repositories.providers import ProviderRepository
    from db.repositories.scoring import ScoringRepository
    from providers.base import invalidate_scoring_cache

    min_downloads = settings.provider_reranking_min_downloads
    max_modifier = settings.provider_reranking_max_modifier

    with get_db() as db:
        provider_repo = ProviderRepository(db)
        scoring_repo = ScoringRepository(db)

        all_stats = provider_repo.get_all_provider_stats()
        global_avg = _compute_global_avg_score(all_stats)

        applied = 0
        skipped = 0
        changes = []

        for stats in all_stats:
            name = stats["provider_name"]
            proposed = compute_modifier_from_stats(stats, global_avg, min_downloads, max_modifier)

            if proposed is None:
                skipped += 1
                continue

            current = scoring_repo.get_provider_modifier(name)
            if proposed != current:
                scoring_repo.set_provider_modifier(name, proposed)
                changes.append(f"{name}: {current:+d} → {proposed:+d}")
                applied += 1

    if applied:
        invalidate_scoring_cache()
        logger.info(
            "Provider re-ranking applied %d modifier(s): %s",
            applied,
            ", ".join(changes),
        )
    else:
        logger.debug("Provider re-ranking: no modifier changes needed")

    return {
        "applied": applied,
        "skipped": skipped,
        "reason": "ok",
        "changes": changes,
        "global_avg_score": round(global_avg, 1),
    }
