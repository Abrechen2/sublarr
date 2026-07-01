"""Tests for translator._helpers — small utility functions."""

import os
import shutil
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# _fail_result / _skip_result
# ---------------------------------------------------------------------------


class TestFailResult:
    """Tests for _fail_result."""

    def test_fail_result_structure(self):
        from translator._helpers import _fail_result

        result = _fail_result("something broke")
        assert result["success"] is False
        assert result["output_path"] is None
        assert result["error"] == "something broke"
        assert result["stats"] == {}

    def test_fail_result_with_empty_error(self):
        from translator._helpers import _fail_result

        result = _fail_result("")
        assert result["success"] is False
        assert result["error"] == ""


class TestSkipResult:
    """Tests for _skip_result."""

    def test_skip_result_without_output(self):
        from translator._helpers import _skip_result

        result = _skip_result("already done")
        assert result["success"] is True
        assert result["output_path"] is None
        assert result["stats"]["skipped"] is True
        assert result["stats"]["reason"] == "already done"
        assert result["error"] is None

    def test_skip_result_with_output_path(self):
        from translator._helpers import _skip_result

        result = _skip_result("upgraded", output_path="/media/test.de.ass")
        assert result["output_path"] == "/media/test.de.ass"
        assert result["stats"]["skipped"] is True


# ---------------------------------------------------------------------------
# _extract_series_id
# ---------------------------------------------------------------------------


class TestExtractSeriesId:
    """Tests for _extract_series_id."""

    def test_none_context(self):
        from translator._helpers import _extract_series_id

        assert _extract_series_id(None) is None

    def test_empty_context(self):
        from translator._helpers import _extract_series_id

        assert _extract_series_id({}) is None

    def test_direct_sonarr_series_id(self):
        from translator._helpers import _extract_series_id

        assert _extract_series_id({"sonarr_series_id": 42}) == 42

    def test_nested_series_id_from_webhook(self):
        from translator._helpers import _extract_series_id

        ctx = {"series": {"id": 99}}
        assert _extract_series_id(ctx) == 99

    def test_series_not_dict(self):
        from translator._helpers import _extract_series_id

        ctx = {"series": "not-a-dict"}
        assert _extract_series_id(ctx) is None

    def test_sonarr_series_id_takes_priority(self):
        from translator._helpers import _extract_series_id

        ctx = {"sonarr_series_id": 1, "series": {"id": 2}}
        assert _extract_series_id(ctx) == 1


# ---------------------------------------------------------------------------
# check_disk_space
# ---------------------------------------------------------------------------


class TestCheckDiskSpace:
    """Tests for check_disk_space."""

    def test_sufficient_space(self, tmp_path):
        from translator._helpers import check_disk_space

        # tmp_path should have plenty of free space
        target = str(tmp_path / "output.ass")
        check_disk_space(target)  # should not raise

    def test_insufficient_space_raises(self, tmp_path):
        from collections import namedtuple

        from translator._helpers import MIN_FREE_SPACE_MB, check_disk_space

        target = str(tmp_path / "output.ass")
        DiskUsage = namedtuple("usage", ["total", "used", "free"])
        fake_usage = DiskUsage(
            total=500 * 1024 * 1024,
            used=499 * 1024 * 1024,
            free=1 * 1024 * 1024,  # 1 MB < MIN_FREE_SPACE_MB
        )
        with (
            patch("shutil.disk_usage", return_value=fake_usage),
            pytest.raises(RuntimeError, match="Insufficient disk space"),
        ):
            check_disk_space(target)


# ---------------------------------------------------------------------------
# find_external_source_sub
# ---------------------------------------------------------------------------


class TestFindExternalSourceSub:
    """Tests for find_external_source_sub."""

    def test_no_external_sub_found(self, tmp_path):
        from translator._helpers import find_external_source_sub

        mkv = str(tmp_path / "video.mkv")
        # Create a dummy MKV so path base exists
        with open(mkv, "w") as f:
            f.write("dummy")

        mock_settings = MagicMock()
        mock_settings.get_source_patterns.return_value = [".en.srt"]
        with patch("translator._helpers.get_settings", return_value=mock_settings):
            result = find_external_source_sub(mkv)
        assert result is None

    def test_external_srt_found(self, tmp_path):
        from translator._helpers import find_external_source_sub

        mkv = str(tmp_path / "video.mkv")
        srt = str(tmp_path / "video.en.srt")
        with open(mkv, "w") as f:
            f.write("dummy")
        with open(srt, "w") as f:
            f.write("1\n00:00:01,000 --> 00:00:02,000\nHello\n")

        mock_settings = MagicMock()
        mock_settings.get_source_patterns.side_effect = lambda fmt: [f".en.{fmt}"]
        with patch("translator._helpers.get_settings", return_value=mock_settings):
            result = find_external_source_sub(mkv)
        assert result == srt


# ---------------------------------------------------------------------------
# _is_whisper_enabled
# ---------------------------------------------------------------------------


class TestIsWhisperEnabled:
    """Tests for _is_whisper_enabled."""

    def test_enabled_true(self):
        from translator._helpers import _is_whisper_enabled

        with patch("db.config.get_config_entry", return_value="true"):
            assert _is_whisper_enabled() is True

    def test_enabled_false(self):
        from translator._helpers import _is_whisper_enabled

        with patch("db.config.get_config_entry", return_value="false"):
            assert _is_whisper_enabled() is False

    def test_enabled_none(self):
        from translator._helpers import _is_whisper_enabled

        with patch("db.config.get_config_entry", return_value=None):
            assert _is_whisper_enabled() is False

    def test_enabled_exception(self):
        from translator._helpers import _is_whisper_enabled

        with patch("db.config.get_config_entry", side_effect=Exception("db error")):
            assert _is_whisper_enabled() is False


# ---------------------------------------------------------------------------
# _get_whisper_fallback_min_score
# ---------------------------------------------------------------------------


class TestGetWhisperFallbackMinScore:
    """Tests for _get_whisper_fallback_min_score."""

    def test_returns_int_value(self):
        from translator._helpers import _get_whisper_fallback_min_score

        with patch("db.config.get_config_entry", return_value="75"):
            assert _get_whisper_fallback_min_score() == 75

    def test_clamps_to_100(self):
        from translator._helpers import _get_whisper_fallback_min_score

        with patch("db.config.get_config_entry", return_value="200"):
            assert _get_whisper_fallback_min_score() == 100

    def test_clamps_to_0(self):
        from translator._helpers import _get_whisper_fallback_min_score

        with patch("db.config.get_config_entry", return_value="-5"):
            assert _get_whisper_fallback_min_score() == 0

    def test_none_returns_0(self):
        from translator._helpers import _get_whisper_fallback_min_score

        with patch("db.config.get_config_entry", return_value=None):
            assert _get_whisper_fallback_min_score() == 0

    def test_exception_returns_0(self):
        from translator._helpers import _get_whisper_fallback_min_score

        with patch("db.config.get_config_entry", side_effect=Exception("db error")):
            assert _get_whisper_fallback_min_score() == 0


# ---------------------------------------------------------------------------
# _get_cache_config
# ---------------------------------------------------------------------------


class TestGetCacheConfig:
    """Tests for _get_cache_config."""

    def test_defaults_when_none(self):
        from translator._helpers import _get_cache_config

        with patch("db.config.get_config_entry", return_value=None):
            enabled, threshold = _get_cache_config()
        assert enabled is True
        assert threshold == 1.0

    def test_disabled(self):
        from translator._helpers import _get_cache_config

        def side_effect(key):
            if key == "translation_memory_enabled":
                return "false"
            return None

        with patch("db.config.get_config_entry", side_effect=side_effect):
            enabled, threshold = _get_cache_config()
        assert enabled is False

    def test_custom_threshold(self):
        from translator._helpers import _get_cache_config

        def side_effect(key):
            if key == "translation_memory_enabled":
                return "true"
            if key == "translation_memory_similarity_threshold":
                return "0.85"
            return None

        with patch("db.config.get_config_entry", side_effect=side_effect):
            enabled, threshold = _get_cache_config()
        assert enabled is True
        assert threshold == pytest.approx(0.85)

    def test_threshold_clamped_to_bounds(self):
        from translator._helpers import _get_cache_config

        def side_effect(key):
            if key == "translation_memory_similarity_threshold":
                return "2.5"
            return None

        with patch("db.config.get_config_entry", side_effect=side_effect):
            _, threshold = _get_cache_config()
        assert threshold == 1.0

    def test_exception_returns_defaults(self):
        from translator._helpers import _get_cache_config

        with patch("db.config.get_config_entry", side_effect=Exception("db down")):
            enabled, threshold = _get_cache_config()
        assert enabled is True
        assert threshold == 1.0


# ---------------------------------------------------------------------------
# _get_quality_config
# ---------------------------------------------------------------------------


class TestGetQualityConfig:
    """Tests for _get_quality_config."""

    def test_defaults_when_none(self):
        from translator._helpers import _get_quality_config

        with patch("db.config.get_config_entry", return_value=None):
            enabled, threshold, max_retries = _get_quality_config()
        assert enabled is True
        assert threshold == 50
        assert max_retries == 2

    def test_disabled(self):
        from translator._helpers import _get_quality_config

        def side_effect(key):
            if key == "translation_quality_enabled":
                return "false"
            return None

        with patch("db.config.get_config_entry", side_effect=side_effect):
            enabled, _, _ = _get_quality_config()
        assert enabled is False

    def test_custom_values(self):
        from translator._helpers import _get_quality_config

        def side_effect(key):
            if key == "translation_quality_enabled":
                return "true"
            if key == "translation_quality_threshold":
                return "70"
            if key == "translation_quality_max_retries":
                return "3"
            return None

        with patch("db.config.get_config_entry", side_effect=side_effect):
            enabled, threshold, max_retries = _get_quality_config()
        assert enabled is True
        assert threshold == 70
        assert max_retries == 3

    def test_threshold_clamped(self):
        from translator._helpers import _get_quality_config

        def side_effect(key):
            if key == "translation_quality_threshold":
                return "150"
            if key == "translation_quality_max_retries":
                return "10"
            return None

        with patch("db.config.get_config_entry", side_effect=side_effect):
            _, threshold, max_retries = _get_quality_config()
        assert threshold == 100
        assert max_retries == 5

    def test_exception_returns_defaults(self):
        from translator._helpers import _get_quality_config

        with patch("db.config.get_config_entry", side_effect=Exception("db down")):
            enabled, threshold, max_retries = _get_quality_config()
        assert enabled is True
        assert threshold == 50
        assert max_retries == 2


# ---------------------------------------------------------------------------
# _resolve_backend_for_context
# ---------------------------------------------------------------------------


class TestResolveBackendForContext:
    """Tests for _resolve_backend_for_context."""

    @patch("db.profiles.get_default_profile")
    @patch("db.profiles.get_series_profile")
    def test_sonarr_series_profile(self, mock_series, mock_default):
        from translator._helpers import _resolve_backend_for_context

        mock_series.return_value = {
            "translation_backend": "deepl",
            "fallback_chain": ["deepl", "ollama"],
        }
        backend, chain = _resolve_backend_for_context({"sonarr_series_id": 5}, "de")
        assert backend == "deepl"
        assert chain == ["deepl", "ollama"]
        mock_series.assert_called_once_with(5)

    @patch("db.profiles.get_default_profile")
    @patch("db.profiles.get_movie_profile")
    def test_radarr_movie_profile(self, mock_movie, mock_default):
        from translator._helpers import _resolve_backend_for_context

        mock_movie.return_value = {
            "translation_backend": "google",
            "fallback_chain": ["google"],
        }
        backend, chain = _resolve_backend_for_context({"radarr_movie_id": 10}, "de")
        assert backend == "google"
        assert chain == ["google"]

    @patch("db.profiles.get_default_profile")
    def test_no_context_uses_default(self, mock_default):
        from translator._helpers import _resolve_backend_for_context

        mock_default.return_value = {
            "translation_backend": "ollama",
            "fallback_chain": ["ollama"],
        }
        backend, chain = _resolve_backend_for_context(None, "de")
        assert backend == "ollama"
        mock_default.assert_called_once()

    @patch("db.profiles.get_default_profile")
    @patch("db.profiles.get_series_profile")
    def test_backend_prepended_to_chain(self, mock_series, mock_default):
        from translator._helpers import _resolve_backend_for_context

        mock_series.return_value = {
            "translation_backend": "deepl",
            "fallback_chain": ["ollama"],  # deepl not in chain
        }
        backend, chain = _resolve_backend_for_context({"sonarr_series_id": 1}, "de")
        assert chain[0] == "deepl"
        assert "ollama" in chain

    @patch("db.profiles.get_default_profile")
    @patch("db.profiles.get_series_profile")
    def test_no_profile_falls_back_to_default(self, mock_series, mock_default):
        from translator._helpers import _resolve_backend_for_context

        mock_series.return_value = None
        mock_default.return_value = {
            "translation_backend": "ollama",
            "fallback_chain": ["ollama"],
        }
        backend, chain = _resolve_backend_for_context({"sonarr_series_id": 1}, "de")
        assert backend == "ollama"
        mock_default.assert_called_once()

    @patch("db.profiles.get_default_profile")
    def test_empty_profile_values_coerce_to_ollama(self, mock_default):
        """Regression: a profile with empty backend + empty chain must not
        yield an empty fallback chain (which made translate_with_fallback fail
        with 'All backends failed. Last error: None'). The prod default
        'Standard' profile shipped exactly this state."""
        from translator._helpers import _resolve_backend_for_context

        mock_default.return_value = {
            "translation_backend": "",
            "fallback_chain": [],
        }
        backend, chain = _resolve_backend_for_context(None, "de")
        assert backend == "ollama"
        assert chain == ["ollama"]

    @patch("db.profiles.get_default_profile")
    def test_falsy_entries_dropped_from_chain(self, mock_default):
        from translator._helpers import _resolve_backend_for_context

        mock_default.return_value = {
            "translation_backend": None,
            "fallback_chain": ["", "ollama", None],
        }
        backend, chain = _resolve_backend_for_context(None, "de")
        assert backend == "ollama"
        assert chain == ["ollama"]
