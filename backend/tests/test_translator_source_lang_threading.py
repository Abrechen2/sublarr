"""The real source language must reach every step, not just the first one.

``translate_ass`` / ``_translate_srt`` take a ``source_language`` override so a
non-English source subtitle is translated from the language it is actually in.
The first translation call honoured it; the steps after it read
``settings.source_language`` — the globally configured source — instead.

On the reference install that global is ``en`` while ``en`` is also a target, so
a ``de -> en`` job asked the model to translate German text under an
``en -> en`` instruction, and the per-line quality retry kept the result when it
scored higher. 13 447 such calls were recorded between 2026-07-16 and
2026-08-28.

The existing coverage missed it because every flow test disables quality
evaluation (``_get_quality_config`` -> ``(False, ...)``), so the retry path was
never executed with an explicit source language.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tests.test_translator_core import _make_ass_file, _make_result


def _pkg_mock(settings, translated, quality=(True, 35, 1)):
    pkg = MagicMock()
    pkg.get_settings = MagicMock(return_value=settings)
    pkg._translate_with_manager = MagicMock(return_value=(translated, _make_result(translated)))
    pkg._get_quality_config = MagicMock(return_value=quality)
    return pkg


def test_ass_quality_retry_gets_the_real_source_language(tmp_path):
    from translator.core import translate_ass

    ass_path = str(tmp_path / "source.ass")
    _make_ass_file(ass_path, ["こんにちは"])
    settings = MagicMock(hi_removal_enabled=False, source_language="en", target_language="de")

    with (
        patch("translator.core._pkg") as mock_pkg,
        patch(
            "translator.core.get_output_path_for_lang", return_value=str(tmp_path / "source.de.ass")
        ),
        patch("translator.core.check_disk_space"),
        patch("translator.core._write_quality_sidecar"),
        patch("translator.core._compute_quality_stats", return_value={}),
        patch("translator.core._check_translation_quality", return_value=[]),
        patch("translator.core._resolve_backend_for_context", return_value=(None, ["ollama"])),
        patch("translator.core._evaluate_and_retry_lines", return_value=(["Hallo"], [90])) as ev,
        patch("nfo_export.maybe_write_nfo"),
    ):
        import shutil

        pkg = _pkg_mock(settings, ["Hallo"])
        pkg.extract_subtitle_stream = MagicMock(
            side_effect=lambda mkv, si, out: shutil.copy(ass_path, out)
        )
        mock_pkg.return_value = pkg

        translate_ass(
            "/media/test.mkv",
            {"index": 0, "format": "ass"},
            {},
            target_language="de",
            source_language="ja",
        )

    assert ev.called, "quality retry never ran — the test would prove nothing"
    src_lang = ev.call_args[0][2]
    assert src_lang == "ja", f"quality retry was told the source is {src_lang!r}, not 'ja'"


def _write_srt(path, lines):
    with open(path, "w", encoding="utf-8") as fh:
        for i, text in enumerate(lines, start=1):
            fh.write(f"{i}\n00:00:0{i},000 --> 00:00:0{i + 1},000\n{text}\n\n")


def test_srt_quality_retry_gets_the_real_source_language(tmp_path):
    from translator.srt_flow import _translate_srt

    srt_path = str(tmp_path / "source.srt")
    _write_srt(srt_path, ["こんにちは"])
    settings = MagicMock(hi_removal_enabled=False, source_language="en", target_language="de")

    with (
        patch("translator.core._pkg") as mock_pkg,
        patch("translator.core._extract_series_id", return_value=None),
        patch("translator.core.validate_translation_output", return_value=(True, [])),
        patch("translator.core._check_translation_quality", return_value=[]),
        patch("translator.core._resolve_backend_for_context", return_value=(None, ["ollama"])),
        patch("translator.core._evaluate_and_retry_lines", return_value=(["Hallo"], [90])) as ev,
        patch("translator.core._compute_quality_stats", return_value={}),
        patch("nfo_export.maybe_write_nfo"),
    ):
        mock_pkg.return_value = _pkg_mock(settings, ["Hallo"])

        _translate_srt(
            srt_path,
            str(tmp_path / "out.de.srt"),
            target_language="de",
            source_language="ja",
        )

    assert ev.called, "quality retry never ran — the test would prove nothing"
    src_lang = ev.call_args[0][2]
    assert src_lang == "ja", f"quality retry was told the source is {src_lang!r}, not 'ja'"


def test_srt_validation_retry_keeps_the_real_source_language(tmp_path):
    """A retry after failed validation must not silently switch source language."""
    from translator.srt_flow import _translate_srt

    srt_path = str(tmp_path / "source.srt")
    _write_srt(srt_path, ["こんにちは"])
    settings = MagicMock(hi_removal_enabled=False, source_language="en", target_language="de")
    pkg = _pkg_mock(settings, ["Hallo"], quality=(False, 35, 1))

    with (
        patch("translator.core._pkg", return_value=pkg),
        patch("translator.core._extract_series_id", return_value=None),
        # first check fails, the retry then succeeds
        patch(
            "translator.core.validate_translation_output",
            side_effect=[(False, ["bad"]), (True, [])],
        ),
        patch("translator.core._check_translation_quality", return_value=[]),
        patch("translator.core._compute_quality_stats", return_value={}),
        patch("nfo_export.maybe_write_nfo"),
    ):
        _translate_srt(
            srt_path,
            str(tmp_path / "out.de.srt"),
            target_language="de",
            source_language="ja",
        )

    langs = [c.kwargs["source_lang"] for c in pkg._translate_with_manager.call_args_list]
    assert langs == ["ja", "ja"], f"retry changed the source language: {langs}"
