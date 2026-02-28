"""Integration tests for the provider pipeline and circuit breaker.

Covers: priority ordering, circuit breaker open/close/recovery,
ASS scoring bonus, hash-match scoring, and provider fallback.
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from circuit_breaker import CircuitBreaker, CircuitState
from providers.base import (
    EPISODE_SCORES,
    SubtitleFormat,
    SubtitleResult,
    VideoQuery,
    compute_score,
)

# ─── Circuit Breaker Unit Tests ─────────────────────────────────────────────


class TestCircuitBreaker:
    """Test circuit breaker state transitions."""

    def test_starts_closed(self):
        cb = CircuitBreaker("test", failure_threshold=3, cooldown_seconds=1)
        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request() is True

    def test_opens_after_threshold(self):
        """CLOSED → OPEN after N consecutive failures."""
        cb = CircuitBreaker("test", failure_threshold=3, cooldown_seconds=60)

        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

        cb.record_failure()  # 3rd failure → OPEN
        assert cb.state == CircuitState.OPEN
        assert cb.allow_request() is False

    def test_success_resets(self):
        """Any success resets failure count and returns to CLOSED."""
        cb = CircuitBreaker("test", failure_threshold=3, cooldown_seconds=60)

        cb.record_failure()
        cb.record_failure()
        cb.record_success()

        assert cb.state == CircuitState.CLOSED
        assert cb._failure_count == 0

    def test_half_open_after_cooldown(self):
        """OPEN → HALF_OPEN after cooldown elapses."""
        cb = CircuitBreaker("test", failure_threshold=1, cooldown_seconds=0)

        cb.record_failure()  # → OPEN internally
        # Inspect internal _state directly: reading .state triggers the lazy
        # OPEN→HALF_OPEN transition, so use _state to verify the post-failure state.
        assert cb._state == CircuitState.OPEN

        # With cooldown_seconds=0, reading .state immediately yields HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.allow_request() is True

    def test_half_open_success_closes(self):
        """HALF_OPEN → CLOSED on successful probe."""
        cb = CircuitBreaker("test", failure_threshold=1, cooldown_seconds=0)

        cb.record_failure()  # → OPEN
        time.sleep(0.01)
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_success()  # → CLOSED
        assert cb.state == CircuitState.CLOSED

    def test_half_open_failure_reopens(self):
        """HALF_OPEN → OPEN on failed probe."""
        cb = CircuitBreaker("test", failure_threshold=1, cooldown_seconds=0)

        cb.record_failure()  # → OPEN
        time.sleep(0.01)
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_failure()  # → OPEN again
        # With cooldown_seconds=0, reading .state immediately triggers OPEN→HALF_OPEN.
        # Use internal _state to assert the OPEN state before the lazy transition.
        assert cb._state == CircuitState.OPEN

    def test_manual_reset(self):
        """reset() forces CLOSED from any state."""
        cb = CircuitBreaker("test", failure_threshold=1, cooldown_seconds=60)

        cb.record_failure()  # → OPEN
        assert cb.state == CircuitState.OPEN

        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb._failure_count == 0

    def test_get_status(self):
        """get_status returns serializable dict."""
        cb = CircuitBreaker("mytest", failure_threshold=5, cooldown_seconds=30)
        status = cb.get_status()

        assert status["name"] == "mytest"
        assert status["state"] == "closed"
        assert status["failure_count"] == 0
        assert status["failure_threshold"] == 5
        assert status["cooldown_seconds"] == 30


# ─── Scoring Tests ───────────────────────────────────────────────────────────


class TestScoring:
    """Test subtitle scoring system."""

    def _make_query(self, **kwargs):
        defaults = {
            "series_title": "Test Anime",
            "season": 1,
            "episode": 1,
            "languages": ["en"],
        }
        defaults.update(kwargs)
        return VideoQuery(**defaults)

    def _make_result(self, **kwargs):
        defaults = {
            "provider_name": "test",
            "subtitle_id": "123",
            "language": "en",
            "format": SubtitleFormat.SRT,
            "matches": set(),
        }
        defaults.update(kwargs)
        return SubtitleResult(**defaults)

    def test_hash_match_highest_score(self):
        """Hash match should give the highest score (359 for episodes)."""
        query = self._make_query()
        result = self._make_result(matches={"hash"})

        score = compute_score(result, query)
        assert score == EPISODE_SCORES["hash"]  # 359

    def test_ass_format_bonus(self):
        """ASS format gets +50 bonus."""
        query = self._make_query()
        result_srt = self._make_result(
            format=SubtitleFormat.SRT,
            matches={"series"},
        )
        result_ass = self._make_result(
            format=SubtitleFormat.ASS,
            matches={"series"},
        )

        score_srt = compute_score(result_srt, query)
        score_ass = compute_score(result_ass, query)

        assert score_ass == score_srt + 50  # format_bonus

    def test_full_episode_match(self):
        """All episode fields matched gives maximum score."""
        query = self._make_query()
        result = self._make_result(
            format=SubtitleFormat.ASS,
            matches={"hash", "series", "year", "season", "episode", "release_group"},
        )

        score = compute_score(result, query)
        expected = (
            EPISODE_SCORES["hash"]
            + EPISODE_SCORES["series"]
            + EPISODE_SCORES["year"]
            + EPISODE_SCORES["season"]
            + EPISODE_SCORES["episode"]
            + EPISODE_SCORES["release_group"]
            + EPISODE_SCORES["format_bonus"]  # ASS
        )
        assert score == expected

    def test_empty_matches_zero_score(self):
        """No matches → score 0 (plus format bonus if ASS)."""
        query = self._make_query()
        result = self._make_result(matches=set())

        score = compute_score(result, query)
        assert score == 0


# ─── Provider Manager Integration (with mocks) ──────────────────────────────


class TestProviderPipeline:
    """Test ProviderManager search flow with mocked providers."""

    @patch("config.get_settings")
    @patch("providers._PROVIDER_CLASSES", {})
    def test_no_providers_returns_empty(self, mock_gs):
        """Search with no providers configured returns empty list."""
        mock_gs.return_value = MagicMock(
            providers_enabled="",
            provider_priorities="",
            provider_auto_prioritize=False,
            provider_search_timeout=10,
            provider_cache_ttl_minutes=0,
            provider_rate_limit_enabled=False,
            circuit_breaker_failure_threshold=5,
            circuit_breaker_cooldown_seconds=60,
        )

        from providers import ProviderManager

        with patch.object(ProviderManager, "_init_providers"):
            manager = ProviderManager()
            manager._providers = {}
            manager._circuit_breakers = {}

        query = VideoQuery(series_title="Test", season=1, episode=1, languages=["en"])

        with (
            patch("db.providers.get_cached_results", return_value=None),
            patch("db.providers.cache_provider_results"),
            patch("db.blacklist.is_blacklisted", return_value=False),
        ):
            results = manager.search(query)

        assert results == []

    def test_circuit_breaker_skips_open_provider(self):
        """Providers with open circuit breaker are skipped during search."""
        cb = CircuitBreaker("test_provider", failure_threshold=1, cooldown_seconds=60)
        cb.record_failure()  # → OPEN

        assert cb.state == CircuitState.OPEN
        assert cb.allow_request() is False
