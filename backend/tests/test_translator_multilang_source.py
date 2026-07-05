"""Multi-language auto-translate source selection.

Sublarr now translates the missing target FROM whatever source subtitle exists
(any language, per profile preference), instead of only the configured source
language. Covers:
- find_any_source_sub: any-language sidecar detection (excludes target, prefers
  the preferred language, ignores modifier-only names).
- _search_providers_for_source_sub: iterates candidate source languages.
- translate_ass: threads the real source language into the translation direction.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tests.test_translator_core import _make_ass_file, _make_result


def _touch(path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write("x")


# --- find_any_source_sub -----------------------------------------------------


def test_find_any_source_sub_picks_non_target_any_language(tmp_path):
    from translator._helpers import find_any_source_sub

    base = str(tmp_path / "Movie [imdb-tt123]")
    mkv = base + ".mkv"
    _touch(mkv)
    _touch(base + ".ja.srt")  # japanese source (preferred en absent)
    _touch(base + ".de.srt")  # target — must be excluded
    _touch(base + ".forced.srt")  # modifier-only, no language — must be ignored

    settings = MagicMock(target_language="de", source_language="en")
    with patch("translator._helpers.get_settings", return_value=settings):
        path, lang = find_any_source_sub(mkv)

    assert lang == "ja"
    assert path.endswith(".ja.srt")


def test_find_any_source_sub_prefers_preferred_language(tmp_path):
    from translator._helpers import find_any_source_sub

    base = str(tmp_path / "Ep [imdb-tt9]")
    mkv = base + ".mkv"
    _touch(mkv)
    _touch(base + ".ja.srt")
    _touch(base + ".en.srt")

    settings = MagicMock(target_language="de", source_language="en")
    with patch("translator._helpers.get_settings", return_value=settings):
        path, lang = find_any_source_sub(mkv, preferred_language="en")

    assert lang == "en"
    assert path.endswith(".en.srt")


def test_find_any_source_sub_none_when_only_target_or_modifier(tmp_path):
    from translator._helpers import find_any_source_sub

    base = str(tmp_path / "X [imdb-tt1]")
    mkv = base + ".mkv"
    _touch(mkv)
    _touch(base + ".de.srt")  # target
    _touch(base + ".sdh.srt")  # modifier-only

    settings = MagicMock(target_language="de", source_language="en")
    with patch("translator._helpers.get_settings", return_value=settings):
        path, lang = find_any_source_sub(mkv)

    assert path is None
    assert lang is None


# --- provider multi-language search ------------------------------------------


def test_provider_search_iterates_source_languages(tmp_path):
    from translator import providers as prov

    mkv = str(tmp_path / "vid.mkv")

    class _Fmt:
        value = "srt"

    class _Result:
        content = b"x"
        provider_name = "prov"
        score = 88
        format = _Fmt()

    tried: list[list[str]] = []

    def _search(query, format_filter=None):
        tried.append(list(query.languages))
        # Miss on English, hit on Japanese (any-format branch).
        if query.languages == ["ja"] and format_filter is None:
            return _Result()
        return None

    manager = MagicMock()
    manager.search_and_download_best.side_effect = _search
    manager.save_subtitle.side_effect = lambda r, p, series_id=None: p

    settings = MagicMock(source_language="en")
    with (
        patch("providers.get_provider_manager", return_value=manager),
        patch("translator.providers.get_settings", return_value=settings),
        patch("translator.providers._build_video_query", side_effect=lambda *a, **k: MagicMock(languages=[])),
    ):
        path, fmt, score, lang = prov._search_providers_for_source_sub(
            mkv, None, source_languages=["en", "ja"]
        )

    assert lang == "ja"
    assert fmt == "srt"
    assert score == 88
    assert ["en"] in tried and ["ja"] in tried  # preferred tried before fallback


# --- translation direction threading -----------------------------------------


def test_translate_ass_threads_explicit_source_language(tmp_path):
    """translate_ass must translate FROM the passed source_language, not the
    configured default — so a Japanese source is translated ja->de, not en->de."""
    from translator.core import translate_ass

    ass_path = str(tmp_path / "source.ass")
    _make_ass_file(ass_path, ["こんにちは"])

    settings = MagicMock(hi_removal_enabled=False, source_language="en", target_language="de")
    tr_result = _make_result(["Hallo"])

    with (
        patch("translator.core._pkg") as mock_pkg,
        patch("translator.core.get_output_path_for_lang", return_value=str(tmp_path / "source.de.ass")),
        patch("translator.core.check_disk_space"),
        patch("translator.core._write_quality_sidecar"),
        patch("translator.core._compute_quality_stats", return_value={}),
        patch("translator.core._check_translation_quality", return_value=[]),
        patch("nfo_export.maybe_write_nfo"),
    ):
        import shutil

        pkg = MagicMock()
        pkg.extract_subtitle_stream = MagicMock(
            side_effect=lambda mkv, si, out: shutil.copy(ass_path, out)
        )
        pkg.get_settings = MagicMock(return_value=settings)
        pkg._translate_with_manager = MagicMock(return_value=(["Hallo"], tr_result))
        pkg._get_quality_config = MagicMock(return_value=(False, 50, 2))
        mock_pkg.return_value = pkg

        translate_ass(
            "/media/test.mkv",
            {"index": 0, "format": "ass"},
            {},
            target_language="de",
            source_language="ja",
        )

    _, kwargs = pkg._translate_with_manager.call_args
    assert kwargs["source_lang"] == "ja"
