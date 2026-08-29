"""Status and summary reporting methods for ProviderManager.

Used as a mixin. Reads self._providers, self._rate_limits,
self._server_rate_limit_until, self._circuit_breakers, and self.settings.
Does not mutate state.

Importing rule: do NOT import `ProviderManager` here (would cause a
circular import). Access all state via self.
"""

from __future__ import annotations

import logging

from providers.registry import _PROVIDER_CLASSES

logger = logging.getLogger(__name__)

#: How many searches a provider has to have answered before "it never found
#: anything" becomes a verdict rather than a coincidence. Deliberately
#: generous: a niche provider on an unusual library can legitimately miss for
#: a long time, and a false accusation is worse than a late one. The cases
#: this is meant to catch were far past it — podnapisi sat at 1,666 searches
#: with a domain that had no DNS record (#198).
DEAD_PROVIDER_SEARCH_THRESHOLD = 50


#: Machine-readable reasons behind ``healthy``. The UI branches on these
#: instead of guessing from a free-text message — before this, every
#: ``healthy: false`` rendered as "Unreachable", so a provider with no account
#: configured looked like a network outage and sent you hunting in the wrong
#: place (#201).
#:
#: Keep in step with the frontend map in ProvidersOverview.tsx. A value added
#: here without its counterpart there renders as a blank label; that mistake
#: has been made twice in this codebase already.
STATUS_REASONS = (
    "ok",
    "auto_disabled",
    "circuit_open",
    "consecutive_failures",
    "no_results",
    "no_credentials",
    "not_initialized",
)


def _classify_health(
    *,
    auto_disabled: bool,
    cb_state: str,
    consecutive_failures: int,
    total_searches: int,
    results: int,
    downloads: int,
) -> tuple[bool, str, str]:
    """Return ``(healthy, message, reason)`` for an initialised provider.

    Order matters and is deliberate: a provider that is switched off, tripped
    or actively failing has a more urgent explanation than "it never found
    anything", and reporting the latter would hide the former.
    """
    if auto_disabled:
        return False, "Auto-disabled", "auto_disabled"
    if cb_state == "open":
        return False, "Circuit breaker open", "circuit_open"
    if consecutive_failures >= 3:
        return False, f"{consecutive_failures} consecutive failures", "consecutive_failures"
    if _looks_dead(total_searches=total_searches, results=results, downloads=downloads):
        # Answering is not the same as working. Before #198 this read "OK"
        # with a 100% success rate.
        return (
            False,
            f"{total_searches} searches, no results, no downloads",
            "no_results",
        )
    return True, "OK", "ok"


def _uninitialized_reason(config_fields: list[dict], settings) -> tuple[str, str]:
    """Explain why a provider never came up: ``(message, reason)``.

    A provider whose required credentials are blank did not fail — it was
    never asked to start. Saying "Unreachable" for that case is the single
    most misleading label in the panel, because the fix is a form field, not
    a network.
    """
    missing = [
        f.get("key")
        for f in config_fields or []
        if f.get("required") and not (getattr(settings, f.get("key", ""), "") or "")
    ]
    if missing:
        return f"No credentials stored ({', '.join(m for m in missing if m)})", "no_credentials"
    return "Not initialized", "not_initialized"


def _looks_dead(total_searches: int, results: int, downloads: int) -> bool:
    """Has this provider answered plenty and delivered nothing at all?

    One download or one search that returned candidates, ever, is enough to
    clear it — that provider works and is merely selective. What this catches
    is the shape the health panel could not see before: a provider answering
    every single call, politely, while returning nothing, forever.
    """
    if downloads > 0 or results > 0:
        return False
    return total_searches >= DEAD_PROVIDER_SEARCH_THRESHOLD


class StatusReportingMixin:
    """Mixin for ProviderManager that owns read-only status/summary APIs."""

    def get_provider_status(self) -> list[dict]:
        """Get status of all providers (for API/UI) with priority, downloads, config_fields, and stats."""
        from db.providers import get_all_provider_stats_enriched, get_provider_download_stats

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
            enabled_set = set(_PROVIDER_CLASSES.keys())

        # Download stats from DB (single batch query)
        download_stats = get_provider_download_stats()
        # Performance stats — enriched form mirrors the auto_disabled cooldown
        # expiry without an extra DB write, so a provider whose disabled_until
        # has lapsed shows up as auto_disabled=False even before the next
        # search re-enables it for real (B1 audit fix 2026-05-08).
        performance_stats = get_all_provider_stats_enriched()

        statuses = []
        for name, cls in _PROVIDER_CLASSES.items():
            priority = priority_list.index(name) if name in priority_list else len(priority_list)
            downloads = download_stats.get(name, {}).get("total", 0)
            config_fields = self._get_provider_config_fields(name)

            # Read all stats from the already-fetched batch (no extra per-provider queries).
            # The enriched fetch pre-computes success_rate / download_rate / result_rate
            # plus the cooldown-aware auto_disabled flag.
            perf_stats = performance_stats.get(name, {})
            auto_disabled = bool(perf_stats.get("auto_disabled", False))
            stats_dict = {
                "total_searches": perf_stats.get("total_searches", 0),
                "successful_searches": perf_stats.get("successful_searches", 0) or 0,
                "successful_downloads": perf_stats.get("successful_downloads", 0),
                "failed_downloads": perf_stats.get("failed_downloads", 0),
                "success_rate": perf_stats.get("success_rate", 0.0) or 0.0,
                "download_rate": perf_stats.get("download_rate", 0.0) or 0.0,
                "result_rate": perf_stats.get("result_rate", 0.0) or 0.0,
                "avg_score": perf_stats.get("avg_score", 0),
                "consecutive_failures": perf_stats.get("consecutive_failures", 0),
                "last_success_at": perf_stats.get("last_success_at"),
                # Kept apart from last_success_at, which cannot say which path
                # produced it. Search and download use different credentials
                # and fail independently — searches passing while downloads
                # 401 is a real, and previously invisible, outage shape.
                "last_search_at": perf_stats.get("last_search_at"),
                "last_download_at": perf_stats.get("last_download_at"),
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

            # Declared language support — lets the UI offer only meaningful
            # options for the per-provider language exclusion (#192).
            supported_languages = sorted(getattr(cls, "languages", None) or [])

            if provider:
                # Derive health from cached DB stats — no live HTTP requests.
                healthy, msg, status_reason = _classify_health(
                    auto_disabled=auto_disabled,
                    cb_state=cb_state,
                    consecutive_failures=perf_stats.get("consecutive_failures", 0) or 0,
                    total_searches=stats_dict.get("total_searches", 0) or 0,
                    results=stats_dict.get("successful_searches", 0) or 0,
                    downloads=downloads,
                )
                statuses.append(
                    {
                        "name": name,
                        "enabled": name in enabled_set,
                        "initialized": True,
                        "healthy": healthy,
                        "message": msg,
                        "status_reason": status_reason,
                        "priority": priority,
                        "downloads": downloads,
                        "config_fields": config_fields,
                        "languages": supported_languages,
                        "stats": stats_dict,
                        "circuit_breaker_state": cb_state,
                        "throttled_until": throttled_until,
                        "throttle_reason": throttle_reason,
                    }
                )
            else:
                uninit_msg, uninit_reason = _uninitialized_reason(config_fields, self.settings)
                statuses.append(
                    {
                        "name": name,
                        "enabled": name in enabled_set,
                        "initialized": False,
                        "healthy": False,
                        "message": uninit_msg,
                        "status_reason": uninit_reason,
                        "priority": priority,
                        "downloads": downloads,
                        "config_fields": config_fields,
                        "languages": supported_languages,
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
        cls = _PROVIDER_CLASSES.get(name)
        if cls:
            return getattr(cls, "config_fields", [])
        return []


__all__ = ["StatusReportingMixin"]
