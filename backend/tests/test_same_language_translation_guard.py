"""Same-language translation must never happen — anywhere in the pipeline.

Prod 2026-08-30/31: wanted items whose target language equals the configured
source language ("en" items on an en-source install) fell through Step 1
(direct target search) into Steps 2/4, which downloaded an English "source"
subtitle and pushed it through the LLM as an en→en "translation". Result:
1326 same-language translation events, 1221 poisoned translation-memory
rows, and LLM-mangled .en.ass files recorded as machine_translation
downloads (e.g. Railway Heroes, wanted item satisfied by a round-tripped
copy of a subtitle it already had).

Three layers now prevent this:

1. Steps 2/4 skip outright when the item's target IS the source language.
2. ``_translate_with_manager`` refuses any same-language request loudly.
3. ``translate_file`` never treats an embedded stream in the target
   language as a translation source (extraction owns that stream).
"""

from unittest.mock import MagicMock, patch

import pytest


def _step_ctx(item_lang: str, source_language: str) -> dict:
    """Minimal ctx for the Step 2/4 functions up to the provider search."""
    settings = MagicMock()
    settings.source_language = source_language
    manager = MagicMock()
    # A search that returns nothing makes the step return None right after
    # the call — the tests only care whether the search happened at all.
    manager.search_and_download_best.return_value = None
    return {
        "item": {"id": 7, "sonarr_series_id": None},
        "item_id": 7,
        "item_lang": item_lang,
        "settings": settings,
        "manager": manager,
        "_pf": {"must_contain": None, "must_not_contain": None},
        "file_path": "/media/show/episode.mkv",
        "source_query": MagicMock(),
    }


class TestStepGuards:
    def test_step2_skips_en_item_on_en_source_install(self):
        from wanted_search.process import _try_source_ass_translation

        ctx = _step_ctx(item_lang="en", source_language="en")
        assert _try_source_ass_translation(ctx) is None
        ctx["manager"].search_and_download_best.assert_not_called()

    def test_step4_skips_en_item_on_en_source_install(self):
        from wanted_search.process import _try_source_srt_translation

        ctx = _step_ctx(item_lang="en", source_language="en")
        assert _try_source_srt_translation(ctx) is None
        ctx["manager"].search_and_download_best.assert_not_called()

    def test_guard_normalizes_language_tags(self):
        # 'eng' and 'en' are the same language wearing different tags —
        # exactly the mix that exists on disk after the 1.13.x renaming.
        from wanted_search.process import _try_source_ass_translation

        ctx = _step_ctx(item_lang="eng", source_language="en")
        assert _try_source_ass_translation(ctx) is None
        ctx["manager"].search_and_download_best.assert_not_called()

    def test_step2_still_searches_when_there_is_a_real_language_gap(self):
        from wanted_search.process import _try_source_ass_translation

        ctx = _step_ctx(item_lang="de", source_language="en")
        with patch("decision_log.set_step"):
            assert _try_source_ass_translation(ctx) is None
        ctx["manager"].search_and_download_best.assert_called_once()

    def test_step4_still_searches_when_there_is_a_real_language_gap(self):
        from wanted_search.process import _try_source_srt_translation

        ctx = _step_ctx(item_lang="de", source_language="en")
        with patch("decision_log.set_step"):
            assert _try_source_srt_translation(ctx) is None
        ctx["manager"].search_and_download_best.assert_called_once()


class TestManagerGuard:
    """Defense in depth: any caller that still asks gets a loud refusal."""

    def test_manager_refuses_same_language(self):
        from translator.manager import _translate_with_manager

        with pytest.raises(ValueError, match="same-language"):
            _translate_with_manager(["Step aside!"], "en", "en")

    def test_manager_refuses_same_language_across_tag_variants(self):
        from translator.manager import _translate_with_manager

        with pytest.raises(ValueError, match="same-language"):
            _translate_with_manager(["Step aside!"], "eng", "en")

    def test_manager_accepts_a_real_direction(self):
        # Must get PAST the guard — failing later (no backends in a bare
        # test process) is fine, raising ValueError is not.
        from translator.manager import _translate_with_manager

        try:
            _translate_with_manager(["Hello"], "en", "de")
        except ValueError as exc:  # pragma: no cover - guard misfire
            pytest.fail(f"guard rejected a legitimate direction: {exc}")
        except Exception:
            pass  # backend/app-context failures are expected here


class TestEmbeddedStreamGuard:
    """translate_file must not use a target-language embedded stream as source."""

    @patch("translator.core.detect_existing_target_for_lang", return_value=None)
    @patch("translator.core._pkg")
    def test_case_c1_skips_embedded_stream_in_target_language(
        self, mock_pkg, _mock_detect, tmp_path
    ):
        from translator.core import translate_file

        media = tmp_path / "movie.mkv"
        media.write_bytes(b"x")

        settings = MagicMock()
        settings.target_language = "en"
        settings.target_language_name = "English"
        settings.source_language = "en"
        settings.auto_translate_any_source = True
        settings.auto_translate_provider_multilang = False
        settings.auto_translate_source_languages = ["en"]
        settings.whisper_enabled = False

        pkg = MagicMock()
        pkg.get_settings = MagicMock(return_value=settings)
        pkg.get_media_streams = MagicMock(return_value={"subtitle_streams": []})
        # An embedded English ASS stream — for an English target this is
        # extraction material, never a translation source.
        pkg.select_best_subtitle_stream = MagicMock(
            return_value={"index": 0, "format": "ass", "language": "eng"}
        )
        mock_pkg.return_value = pkg

        with (
            patch("translator.core.translate_ass") as mock_translate_ass,
            patch("translator.core.translate_srt_from_stream") as mock_translate_srt,
            patch("translator.core.find_any_source_sub", return_value=(None, None)),
            patch(
                "translator.core._search_providers_for_source_sub",
                return_value=(None, None, 0, None),
            ),
            patch("translator.core._is_whisper_enabled", return_value=False),
        ):
            translate_file(str(media), target_language="en")

        mock_translate_ass.assert_not_called()
        mock_translate_srt.assert_not_called()
