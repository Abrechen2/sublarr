"""Budget status endpoint — exposes per-provider API budget state."""

from __future__ import annotations

import logging

from flask import jsonify

from config import get_settings
from db.repositories.provider_account_pool import ProviderAccountPoolRepository
from db.repositories.provider_learned_limits import ProviderLearnedLimitsRepository
from providers import get_provider_manager
from routes.system import bp
from services.provider_budget import get_budget_manager

logger = logging.getLogger(__name__)

_TIER_RANK = {"vip+": 2, "vip": 1, "free": 0}


def _aggregate_tier(keys: list[dict]) -> str:
    """Highest-tier among enabled keys (vip+ > vip > free). Default 'free' on empty.

    Logs a warning when a key's tier is not in ``_TIER_RANK`` — it'll silently
    sort as 0 which may silently hide pool misconfiguration.
    """
    if not keys:
        return "free"

    def _rank(k: dict) -> int:
        r = _TIER_RANK.get(k["tier"])
        if r is None:
            logger.warning(
                "unknown tier %r for pool key id=%s — ranking as 0",
                k["tier"],
                k.get("id"),
            )
            return 0
        return r

    return max(keys, key=_rank)["tier"]


def _aggregate_limits(keys: list[dict], rate_limits: dict) -> dict:
    """Sum of per-tier rate_limits across enabled keys."""
    out = {"second": 0, "hour": 0, "day": 0}
    for k in keys:
        tier_limits = rate_limits.get(k["tier"]) or rate_limits.get("free") or {}
        for w in ("second", "hour", "day"):
            out[w] += tier_limits.get(w, 0)
    return out


@bp.route("/system/budget", methods=["GET"])
def get_budget_state():
    """Return current budget state for every registered provider.

    ---
    get:
      tags:
        - System
      summary: Get API-budget state per provider
      description: >
        Live per-provider budget snapshot. Each entry reports the provider's
        tier, its effective rate limits, current usage across the three
        windows (second/hour/day), and how many seconds remain until each
        window resets.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Budget snapshot
    """
    settings = get_settings()
    mgr = get_provider_manager()
    budget = get_budget_manager()

    learned_by_provider: dict[str, dict] = {}
    # Fetch learned-limit rows in bulk; on any failure, degrade the whole block
    # to an empty map so all providers get learning=None rather than a partial/
    # inconsistent mix.
    try:
        for (provider, window), row in ProviderLearnedLimitsRepository().get_all().items():
            # Surface the "day" window only — that is what the dashboard shows.
            if window == "day":
                last_429 = row.get("last_429_at")
                learned_by_provider[provider] = {
                    "adjustment_factor": row["adjustment_factor"],
                    "consecutive_good_days": row["consecutive_good_days"],
                    "last_429_at": last_429.isoformat() if last_429 else None,
                }
    except Exception as exc:  # noqa: BLE001
        logger.warning("learned-limits lookup failed (non-blocking): %s", exc)

    providers_out = []
    pools_by_provider = ProviderAccountPoolRepository().get_enabled_grouped()
    for name in sorted(mgr._providers.keys()):
        provider = mgr._providers[name]
        rate_limits = getattr(type(provider), "rate_limits", None) or {}
        pool_rows = pools_by_provider.get(name, [])
        per_key = budget.get_usage_per_key(name)
        # NOTE: outer `tier` is the HIGHEST enabled key's tier (for the badge).
        # `limits` is the SUM across all keys (including lower-tier ones). UI
        # consumers must read `limits` for budget math, not infer from `tier`.
        if pool_rows:
            tier = _aggregate_tier(pool_rows)
            limits = _aggregate_limits(pool_rows, rate_limits)
        else:
            tier = getattr(provider, "tier", "free")
            limits = rate_limits.get(tier) or rate_limits.get("free") or {}
        keys_out = []
        for r in pool_rows:
            keys_out.append(
                {
                    "id": r["id"],
                    "label": r["account_label"],
                    "tier": r["tier"],
                    "used": per_key.get(r["id"], {"second": 0, "hour": 0, "day": 0}),
                    "limit": rate_limits.get(r["tier"]) or rate_limits.get("free") or {},
                    "last_429_at": (r["last_429_at"].isoformat() if r["last_429_at"] else None),
                    "last_used_at": (r["last_used_at"].isoformat() if r["last_used_at"] else None),
                }
            )
        usage = budget.get_usage(name)
        reset_seconds = {
            window: budget.seconds_until_next_window(window) for window in ("second", "hour", "day")
        }
        providers_out.append(
            {
                "name": name,
                "tier": tier,
                "limits": limits,
                "usage": usage,
                "reset_seconds": reset_seconds,
                "learning": learned_by_provider.get(name),
                "keys": keys_out,
            }
        )

    return jsonify(
        {
            "providers": providers_out,
            "enabled": bool(getattr(settings, "provider_budget_enabled", True)),
        }
    )
