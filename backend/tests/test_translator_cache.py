"""Tests for translator.cache — translation memory cache functions."""

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# _apply_translation_cache
# ---------------------------------------------------------------------------


class TestApplyTranslationCache:
    """Tests for _apply_translation_cache."""

    @patch("db.translation.lookup_translation_cache")
    def test_all_cache_hits(self, mock_lookup):
        from translator.cache import _apply_translation_cache

        mock_lookup.side_effect = ["Hallo", "Welt"]
        lines = ["Hello", "World"]

        cached, uncached_idx, uncached_lines = _apply_translation_cache(lines, "en", "de", 1.0)

        assert cached == ["Hallo", "Welt"]
        assert uncached_idx == []
        assert uncached_lines == []

    @patch("db.translation.lookup_translation_cache")
    def test_all_cache_misses(self, mock_lookup):
        from translator.cache import _apply_translation_cache

        mock_lookup.return_value = None
        lines = ["Hello", "World"]

        cached, uncached_idx, uncached_lines = _apply_translation_cache(lines, "en", "de", 1.0)

        assert cached == [None, None]
        assert uncached_idx == [0, 1]
        assert uncached_lines == ["Hello", "World"]

    @patch("db.translation.lookup_translation_cache")
    def test_partial_cache_hit(self, mock_lookup):
        from translator.cache import _apply_translation_cache

        mock_lookup.side_effect = ["Hallo", None, "Guten Tag"]
        lines = ["Hello", "World", "Good day"]

        cached, uncached_idx, uncached_lines = _apply_translation_cache(lines, "en", "de", 0.9)

        assert cached == ["Hallo", None, "Guten Tag"]
        assert uncached_idx == [1]
        assert uncached_lines == ["World"]

    @patch("db.translation.lookup_translation_cache")
    def test_cache_lookup_exception_treated_as_miss(self, mock_lookup):
        from translator.cache import _apply_translation_cache

        mock_lookup.side_effect = Exception("db error")
        lines = ["Hello"]

        cached, uncached_idx, uncached_lines = _apply_translation_cache(lines, "en", "de", 1.0)

        assert cached == [None]
        assert uncached_idx == [0]
        assert uncached_lines == ["Hello"]

    @patch("db.translation.lookup_translation_cache")
    def test_empty_lines(self, mock_lookup):
        from translator.cache import _apply_translation_cache

        cached, uncached_idx, uncached_lines = _apply_translation_cache([], "en", "de", 1.0)

        assert cached == []
        assert uncached_idx == []
        assert uncached_lines == []
        mock_lookup.assert_not_called()

    @patch("db.translation.lookup_translation_cache")
    def test_passes_similarity_threshold(self, mock_lookup):
        from translator.cache import _apply_translation_cache

        mock_lookup.return_value = None
        _apply_translation_cache(["Hello"], "en", "de", 0.75)

        mock_lookup.assert_called_once_with("en", "de", "Hello", 0.75)


# ---------------------------------------------------------------------------
# _store_translations_in_cache
# ---------------------------------------------------------------------------


class TestStoreTranslationsInCache:
    """Tests for _store_translations_in_cache."""

    @patch("db.translation.store_translation_cache")
    def test_stores_all_pairs(self, mock_store):
        from translator.cache import _store_translations_in_cache

        src = ["Hello", "World"]
        tgt = ["Hallo", "Welt"]
        _store_translations_in_cache(src, tgt, "en", "de")

        assert mock_store.call_count == 2
        mock_store.assert_any_call("en", "de", "Hello", "Hallo")
        mock_store.assert_any_call("en", "de", "World", "Welt")

    @patch("db.translation.store_translation_cache")
    def test_store_exception_silently_ignored(self, mock_store):
        from translator.cache import _store_translations_in_cache

        mock_store.side_effect = Exception("db write error")
        # Should not raise
        _store_translations_in_cache(["Hello"], ["Hallo"], "en", "de")

    @patch("db.translation.store_translation_cache")
    def test_empty_lists(self, mock_store):
        from translator.cache import _store_translations_in_cache

        _store_translations_in_cache([], [], "en", "de")
        mock_store.assert_not_called()

    @patch("db.translation.store_translation_cache")
    def test_partial_failure_continues(self, mock_store):
        from translator.cache import _store_translations_in_cache

        # First call fails, second succeeds
        mock_store.side_effect = [Exception("fail"), None]
        _store_translations_in_cache(["A", "B"], ["X", "Y"], "en", "de")

        assert mock_store.call_count == 2

    @patch("db.translation.store_translation_cache")
    def test_single_pair(self, mock_store):
        from translator.cache import _store_translations_in_cache

        _store_translations_in_cache(["Hi"], ["Hallo"], "ja", "de")
        mock_store.assert_called_once_with("ja", "de", "Hi", "Hallo")
