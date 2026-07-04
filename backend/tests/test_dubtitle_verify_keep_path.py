"""Tests for the dubtitle audio-verify-on-keep helper (wanted_search/dubtitle_verify.py).

Covers the 5 key paths:
  - flag disabled → keep silently, validator never called
  - non-English sidecar → keep silently, validator never called
  - unverifiable result (skipped message) → keep silently
  - confident low-score mismatch → return False (caller keeps + flags)
  - passing score → keep silently
"""

from __future__ import annotations

import types
from unittest.mock import MagicMock, patch

import pytest

from wanted_search.dubtitle_verify import verify_dubtitle_on_keep

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VERIFY_TARGET = "wanted_search.dubtitle_verify.validate_subtitle_against_audio"


def _settings(*, enabled: bool = True) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        dubtitle_verify_on_download=enabled,
        dubtitle_min_score=0.55,
    )


def _vr(*, passed: bool, score: float = 0.0, message: str = "") -> MagicMock:
    """Build a ValidationResult-like object."""
    r = MagicMock()
    r.passed = passed
    r.score = score
    r.message = message
    return r


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestVerifyDubtitleOnKeep:
    def test_flag_disabled_returns_true_no_call(self):
        """When dubtitle_verify_on_download is False, keep silently without calling validator."""
        settings = _settings(enabled=False)
        with patch(_VERIFY_TARGET) as mock_val:
            result = verify_dubtitle_on_keep("/media/ep.en.srt", "/media/ep.mkv", settings)
        assert result is True
        mock_val.assert_not_called()

    def test_non_english_path_returns_true_no_call(self):
        """A .de.srt path with the flag ON is not dub-verifiable — keep silently."""
        settings = _settings(enabled=True)
        with patch(_VERIFY_TARGET) as mock_val:
            result = verify_dubtitle_on_keep("/media/ep.de.srt", "/media/ep.mkv", settings)
        assert result is True
        mock_val.assert_not_called()

    def test_unverifiable_result_returns_true(self):
        """passed=False with a 'validation skipped' message → unverifiable → keep silently."""
        settings = _settings(enabled=True)
        vr = _vr(
            passed=False,
            score=0.0,
            message="Could not sample dub audio — validation skipped.",
        )
        with patch(_VERIFY_TARGET, return_value=vr):
            result = verify_dubtitle_on_keep("/media/ep.en.srt", "/media/ep.mkv", settings)
        assert result is True

    def test_confident_mismatch_returns_false(self):
        """passed=False with a real low-score message → confident mismatch → return False."""
        settings = _settings(enabled=True)
        vr = _vr(
            passed=False,
            score=0.20,
            message="Audio match 0.20 < threshold 0.55. Subtitle may not match the English dub.",
        )
        with patch(_VERIFY_TARGET, return_value=vr):
            result = verify_dubtitle_on_keep("/media/ep.en.srt", "/media/ep.mkv", settings)
        assert result is False

    def test_passing_score_returns_true(self):
        """passed=True → clean keep."""
        settings = _settings(enabled=True)
        vr = _vr(passed=True, score=0.82, message="Audio match 0.82 ≥ threshold 0.55.")
        with patch(_VERIFY_TARGET, return_value=vr):
            result = verify_dubtitle_on_keep("/media/ep.en.srt", "/media/ep.mkv", settings)
        assert result is True
