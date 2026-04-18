"""Status and summary reporting methods for ProviderManager.

Used as a mixin. Reads self._providers, self._rate_limits,
self._server_rate_limit_until, self._circuit_breakers, and self.settings.
Does not mutate state.

Importing rule: do NOT import `ProviderManager` here (would cause a
circular import). Access all state via self.
"""

from __future__ import annotations

import logging

from providers.registry import PROVIDER_METADATA  # noqa: F401 — available for subclasses

logger = logging.getLogger(__name__)


class StatusReportingMixin:
    """Mixin for ProviderManager that owns read-only status/summary APIs."""

    def get_provider_status(self) -> list[dict]:
        """Get status of all providers (for API/UI) with priority, downloads, config_fields, and stats."""
        from db.providers import get_provider_download_stats, get_provider_stats

        # Build priority order (use current priority list from _init_providers)
        priority_str = getattr(
            self.settings, "provider_priorities", "animetosho,jimaku,opensubtitles,subdl"
        )
        priority_list = [p.strip() for p in priority_str.split(",") if p.strip()]

        # Get enabled set
        enabled_str = getattr(self.settings, "providers_enabled", "")
        if enabled_str:
            enabled_set = {p.strip() for p in enabled_str.split(",") if p.strip()}
        else:
            from providers.registry import _PROVIDER_CLASSES

            enabled_set = set(_PROVIDER_CLASSES.keys())

        # Download stats from DB (single batch query)
        download_stats = get_provider_download_stats()
        # Performance stats (single batch query — includes auto_disabled, disabled_until,
        # consecutive_failures, successful_downloads, total_searches, etc.)
        performance_stats = get_provider_stats()

        from providers.registry import _PROVIDER_CLASSES

        statuses = []
        for name, cls in _PROVIDER_CLASSES.items():
            priority = priority_list.index(name) if name in priority_list else len(priority_list)
            downloads = download_stats.get(name, {}).get("total", 0)
            config_fields = self._get_provider_config_fields(name)

            # Read all stats from the already-fetched batch (no extra per-provider queries)
            perf_stats = performance_stats.get(name, {})
            total_searches = perf_stats.get("total_searches", 0) or 0
            successful_downloads = perf_stats.get("successful_downloads", 0) or 0
            success_rate = successful_downloads / total_searches if total_searches > 0 else 0.0

            # auto_disabled is stored as int (0/1) in the ORM model; cast to bool.
            # Note: cooldown expiry side-effect (clearing the flag) runs on next actual
            # is_auto_disabled() call; for the status view, the batch value is sufficient.
            auto_disabled = bool(perf_stats.get("auto_disabled", 0))
            stats_dict = {
                "total_searches": perf_stats.get("total_searches", 0),
                "successful_downloads": perf_stats.get("successful_downloads", 0),
                "failed_downloads": perf_stats.get("failed_downloads", 0),
                "success_rate": success_rate,
                "avg_score": perf_stats.get("avg_score", 0),
                "consecutive_failures": perf_stats.get("consecutive_failures", 0),
                "last_success_at": perf_stats.get("last_success_at"),
                "last_failure_at": perf_stats.get("last_failure_at"),
                "avg_response_time_ms": perf_stats.get("avg_response_time_ms", 0) or 0,
                "last_response_time_ms": perf_stats.get("last_response_time_ms", 0) or 0,
                "auto_disabled": auto_disabled,
                "disabled_until": perf_stats.get("disabled_until", "") or "",
            }

            provider = self._providers.get(name)

            # Circuit breaker + rate limit state
            cb_state = "closed"
            throttled_until = None
            throttle_reason = None

            cb = self._circuit_breakers.get(name)
            if cb:
                cb_state = cb.state

            if provider and hasattr(provider, "session"):
                remaining = getattr(provider.session, "rate_limit_remaining_seconds", 0.0)
                if remaining > 0:
                    import time as _time
                    from datetime import UTC, datetime

                    throttled_until = datetime.fromtimestamp(
                        _time.time() + remaining, tz=UTC
                    ).isoformat()
                    throttle_reason = "rate_limited"

            if auto_disabled:
                disabled_until_str = perf_stats.get("disabled_until", "") or ""
                if disabled_until_str:
                    throttled_until = disabled_until_str
                throttle_reason = "auto_disabled"

            if provider:
                # Derive health from cached DB stats — no live HTTP requests.
                consecutive_failures = perf_stats.get("consecutive_failures", 0) or 0
                if auto_disabled:
                    healthy, msg = False, "Auto-disabled"
                elif cb_state == "open":
                    healthy, msg = False, "Circuit breaker open"
                elif consecutive_failures >= 3:
                    healthy, msg = False, f"{consecutive_failures} consecutive failures"
                else:
                    healthy, msg = True, "OK"
                statuses.append(
                    {
                        "name": name,
                        "enabled": name in enabled_set,
                        "initialized": True,
                        "healthy": healthy,
                        "message": msg,
                        "priority": priority,
                        "downloads": downloads,
                        "config_fields": config_fields,
                        "stats": stats_dict,
                        "circuit_breaker_state": cb_state,
                        "throttled_until": throttled_until,
                        "throttle_reason": throttle_reason,
                    }
                )
            else:
                statuses.append(
                    {
                        "name": name,
                        "enabled": name in enabled_set,
                        "initialized": False,
                        "healthy": False,
                        "message": "Not initialized",
                        "priority": priority,
                        "downloads": downloads,
                        "config_fields": config_fields,
                        "stats": stats_dict,
                        "circuit_breaker_state": cb_state,
                        "throttled_until": throttled_until,
                        "throttle_reason": throttle_reason,
                    }
                )

        # Sort by priority
        statuses.sort(key=lambda s: s["priority"])
        return statuses

    def get_provider_summary(self) -> dict:
        """Return aggregate counts of provider states for search progress UI."""
        active = 0
        throttled = 0
        circuit_open = 0
        throttled_providers = []

        enabled_str = getattr(self.settings, "providers_enabled", "")
        if enabled_str:
            enabled_set = {p.strip() for p in enabled_str.split(",") if p.strip()}
        else:
            from providers.registry import _PROVIDER_CLASSES

            enabled_set = set(_PROVIDER_CLASSES.keys())

        for name in enabled_set:
            provider = self._providers.get(name)
            if not provider:
                continue

            cb = self._circuit_breakers.get(name)
            cb_state = cb.state if cb else "closed"

            if cb_state == "open":
                circuit_open += 1
                continue

            remaining = 0.0
            if hasattr(provider, "session"):
                remaining = getattr(provider.session, "rate_limit_remaining_seconds", 0.0)

            if remaining > 0:
                throttled += 1
                throttled_providers.append({"name": name, "remaining_seconds": round(remaining)})
            else:
                # Check auto-disabled
                from db.providers import is_provider_auto_disabled

                if is_provider_auto_disabled(name):
                    throttled += 1
                    throttled_providers.append({"name": name, "remaining_seconds": 0})
                else:
                    active += 1

        return {
            "active": active,
            "throttled": throttled,
            "circuit_open": circuit_open,
            "throttled_providers": throttled_providers,
        }

    @staticmethod
    def _get_provider_config_fields(name: str) -> list[dict]:
        """Return config field definitions for a provider (for dynamic UI forms).

        Reads from the provider class's config_fields attribute instead of
        a hardcoded map. Returns an empty list if the class has no config_fields.
        """
        from providers.registry import _PROVIDER_CLASSES

        cls = _PROVIDER_CLASSES.get(name)
        if cls:
            return getattr(cls, "config_fields", [])
        return []


__all__ = ["StatusReportingMixin"]
