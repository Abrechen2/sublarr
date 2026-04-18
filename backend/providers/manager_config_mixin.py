"""Config / rate-limit / timeout resolution methods for ProviderManager.

Used as a mixin — not instantiated directly. The mixin methods read
instance attributes (self.settings, self._providers, self._rate_limits,
self._rate_limit_lock, self._server_rate_limit_until) that are
initialised by ProviderManager.__init__.

Importing rule: keep all provider-state reads going through `self`; do
NOT import `ProviderManager` here (would cause a circular import).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from providers.registry import _PROVIDER_CLASSES, PROVIDER_METADATA

logger = logging.getLogger(__name__)


class ConfigResolvingMixin:
    """Mixin for ProviderManager that owns per-provider config lookup,
    rate-limit tracking, and dynamic timeout computation."""

    def _get_provider_config(self, name: str) -> dict:
        """Get provider-specific config from settings or plugin DB config.

        For built-in providers, reads config from Pydantic Settings using
        the config_fields declared on the provider class. For plugins
        (is_plugin=True), reads from the plugin config DB table instead.
        """
        cls = _PROVIDER_CLASSES.get(name)
        if not cls:
            return {}

        config = {}

        if getattr(cls, "is_plugin", False):
            # Plugin providers: read config from DB
            try:
                from db.plugins import get_plugin_config

                plugin_config = get_plugin_config(name)
                for field in getattr(cls, "config_fields", []):
                    key = field["key"]
                    config[key] = plugin_config.get(key, field.get("default", ""))
            except Exception as e:
                logger.warning("Failed to read plugin config for %s: %s", name, e)
        else:
            # Built-in providers: read from Pydantic Settings
            for field in getattr(cls, "config_fields", []):
                key = field["key"]
                config[key] = getattr(self.settings, key, field.get("default", ""))

        # Map settings-level keys to constructor parameter names.
        # Built-in providers expect short param names (e.g. "api_key" not
        # "opensubtitles_api_key"), so strip the provider-name prefix.
        mapped_config = {}
        for key, value in config.items():
            # e.g. "opensubtitles_api_key" -> "api_key", "jimaku_api_key" -> "api_key"
            short_key = key
            prefix = f"{name}_"
            if key.startswith(prefix):
                short_key = key[len(prefix) :]
            mapped_config[short_key] = value

        # Strip whitespace from all credential values (prevent paste artifacts)
        for key in mapped_config:
            if isinstance(mapped_config[key], str):
                mapped_config[key] = mapped_config[key].strip()

        return mapped_config

    def _get_rate_limit(self, provider_name: str) -> tuple[int, int]:
        """Get rate limit for a provider: (max_requests, window_seconds).

        Prefers class attribute, falls back to registry, then (0, 0).
        """
        cls = _PROVIDER_CLASSES.get(provider_name)
        if cls:
            class_limit = getattr(cls, "rate_limit", (0, 0))
            if class_limit != (0, 0):
                return class_limit
        return PROVIDER_METADATA.get(provider_name, {}).get("rate_limit", (0, 0))

    def _compute_dynamic_timeout(self, provider_name: str, stats: dict) -> int | None:
        """Compute a dynamic timeout from provider stats (avg response time × multiplier + buffer).

        Returns None if dynamic timeouts are disabled or there are too few samples.
        Formula: max(min_s, min(avg_ms * multiplier / 1000 + buffer, max_s))
        """
        if not getattr(self.settings, "provider_dynamic_timeout_enabled", True):
            return None
        total = stats.get("total_searches", 0) or 0
        min_samples = getattr(self.settings, "provider_dynamic_timeout_min_samples", 5)
        if total < min_samples:
            return None
        avg_ms = stats.get("avg_response_time_ms", 0) or 0
        if avg_ms <= 0:
            return None
        multiplier = getattr(self.settings, "provider_dynamic_timeout_multiplier", 3.0)
        buffer = getattr(self.settings, "provider_dynamic_timeout_buffer_secs", 2.0)
        min_s = getattr(self.settings, "provider_dynamic_timeout_min_secs", 5)
        max_s = getattr(self.settings, "provider_dynamic_timeout_max_secs", 30)
        return int(max(min_s, min((avg_ms * multiplier / 1000) + buffer, max_s)))

    def _get_timeout(self, provider_name: str, all_stats: dict | None = None) -> int:
        """Get timeout for a provider (seconds).

        Priority:
        1. Dynamic timeout computed from historical avg_response_time_ms
        2. Class attribute (provider-specific hardcoded timeout)
        3. Registry (PROVIDER_METADATA)
        4. Global provider_search_timeout setting

        The global provider_search_timeout acts as an upper bound — no provider
        timeout may exceed it, so the setting is always effective.
        """
        global_cap = self.settings.provider_search_timeout
        # 1. Dynamic timeout from stats
        if all_stats and provider_name in all_stats:
            dynamic = self._compute_dynamic_timeout(provider_name, all_stats[provider_name])
            if dynamic:
                return min(dynamic, global_cap)
        # 2. Class attribute
        cls = _PROVIDER_CLASSES.get(provider_name)
        if cls:
            class_timeout = getattr(cls, "timeout", 0)
            if class_timeout > 0:
                return min(class_timeout, global_cap)
        # 3. Registry, 4. Global setting
        meta = PROVIDER_METADATA.get(provider_name, {})
        return min(meta.get("timeout", global_cap), global_cap)

    def _get_retries(self, provider_name: str) -> int:
        """Get retry count for a provider.

        Prefers class attribute, falls back to registry, then default 2.
        """
        cls = _PROVIDER_CLASSES.get(provider_name)
        if cls:
            class_retries = getattr(cls, "max_retries", -1)
            if class_retries >= 0:
                return class_retries
        return PROVIDER_METADATA.get(provider_name, {}).get("retries", 2)

    def _check_rate_limit(self, provider_name: str) -> bool:
        """Check if provider is within rate limit.

        Returns:
            True if request is allowed, False if rate limited
        """
        if not getattr(self.settings, "provider_rate_limit_enabled", True):
            return True

        # Check server-imposed rate limit (from 429 responses) — shared across threads
        import time as _time

        until = self._server_rate_limit_until.get(provider_name, 0)
        if _time.time() < until:
            logger.debug(
                "Provider %s server-rate-limited for %.0fs more",
                provider_name,
                until - _time.time(),
            )
            return False

        max_requests, window_seconds = self._get_rate_limit(provider_name)
        if max_requests == 0 and window_seconds == 0:
            return True  # No rate limit configured
        with self._rate_limit_lock:
            now = datetime.now(UTC)
            timestamps = self._rate_limits[provider_name]

            # Remove old timestamps outside the window
            window = timedelta(seconds=window_seconds)
            timestamps[:] = [ts for ts in timestamps if now - ts < window]

            if len(timestamps) >= max_requests:
                logger.debug(
                    "Provider %s rate limited: %d/%d requests in %ds window",
                    provider_name,
                    len(timestamps),
                    max_requests,
                    window_seconds,
                )
                return False  # Rate limited

            # Record this request
            timestamps.append(now)
            return True


__all__ = ["ConfigResolvingMixin"]
