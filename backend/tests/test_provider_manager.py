"""Unit tests for ProviderManager -- cache hit/miss, circuit breaker, rate limiter."""

from unittest.mock import MagicMock

import pytest

from providers.base import SubtitleFormat, SubtitleResult


def _make_real_result(provider_name="test_provider"):
    """Return a minimal but real SubtitleResult (avoids AttributeError in post-processing)."""
    return SubtitleResult(
        provider_name=provider_name,
        subtitle_id="sub-001",
        language="de",
        format=SubtitleFormat.SRT,
        filename="test.srt",
        score=80,
        release_info="",
        hearing_impaired=False,
        forced=False,
        provider_data={},
    )


def _make_mock_provider(name="test_provider"):
    """Return a mock provider that always returns one result."""
    result = _make_real_result(name)
    provider = MagicMock(spec_set=["name", "search", "download"])
    provider.name = name
    provider.search = MagicMock(return_value=[result])
    provider.download = MagicMock(return_value=b"subtitle content")
    return provider, result


def _patch_db_noop(monkeypatch):
    """Patch all db.providers side effects so tests are deterministic."""
    monkeypatch.setattr("db.providers.is_provider_auto_disabled", lambda name: False)
    monkeypatch.setattr("db.providers.update_provider_stats", lambda *a, **kw: None)
    monkeypatch.setattr("db.providers.cache_provider_results", lambda *a, **kw: None)
    # DB cache: always miss
    monkeypatch.setattr("db.providers.get_cached_results", lambda *a, **kw: None)
    # get_all_provider_stats may not exist in all versions -- use raising=False
    monkeypatch.setattr(
        "db.providers.get_all_provider_stats", lambda: [], raising=False
    )


def _bypass_fast_cache(monkeypatch):
    """Patch _get_cache_backend at class level (it's a @staticmethod — instance shadow is fragile)."""
    monkeypatch.setattr("providers.ProviderManager._get_cache_backend", staticmethod(lambda: None))


def _make_query(file_path="/test/movie.mkv", languages=None):
    """Build a minimal VideoQuery-compatible mock."""
    from providers.base import VideoQuery

    return VideoQuery(
        file_path=file_path,
        languages=languages or ["de"],
        forced_only=False,
    )


# ---------------------------------------------------------------------------
# Cache tests
# ---------------------------------------------------------------------------


class TestProviderManagerCache:
    """search() must cache results and return them on second call without hitting provider."""

    def test_cache_hit_skips_provider_on_second_search(self, app_ctx, monkeypatch):
        from providers import ProviderManager

        manager = ProviderManager()
        provider, result = _make_mock_provider()

        manager._providers.clear()
        manager._providers["test_provider"] = provider

        cb = MagicMock()
        cb.allow_request.return_value = True
        manager._circuit_breakers["test_provider"] = cb

        _patch_db_noop(monkeypatch)

        # Controlled two-tier cache: stores on first write, returns on second get
        stored = {}

        class ControlledCache:
            def get(self, key):
                return stored.get(key)

            def set(self, key, value, ttl_seconds=None, ex=None):
                stored[key] = value

        monkeypatch.setattr(manager, "_get_cache_backend", lambda: ControlledCache())

        query = _make_query("/test/cache_test.mkv")

        manager.search(query)
        calls_after_first = provider.search.call_count

        manager.search(query)
        calls_after_second = provider.search.call_count

        assert calls_after_second == calls_after_first, (
            f"Provider.search called again on cache hit "
            f"(calls: first={calls_after_first}, second={calls_after_second})"
        )

    def test_cache_miss_always_hits_provider(self, app_ctx, monkeypatch):
        from providers import ProviderManager

        manager = ProviderManager()
        provider, _ = _make_mock_provider()

        manager._providers.clear()
        manager._providers["test_provider"] = provider

        cb = MagicMock()
        cb.allow_request.return_value = True
        manager._circuit_breakers["test_provider"] = cb

        _patch_db_noop(monkeypatch)
        # Both tiers always miss
        _bypass_fast_cache(monkeypatch)

        query = _make_query("/test/no_cache.mkv")

        manager.search(query)
        manager.search(query)

        assert provider.search.call_count == 2, (
            "Provider.search should be called on every search when cache misses"
        )


# ---------------------------------------------------------------------------
# Circuit breaker tests
# ---------------------------------------------------------------------------


class TestCircuitBreaker:
    """Open circuit breaker must prevent provider calls."""

    def test_open_circuit_breaker_skips_provider(self, app_ctx, monkeypatch):
        from providers import ProviderManager

        manager = ProviderManager()
        provider, _ = _make_mock_provider()

        _patch_db_noop(monkeypatch)
        _bypass_fast_cache(monkeypatch)

        # Circuit breaker OPEN: allow_request() returns False
        open_cb = MagicMock()
        open_cb.allow_request.return_value = False

        manager._providers.clear()
        manager._providers["test_provider"] = provider
        manager._circuit_breakers["test_provider"] = open_cb

        query = _make_query("/test/cb_open.mkv")
        manager.search(query)

        assert not provider.search.called, (
            "provider.search was called despite circuit breaker being open"
        )

    def test_closed_circuit_breaker_allows_provider(self, app_ctx, monkeypatch):
        from providers import ProviderManager

        manager = ProviderManager()
        provider, _ = _make_mock_provider()

        _patch_db_noop(monkeypatch)
        _bypass_fast_cache(monkeypatch)

        # Circuit breaker CLOSED: allow_request() returns True
        closed_cb = MagicMock()
        closed_cb.allow_request.return_value = True

        manager._providers.clear()
        manager._providers["test_provider"] = provider
        manager._circuit_breakers["test_provider"] = closed_cb

        query = _make_query("/test/cb_closed.mkv")
        manager.search(query)

        assert provider.search.called, (
            "Provider was not called despite closed circuit breaker"
        )

    def test_no_circuit_breaker_entry_allows_provider(self, app_ctx, monkeypatch):
        """Provider with no circuit breaker entry must not be blocked."""
        from providers import ProviderManager

        manager = ProviderManager()
        provider, _ = _make_mock_provider()

        _patch_db_noop(monkeypatch)
        _bypass_fast_cache(monkeypatch)

        manager._providers.clear()
        manager._providers["test_provider"] = provider
        # No circuit breaker registered for this provider
        manager._circuit_breakers.clear()

        query = _make_query("/test/cb_none.mkv")
        manager.search(query)

        assert provider.search.called, (
            "Provider without circuit breaker entry must not be skipped"
        )


# ---------------------------------------------------------------------------
# Rate limiter tests
# ---------------------------------------------------------------------------


class TestRateLimiter:
    """Rate limiter check must gate provider access."""

    def test_rate_limited_provider_is_skipped(self, app_ctx, monkeypatch):
        from providers import ProviderManager

        manager = ProviderManager()
        provider, _ = _make_mock_provider()

        _patch_db_noop(monkeypatch)
        _bypass_fast_cache(monkeypatch)

        # Force rate limit to deny access
        monkeypatch.setattr(manager, "_check_rate_limit", lambda name: False)

        manager._providers.clear()
        manager._providers["test_provider"] = provider

        cb = MagicMock()
        cb.allow_request.return_value = True
        manager._circuit_breakers["test_provider"] = cb

        query = _make_query("/test/rate_limited.mkv")
        manager.search(query)

        assert not provider.search.called, (
            "Provider was called despite rate limit returning False"
        )

    def test_rate_not_limited_provider_is_called(self, app_ctx, monkeypatch):
        from providers import ProviderManager

        manager = ProviderManager()
        provider, _ = _make_mock_provider()

        _patch_db_noop(monkeypatch)
        _bypass_fast_cache(monkeypatch)

        # Rate limit allows access
        monkeypatch.setattr(manager, "_check_rate_limit", lambda name: True)

        manager._providers.clear()
        manager._providers["test_provider"] = provider

        cb = MagicMock()
        cb.allow_request.return_value = True
        manager._circuit_breakers["test_provider"] = cb

        query = _make_query("/test/rate_ok.mkv")
        manager.search(query)

        assert provider.search.called, (
            "Provider was not called despite rate limit allowing access"
        )
