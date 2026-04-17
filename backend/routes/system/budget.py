"""Budget status endpoint — exposes per-provider API budget state."""

from __future__ import annotations

import logging

from flask import jsonify

from config import get_settings
from providers import get_provider_manager
from routes.system import bp
from services.provider_budget import get_budget_manager

logger = logging.getLogger(__name__)


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

    from db.repositories.provider_learned_limits import ProviderLearnedLimitsRepository

    learned_by_provider: dict[str, dict] = {}
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
    for name in sorted(mgr._providers.keys()):
        provider = mgr._providers[name]
        tier = getattr(provider, "tier", "free")
        rate_limits = getattr(type(provider), "rate_limits", None) or {}
        limits = rate_limits.get(tier) or rate_limits.get("free") or {}
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
            }
        )

    return jsonify(
        {
            "providers": providers_out,
            "enabled": bool(getattr(settings, "provider_budget_enabled", True)),
        }
    )
