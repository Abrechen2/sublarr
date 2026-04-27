"""Tests for translator.manager — translation orchestration with cache and batching."""

from unittest.mock import MagicMock, patch

import pytest

from translation.base import TranslationResult


def _make_result(lines, backend="ollama", success=True, error=None):
    """Create a TranslationResult for test use."""
    return TranslationResult(
        translated_lines=lines,
        backend_name=backend,
        success=success,
        error=error,
    )


# ---------------------------------------------------------------------------
# _translate_with_manager
# ---------------------------------------------------------------------------


class TestTranslateWithManager:
    """Tests for _translate_with_manager."""

    @patch("translator.manager._translate_in_batches")
    @patch("translator.manager._load_glossary_entries", return_value=None)
    @patch("translator.manager._get_cache_config", return_value=(False, 1.0))
    @patch("translator.manager._resolve_backend_for_context", return_value=("ollama", ["ollama"]))
    @patch("translator.manager.get_translation_manager")
    def test_basic_translation_no_cache(
        self, mock_mgr_fn, mock_resolve, mock_cache_cfg, mock_glossary, mock_batch
    ):
        from translator.manager import _translate_with_manager

        result = _make_result(["Hallo", "Welt"])
        mock_batch.return_value = (["Hallo", "Welt"], result)

        mock_settings = MagicMock()
        mock_settings.batch_size = 15
        with patch("translator.manager._pkg") as mock_pkg:
            mock_pkg.return_value.get_settings = MagicMock(return_value=mock_settings)

            output, tr = _translate_with_manager(["Hello", "World"], "en", "de")

        assert output == ["Hallo", "Welt"]
        assert tr.backend_name == "ollama"

    @patch("translator.manager._store_translations_in_cache")
    @patch("translator.manager._translate_in_batches")
    @patch("translator.manager._load_glossary_entries", return_value=None)
    @patch("translator.manager._apply_translation_cache")
    @patch("translator.manager._get_cache_config", return_value=(True, 0.9))
    @patch("translator.manager._resolve_backend_for_context", return_value=("ollama", ["ollama"]))
    @patch("translator.manager.get_translation_manager")
    def test_partial_cache_hit(
        self,
        mock_mgr_fn,
        mock_resolve,
        mock_cache_cfg,
        mock_apply_cache,
        mock_glossary,
        mock_batch,
        mock_store_cache,
    ):
        from translator.manager import _translate_with_manager

        # Line 0 cached, line 1 uncached
        mock_apply_cache.return_value = (["Hallo", None], [1], ["World"])
        result = _make_result(["Welt"])
        mock_batch.return_value = (["Welt"], result)

        mock_settings = MagicMock()
        mock_settings.batch_size = 15
        with patch("translator.manager._pkg") as mock_pkg:
            mock_pkg.return_value.get_settings = MagicMock(return_value=mock_settings)

            output, tr = _translate_with_manager(["Hello", "World"], "en", "de")

        assert output == ["Hallo", "Welt"]
        mock_store_cache.assert_called_once_with(["World"], ["Welt"], "en", "de", backend="ollama")

    @patch("translator.manager._load_glossary_entries", return_value=None)
    @patch("translator.manager._apply_translation_cache")
    @patch("translator.manager._get_cache_config", return_value=(True, 1.0))
    @patch("translator.manager._resolve_backend_for_context", return_value=("tm", ["tm"]))
    @patch("translator.manager.get_translation_manager")
    def test_all_lines_from_cache(
        self, mock_mgr_fn, mock_resolve, mock_cache_cfg, mock_apply_cache, mock_glossary
    ):
        from translator.manager import _translate_with_manager

        mock_apply_cache.return_value = (["Hallo", "Welt"], [], [])

        output, tr = _translate_with_manager(["Hello", "World"], "en", "de")

        assert output == ["Hallo", "Welt"]
        assert tr.backend_name == "translation_memory"
        assert tr.success is True


# ---------------------------------------------------------------------------
# _load_glossary_entries
# ---------------------------------------------------------------------------


class TestLoadGlossaryEntries:
    """Tests for _load_glossary_entries."""

    def test_glossary_disabled(self):
        from translator.manager import _load_glossary_entries

        mock_settings = MagicMock()
        mock_settings.glossary_enabled = False
        with patch("translator.manager._pkg") as mock_pkg:
            mock_pkg.return_value.get_settings = MagicMock(return_value=mock_settings)
            result = _load_glossary_entries(None)
        assert result is None

    @patch("db.translation.get_merged_glossary_for_series")
    def test_series_glossary_loaded(self, mock_get_glossary):
        from translator.manager import _load_glossary_entries

        mock_get_glossary.return_value = [
            {"source_term": "nakama", "target_term": "Kamerad"},
        ]
        mock_settings = MagicMock()
        mock_settings.glossary_enabled = True
        mock_settings.glossary_max_terms = 100
        with patch("translator.manager._pkg") as mock_pkg:
            mock_pkg.return_value.get_settings = MagicMock(return_value=mock_settings)
            result = _load_glossary_entries(series_id=42)

        assert len(result) == 1
        assert result[0]["source_term"] == "nakama"

    @patch("db.translation.get_global_glossary")
    def test_global_glossary_loaded_when_no_series(self, mock_get_global):
        from translator.manager import _load_glossary_entries

        mock_get_global.return_value = [
            {"source_term": "sensei", "target_term": "Lehrer"},
        ]
        mock_settings = MagicMock()
        mock_settings.glossary_enabled = True
        mock_settings.glossary_max_terms = 100
        with patch("translator.manager._pkg") as mock_pkg:
            mock_pkg.return_value.get_settings = MagicMock(return_value=mock_settings)
            result = _load_glossary_entries(series_id=None)

        assert len(result) == 1
        assert result[0]["source_term"] == "sensei"

    @patch("db.translation.get_merged_glossary_for_series")
    def test_glossary_truncated_to_max_terms(self, mock_get_glossary):
        from translator.manager import _load_glossary_entries

        mock_get_glossary.return_value = [
            {"source_term": f"t{i}", "target_term": f"T{i}"} for i in range(50)
        ]
        mock_settings = MagicMock()
        mock_settings.glossary_enabled = True
        mock_settings.glossary_max_terms = 10
        with patch("translator.manager._pkg") as mock_pkg:
            mock_pkg.return_value.get_settings = MagicMock(return_value=mock_settings)
            result = _load_glossary_entries(series_id=1)

        assert len(result) == 10

    def test_glossary_exception_returns_none(self):
        from translator.manager import _load_glossary_entries

        mock_settings = MagicMock()
        mock_settings.glossary_enabled = True
        with patch("translator.manager._pkg") as mock_pkg:
            mock_pkg.return_value.get_settings = MagicMock(return_value=mock_settings)
            with patch(
                "db.translation.get_merged_glossary_for_series",
                side_effect=Exception("db error"),
            ):
                result = _load_glossary_entries(series_id=5)
        assert result is None

    @patch("db.translation.get_merged_glossary_for_series")
    def test_empty_glossary_returns_none(self, mock_get_glossary):
        from translator.manager import _load_glossary_entries

        mock_get_glossary.return_value = []
        mock_settings = MagicMock()
        mock_settings.glossary_enabled = True
        mock_settings.glossary_max_terms = 100
        with patch("translator.manager._pkg") as mock_pkg:
            mock_pkg.return_value.get_settings = MagicMock(return_value=mock_settings)
            result = _load_glossary_entries(series_id=1)
        assert result is None


# ---------------------------------------------------------------------------
# _translate_in_batches
# ---------------------------------------------------------------------------


class TestTranslateInBatches:
    """Tests for _translate_in_batches."""

    def test_single_batch(self):
        from translator.manager import _translate_in_batches

        manager = MagicMock()
        result = _make_result(["Hallo", "Welt"])
        manager.translate_with_fallback.return_value = result

        lines = ["Hello", "World"]
        translated, tr = _translate_in_batches(
            manager, lines, "en", "de", ["ollama"], None, batch_size=10
        )

        assert translated == ["Hallo", "Welt"]
        assert tr is result

    def test_multiple_batches(self):
        from translator.manager import _translate_in_batches

        manager = MagicMock()

        # Two batches: ["A","B"] and ["C"]
        result1 = _make_result(["X", "Y"])
        result2 = _make_result(["Z"])
        manager.translate_with_fallback.side_effect = [result1, result2]

        translated, tr = _translate_in_batches(
            manager, ["A", "B", "C"], "en", "de", ["ollama"], None, batch_size=2
        )

        assert translated == ["X", "Y", "Z"]
        assert manager.translate_with_fallback.call_count == 2

    def test_batch_failure_raises(self):
        from translator.manager import _translate_in_batches

        manager = MagicMock()
        fail_result = _make_result([], success=False, error="timeout")
        manager.translate_with_fallback.return_value = fail_result

        with pytest.raises(RuntimeError, match="Translation failed"):
            _translate_in_batches(manager, ["Hello"], "en", "de", ["ollama"], None, batch_size=10)

    def test_chunk_count_mismatch_raises(self):
        from translator.manager import _translate_in_batches

        manager = MagicMock()
        # Return 1 line for a 2-line chunk
        bad_result = _make_result(["only-one"])
        manager.translate_with_fallback.return_value = bad_result

        with pytest.raises(RuntimeError, match="Chunk translation returned"):
            _translate_in_batches(
                manager, ["A", "B", "C"], "en", "de", ["ollama"], None, batch_size=2
            )

    def test_glossary_forwarded(self):
        from translator.manager import _translate_in_batches

        manager = MagicMock()
        result = _make_result(["X"])
        manager.translate_with_fallback.return_value = result

        glossary = [{"source_term": "senpai", "target_term": "Senpai"}]
        _translate_in_batches(manager, ["A"], "ja", "de", ["ollama"], glossary, batch_size=10)

        call_args = manager.translate_with_fallback.call_args
        assert call_args[0][4] == glossary  # 5th positional arg
