"""Provider re-ranking engine tests.

Tests:
- TestComputeModifierFromStats: formula correctness, edge cases
- TestComputeGlobalAvgScore: weighted average calculation
- TestRerankingThrottle: throttle prevents repeated runs
- TestRerankingDisabled: no-op when feature flag is off
"""

import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from providers.reranker import (
    _BASELINE_SUCCESS_RATE,
    _CONSECUTIVE_FAILURE_THRESHOLD,
    _compute_global_avg_score,
    compute_modifier_from_stats,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _stats(
    successful=30,
    failed=10,
    avg_score=800.0,
    success_rate=None,
    consecutive_failures=0,
):
    if success_rate is None:
        total = successful + failed
        success_rate = successful / total if total > 0 else 0.0
    return {
        "provider_name": "testprovider",
        "successful_downloads": successful,
        "failed_downloads": failed,
        "avg_score": avg_score,
        "success_rate": success_rate,
        "consecutive_failures": consecutive_failures,
    }


# ── TestComputeModifierFromStats ──────────────────────────────────────────────


class TestComputeModifierFromStats:
    def test_none_when_below_min_downloads(self):
        result = compute_modifier_from_stats(
            _stats(successful=5), global_avg_score=800.0, min_downloads=20, max_modifier=50
        )
        assert result is None

    def test_zero_when_exactly_at_baseline_success_rate(self):
        result = compute_modifier_from_stats(
            _stats(successful=20, failed=10, success_rate=_BASELINE_SUCCESS_RATE, avg_score=800.0),
            global_avg_score=800.0,
            min_downloads=20,
            max_modifier=50,
        )
        # At baseline success rate AND avg score == global avg → modifier near 0
        assert result is not None
        assert abs(result) <= 5  # small rounding allowed

    def test_positive_modifier_for_high_success_rate(self):
        result = compute_modifier_from_stats(
            _stats(successful=50, failed=5, success_rate=0.91, avg_score=850.0),
            global_avg_score=800.0,
            min_downloads=20,
            max_modifier=50,
        )
        assert result is not None
        assert result > 0

    def test_negative_modifier_for_low_success_rate(self):
        result = compute_modifier_from_stats(
            _stats(successful=20, failed=40, success_rate=0.33, avg_score=600.0),
            global_avg_score=800.0,
            min_downloads=20,
            max_modifier=50,
        )
        assert result is not None
        assert result < 0

    def test_hard_penalty_for_consecutive_failures(self):
        result = compute_modifier_from_stats(
            _stats(
                successful=50,
                failed=5,
                success_rate=0.91,
                consecutive_failures=_CONSECUTIVE_FAILURE_THRESHOLD,
            ),
            global_avg_score=800.0,
            min_downloads=20,
            max_modifier=50,
        )
        assert result is not None
        assert result < 0  # Even with high success rate, consecutive failures penalize

    def test_modifier_capped_at_max(self):
        # Perfect provider with low global avg
        result = compute_modifier_from_stats(
            _stats(successful=1000, failed=0, success_rate=1.0, avg_score=1000.0),
            global_avg_score=100.0,
            min_downloads=20,
            max_modifier=50,
        )
        assert result is not None
        assert result <= 50

    def test_modifier_floor_at_negative_max(self):
        # Terrible provider
        result = compute_modifier_from_stats(
            _stats(successful=20, failed=200, success_rate=0.09, avg_score=100.0),
            global_avg_score=900.0,
            min_downloads=20,
            max_modifier=50,
        )
        assert result is not None
        assert result >= -50

    def test_no_score_bonus_when_global_avg_zero(self):
        # When global_avg_score is 0, score component should be 0
        result_with_avg = compute_modifier_from_stats(
            _stats(successful=30, failed=10, success_rate=0.75, avg_score=900.0),
            global_avg_score=800.0,
            min_downloads=20,
            max_modifier=50,
        )
        result_no_avg = compute_modifier_from_stats(
            _stats(successful=30, failed=10, success_rate=0.75, avg_score=900.0),
            global_avg_score=0.0,
            min_downloads=20,
            max_modifier=50,
        )
        # With global_avg=0, score component is skipped — result is success_rate component only
        assert result_no_avg is not None
        assert result_with_avg is not None
        # Should differ (score component was adding bonus with global_avg=800)
        assert result_no_avg != result_with_avg

    def test_zero_consecutive_failures_no_penalty(self):
        result = compute_modifier_from_stats(
            _stats(successful=50, consecutive_failures=0, success_rate=0.83),
            global_avg_score=800.0,
            min_downloads=20,
            max_modifier=50,
        )
        assert result is not None
        assert result >= 0  # No failure streak → no penalty from that component


# ── TestComputeGlobalAvgScore ─────────────────────────────────────────────────


class TestComputeGlobalAvgScore:
    def _make_stats(self, name, avg_score, n):
        return {
            "provider_name": name,
            "avg_score": avg_score,
            "successful_downloads": n,
        }

    def test_empty_list_returns_zero(self):
        assert _compute_global_avg_score([]) == 0.0

    def test_single_provider(self):
        result = _compute_global_avg_score([self._make_stats("p1", 800.0, 10)])
        assert result == pytest.approx(800.0)

    def test_weighted_by_download_count(self):
        # p1: avg=600 with 100 downloads, p2: avg=900 with 100 downloads → avg=750
        stats = [
            self._make_stats("p1", 600.0, 100),
            self._make_stats("p2", 900.0, 100),
        ]
        result = _compute_global_avg_score(stats)
        assert result == pytest.approx(750.0)

    def test_higher_weight_dominates(self):
        # p1: avg=400 with 10 downloads, p2: avg=900 with 990 downloads → heavily weighted to p2
        stats = [
            self._make_stats("p1", 400.0, 10),
            self._make_stats("p2", 900.0, 990),
        ]
        result = _compute_global_avg_score(stats)
        assert result > 800.0  # p2 should dominate

    def test_providers_with_zero_score_excluded(self):
        stats = [
            self._make_stats("p1", 0.0, 100),  # excluded
            self._make_stats("p2", 800.0, 50),
        ]
        result = _compute_global_avg_score(stats)
        assert result == pytest.approx(800.0)

    def test_providers_with_zero_downloads_excluded(self):
        stats = [
            self._make_stats("p1", 900.0, 0),  # excluded
            self._make_stats("p2", 800.0, 50),
        ]
        result = _compute_global_avg_score(stats)
        assert result == pytest.approx(800.0)


# ── TestRerankingDisabled ─────────────────────────────────────────────────────


class TestRerankingDisabled:
    def test_returns_disabled_reason_when_feature_flag_off(self):
        from providers.reranker import apply_auto_reranking

        mock_settings = MagicMock()
        mock_settings.provider_reranking_enabled = False

        with patch("config.get_settings", return_value=mock_settings):
            result = apply_auto_reranking(force=False)

        assert result["applied"] == 0
        assert "disabled" in result["reason"]

    def test_force_bypasses_feature_flag_check(self):
        """force=True must bypass the enabled check (used for manual triggers)."""
        from providers import reranker

        mock_settings = MagicMock()
        mock_settings.provider_reranking_enabled = False
        mock_settings.provider_reranking_min_downloads = 20
        mock_settings.provider_reranking_max_modifier = 50

        with (
            patch("config.get_settings", return_value=mock_settings),
            patch("db.get_db") as mock_db_ctx,
        ):
            mock_db = MagicMock()
            mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

            mock_provider_repo = MagicMock()
            mock_provider_repo.get_all_provider_stats.return_value = []
            mock_scoring_repo = MagicMock()
            mock_scoring_repo.get_all_provider_modifiers.return_value = {}

            with (
                patch(
                    "db.repositories.providers.ProviderRepository", return_value=mock_provider_repo
                ),
                patch("db.repositories.scoring.ScoringRepository", return_value=mock_scoring_repo),
                patch("providers.base.invalidate_scoring_cache"),
            ):
                result = reranker.apply_auto_reranking(force=True)

        # Should NOT return "disabled" — it ran (even with empty stats)
        assert "disabled" not in result["reason"]


# ── TestRerankingThrottle ─────────────────────────────────────────────────────


class TestRerankingThrottle:
    def test_throttled_after_recent_run(self):
        from providers import reranker

        mock_settings = MagicMock()
        mock_settings.provider_reranking_enabled = True

        # Simulate last run just now
        reranker._last_rerank_ts = time.monotonic()

        with patch("config.get_settings", return_value=mock_settings):
            result = reranker.apply_auto_reranking(force=False)

        assert "throttled" in result["reason"]
        assert result["applied"] == 0

    def test_not_throttled_after_interval(self):
        from providers import reranker

        mock_settings = MagicMock()
        mock_settings.provider_reranking_enabled = True
        mock_settings.provider_reranking_min_downloads = 20
        mock_settings.provider_reranking_max_modifier = 50

        # Simulate last run long ago
        reranker._last_rerank_ts = time.monotonic() - reranker._RERANK_INTERVAL_SECS - 1

        with (
            patch("config.get_settings", return_value=mock_settings),
            patch("db.get_db") as mock_db_ctx,
        ):
            mock_db = MagicMock()
            mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

            mock_provider_repo = MagicMock()
            mock_provider_repo.get_all_provider_stats.return_value = []
            mock_scoring_repo = MagicMock()

            with (
                patch(
                    "db.repositories.providers.ProviderRepository", return_value=mock_provider_repo
                ),
                patch("db.repositories.scoring.ScoringRepository", return_value=mock_scoring_repo),
                patch("providers.base.invalidate_scoring_cache"),
            ):
                result = reranker.apply_auto_reranking(force=False)

        assert "throttled" not in result["reason"]

    def test_force_bypasses_throttle(self):
        from providers import reranker

        mock_settings = MagicMock()
        mock_settings.provider_reranking_enabled = True
        mock_settings.provider_reranking_min_downloads = 20
        mock_settings.provider_reranking_max_modifier = 50

        # Simulate last run just now
        reranker._last_rerank_ts = time.monotonic()

        with (
            patch("config.get_settings", return_value=mock_settings),
            patch("db.get_db") as mock_db_ctx,
        ):
            mock_db = MagicMock()
            mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

            mock_provider_repo = MagicMock()
            mock_provider_repo.get_all_provider_stats.return_value = []
            mock_scoring_repo = MagicMock()

            with (
                patch(
                    "db.repositories.providers.ProviderRepository", return_value=mock_provider_repo
                ),
                patch("db.repositories.scoring.ScoringRepository", return_value=mock_scoring_repo),
                patch("providers.base.invalidate_scoring_cache"),
            ):
                result = reranker.apply_auto_reranking(force=True)

        assert "throttled" not in result["reason"]
