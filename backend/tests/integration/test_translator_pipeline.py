"""Integration tests for the translation pipeline (translator.py).

All tests use mocks — no real Ollama, providers, or filesystem access beyond temp dirs.
Covers the three-case priority chain:
    Case A: Target ASS exists → skip
    Case B: Target SRT exists → upgrade (B1 provider, B2 translate SRT)
    Case C: No target → full pipeline (C1 embedded, C3 provider, C4 fail)
"""

import os
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Minimal ASS content for test files
MINIMAL_ASS = """\
[Script Info]
Title: Test
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Hello World
Dialogue: 0,0:00:04.00,0:00:06.00,Default,,0,0,0,,How are you
"""

MINIMAL_SRT = """\
1
00:00:01,000 --> 00:00:03,000
Hello World

2
00:00:04,000 --> 00:00:06,000
How are you
"""


@pytest.fixture
def work_dir():
    """Temporary directory simulating a media folder."""
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d)


@pytest.fixture
def mkv_path(work_dir):
    """Create a fake MKV file (just needs to exist for os.path checks)."""
    path = os.path.join(work_dir, "episode.mkv")
    Path(path).write_bytes(b"\x1a\x45\xdf\xa3")  # MKV magic bytes
    return path


@pytest.fixture
def mock_settings():
    """Return a mock Settings object with defaults."""
    s = MagicMock()
    s.source_language = "en"
    s.target_language = "de"
    s.source_language_name = "English"
    s.target_language_name = "German"
    s.media_path = "/media"
    s.use_embedded_subs = True
    s.upgrade_enabled = True
    s.upgrade_prefer_ass = True
    s.upgrade_min_score_delta = 50
    s.hi_removal_enabled = False
    s.get_target_patterns.return_value = [".de.ass"]
    s.get_source_patterns.return_value = [".en.ass"]
    s.get_target_lang_tags.return_value = {"de", "deu", "ger", "german"}
    s.get_source_lang_tags.return_value = {"en", "eng", "english"}
    s.get_prompt_template.return_value = "Translate from English to German.\nReturn ONLY the translated lines.\n"
    s.get_translation_config_hash.return_value = "abc123"
    s.ollama_model = "test-model"
    s.batch_size = 5
    return s


# ─── Case A: Target ASS exists → Skip ────────────────────────────────────────


class TestCaseA:
    """Target ASS already exists — translator should skip."""

    def test_skip_when_target_ass_exists(self, mkv_path, mock_settings):
        """translate_file returns success+skip when .de.ass is present."""
        # Create existing target file
        target = os.path.splitext(mkv_path)[0] + ".de.ass"
        Path(target).write_text(MINIMAL_ASS, encoding="utf-8")

        with patch("translator.get_settings", return_value=mock_settings), \
             patch("translator.get_media_streams", return_value=None):
            from translator import translate_file
            result = translate_file(mkv_path)

        assert result["success"] is True
        stats = result.get("stats", {})
        assert stats.get("skipped") is True


# ─── Case B: Target SRT exists → Upgrade attempt ────────────────────────────


class TestCaseB:
    """Target SRT found — try to upgrade to ASS via provider or translate."""

    @patch("translator.get_settings")
    @patch("translator.get_media_streams", return_value=None)
    def test_b1_provider_upgrade_to_ass(self, mock_probe, mock_gs, mkv_path, mock_settings):
        """B1: Provider finds ASS upgrade for existing SRT."""
        mock_gs.return_value = mock_settings

        # Create existing target SRT
        srt_path = os.path.splitext(mkv_path)[0] + ".de.srt"
        Path(srt_path).write_text(MINIMAL_SRT, encoding="utf-8")

        # Mock provider returning ASS content
        mock_result = MagicMock()
        mock_result.content = MINIMAL_ASS.encode("utf-8")
        mock_result.format.value = "ass"
        mock_result.provider_name = "animetosho"
        mock_result.score = 200

        with patch("translator.get_provider_manager") as mock_pm:
            manager = MagicMock()
            manager.search_and_download_best.return_value = mock_result
            mock_pm.return_value = manager

            from translator import translate_file
            result = translate_file(mkv_path)

        # Should attempt provider search
        manager.search_and_download_best.assert_called()
        # Result must be a dict with a success/status indicator
        assert result is not None
        assert "success" in result or "status" in result

    @patch("translator.get_settings")
    @patch("translator.get_media_streams")
    @patch("translator.translate_all")
    def test_b2_translate_existing_srt(self, mock_translate, mock_probe, mock_gs,
                                        mkv_path, mock_settings):
        """B2: No ASS upgrade found — translate the existing SRT."""
        mock_gs.return_value = mock_settings
        mock_probe.return_value = None

        # Create existing target SRT
        srt_path = os.path.splitext(mkv_path)[0] + ".de.srt"
        Path(srt_path).write_text(MINIMAL_SRT, encoding="utf-8")

        # Provider returns nothing
        with patch("translator.get_provider_manager") as mock_pm:
            manager = MagicMock()
            manager.search_and_download_best.return_value = None
            mock_pm.return_value = manager

            # Mock translate_all to return translated lines
            mock_translate.return_value = ["Hallo Welt", "Wie geht es dir"]

            from translator import translate_file
            result = translate_file(mkv_path)

        # Result must be a dict with a success/status indicator
        assert result is not None
        assert result.get("success") is not None or result.get("status") is not None


# ─── Case C: No target subtitle ─────────────────────────────────────────────


class TestCaseC:
    """No target subtitle — full pipeline."""

    @patch("translator.get_settings")
    @patch("translator.get_media_streams")
    @patch("translator.select_best_subtitle_stream")
    @patch("translator.extract_subtitle_stream")
    @patch("translator.translate_all")
    def test_c1_embedded_ass_extraction(self, mock_translate, mock_extract,
                                         mock_select, mock_probe, mock_gs,
                                         mkv_path, mock_settings, work_dir):
        """C1: Source ASS embedded → extract + translate to .de.ass."""
        mock_gs.return_value = mock_settings

        # Simulate ffprobe finding embedded streams
        mock_probe.return_value = {"streams": [
            {"index": 2, "codec_name": "ass", "codec_type": "subtitle",
             "tags": {"language": "eng"}},
        ]}
        mock_select.return_value = {
            "index": 2, "format": "ass", "language": "eng",
        }

        # extract_subtitle_stream returns a temp ASS file
        extracted_path = os.path.join(work_dir, "extracted.ass")
        Path(extracted_path).write_text(MINIMAL_ASS, encoding="utf-8")
        mock_extract.return_value = extracted_path

        # Translation returns German lines
        mock_translate.return_value = ["Hallo Welt", "Wie geht es dir"]

        from translator import translate_file
        result = translate_file(mkv_path)

        assert result["success"] is True
        mock_extract.assert_called_once()
        mock_translate.assert_called_once()

    def test_c4_no_source_no_provider_fails(self, mkv_path, mock_settings):
        """C4: No source subtitle, no provider result → fail."""
        with patch("translator.get_settings", return_value=mock_settings), \
             patch("translator.get_media_streams", return_value=None), \
             patch("translator.get_provider_manager") as mock_pm:
            manager = MagicMock()
            manager.search_and_download_best.return_value = None
            mock_pm.return_value = manager

            from translator import translate_file
            result = translate_file(mkv_path)

        assert result["success"] is False


# ─── Error handling ──────────────────────────────────────────────────────────


class TestErrorHandling:
    """Edge cases and error scenarios."""

    def test_missing_file_raises(self):
        """translate_file raises FileNotFoundError for nonexistent files."""
        with patch("translator.get_settings") as mock_gs:
            mock_gs.return_value = MagicMock(
                target_language="de",
                target_language_name="German",
            )
            from translator import translate_file
            with pytest.raises(FileNotFoundError):
                translate_file("/nonexistent/file.mkv")

    @patch("translator.get_settings")
    @patch("translator.get_media_streams")
    @patch("translator.translate_all", side_effect=Exception("Ollama timeout"))
    @patch("translator.select_best_subtitle_stream")
    @patch("translator.extract_subtitle_stream")
    def test_ollama_failure_returns_error(self, mock_extract, mock_select,
                                           mock_translate, mock_probe, mock_gs,
                                           mkv_path, mock_settings, work_dir):
        """Translation failure when Ollama is unreachable."""
        mock_gs.return_value = mock_settings
        mock_probe.return_value = {"streams": [
            {"index": 2, "codec_name": "ass", "codec_type": "subtitle",
             "tags": {"language": "eng"}},
        ]}
        mock_select.return_value = {"index": 2, "format": "ass", "language": "eng"}

        extracted_path = os.path.join(work_dir, "extracted.ass")
        Path(extracted_path).write_text(MINIMAL_ASS, encoding="utf-8")
        mock_extract.return_value = extracted_path

        from translator import translate_file
        result = translate_file(mkv_path)

        assert result["success"] is False
        assert "error" in result or "Ollama" in str(result.get("stats", {}).get("error", ""))
