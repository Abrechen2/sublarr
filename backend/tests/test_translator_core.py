"""Tests for translator.core — translate_ass, translate_srt_*, translate_file, Translator."""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pysubs2
import pytest

from translation.base import TranslationResult


def _make_result(lines, backend="ollama"):
    """Create a TranslationResult for test use."""
    return TranslationResult(
        translated_lines=lines,
        backend_name=backend,
        success=True,
    )


def _make_ass_file(path, dialog_lines, styles=None):
    """Create a minimal ASS file for testing."""
    subs = pysubs2.SSAFile()
    if styles is None:
        subs.styles["Default"] = pysubs2.SSAStyle()
    else:
        for s in styles:
            subs.styles[s] = pysubs2.SSAStyle()
    for i, text in enumerate(dialog_lines):
        evt = pysubs2.SSAEvent(
            start=i * 3000,
            end=(i + 1) * 3000,
            text=text,
            style=styles[0] if styles else "Default",
        )
        subs.events.append(evt)
    subs.save(path)


def _make_srt_file(path, dialog_lines):
    """Create a minimal SRT file for testing."""
    content = ""
    for i, line in enumerate(dialog_lines, 1):
        content += (
            f"{i}\n00:00:{(i - 1) * 3 + 1:02d},000 --> 00:00:{(i - 1) * 3 + 3:02d},000\n{line}\n\n"
        )
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ---------------------------------------------------------------------------
# Translator class shim
# ---------------------------------------------------------------------------


class TestTranslatorClass:
    """Tests for the Translator compatibility shim."""

    @patch("translator.core.translate_file")
    def test_delegates_to_module_function(self, mock_tf):
        from translator.core import Translator

        mock_tf.return_value = {"success": True}
        t = Translator()
        result = t.translate_file("/media/test.mkv", target_language="de")

        mock_tf.assert_called_once_with("/media/test.mkv", target_language="de")
        assert result["success"] is True

    @patch("translator.core.translate_file")
    def test_forwards_kwargs(self, mock_tf):
        from translator.core import Translator

        mock_tf.return_value = {"success": True}
        Translator().translate_file("/m.mkv", target_language="fr", force=True)
        mock_tf.assert_called_once_with("/m.mkv", target_language="fr", force=True)


# ---------------------------------------------------------------------------
# translate_ass
# ---------------------------------------------------------------------------


class TestTranslateAss:
    """Tests for translate_ass."""

    def _patch_all(self):
        """Return a dict of common patches for translate_ass tests."""
        settings = MagicMock()
        settings.hi_removal_enabled = False
        settings.source_language = "en"
        settings.target_language = "de"
        return settings

    @patch("translator.core._write_quality_sidecar")
    @patch("translator.core._compute_quality_stats", return_value={})
    @patch("translator.core._check_translation_quality", return_value=[])
    @patch("nfo_export.maybe_write_nfo")
    def test_translate_ass_happy_path(
        self, mock_nfo, mock_quality, mock_stats, mock_sidecar, tmp_path
    ):
        from translator.core import translate_ass

        ass_path = str(tmp_path / "source.ass")
        _make_ass_file(ass_path, ["Hello world", "How are you"])

        settings = self._patch_all()
        tr_result = _make_result(["Hallo Welt", "Wie geht es dir"])

        with (
            patch("translator.core._pkg") as mock_pkg,
            patch("translator.core.get_output_path_for_lang") as mock_out,
            patch("translator.core.check_disk_space"),
        ):
            mock_out.return_value = str(tmp_path / "source.de.ass")
            pkg = MagicMock()
            pkg.extract_subtitle_stream = MagicMock()
            # Make extract just copy the file
            pkg.extract_subtitle_stream.side_effect = lambda mkv, si, out: __import__(
                "shutil"
            ).copy(ass_path, out)
            pkg.get_settings = MagicMock(return_value=settings)
            pkg._translate_with_manager = MagicMock(
                return_value=(["Hallo Welt", "Wie geht es dir"], tr_result)
            )
            pkg._get_quality_config = MagicMock(return_value=(False, 50, 2))
            mock_pkg.return_value = pkg

            result = translate_ass(
                "/media/test.mkv",
                {"index": 0, "format": "ass"},
                {},
                target_language="de",
            )

        assert result["success"] is True
        assert result["stats"]["format"] == "ass"
        assert result["stats"]["translated"] == 2
        assert os.path.exists(result["output_path"])

    @patch("translator.core._pkg")
    @patch("translator.core.get_output_path_for_lang", return_value="/tmp/out.ass")
    @patch("translator.core.check_disk_space")
    def test_translate_ass_no_dialog_lines(self, mock_disk, mock_out, mock_pkg, tmp_path):
        from translator.core import translate_ass

        # ASS file with only empty events
        ass_path = str(tmp_path / "empty.ass")
        subs = pysubs2.SSAFile()
        subs.styles["Default"] = pysubs2.SSAStyle()
        evt = pysubs2.SSAEvent(start=0, end=1000, text="", style="Default")
        subs.events.append(evt)
        subs.save(ass_path)

        pkg = MagicMock()
        pkg.extract_subtitle_stream = MagicMock(
            side_effect=lambda mkv, si, out: __import__("shutil").copy(ass_path, out)
        )
        pkg.get_settings = MagicMock(return_value=MagicMock(hi_removal_enabled=False))
        mock_pkg.return_value = pkg

        result = translate_ass("/m.mkv", {"index": 0}, {})

        assert result["success"] is False
        assert "No dialog lines" in result["error"]

    @patch("translator.core._pkg")
    @patch("translator.core.get_output_path_for_lang", return_value="/tmp/out.ass")
    @patch("translator.core.check_disk_space")
    def test_translate_ass_extraction_error(self, mock_disk, mock_out, mock_pkg):
        from translator.core import translate_ass

        pkg = MagicMock()
        pkg.extract_subtitle_stream = MagicMock(side_effect=RuntimeError("ffmpeg failed"))
        mock_pkg.return_value = pkg

        result = translate_ass("/m.mkv", {"index": 0}, {})

        assert result["success"] is False
        assert "ffmpeg failed" in result["error"]

    @patch("translator.core._write_quality_sidecar")
    @patch("translator.core._compute_quality_stats", return_value={})
    @patch("translator.core._check_translation_quality", return_value=[])
    @patch("nfo_export.maybe_write_nfo")
    def test_translate_ass_count_mismatch(
        self, mock_nfo, mock_quality, mock_stats, mock_sidecar, tmp_path
    ):
        from translator.core import translate_ass

        ass_path = str(tmp_path / "source.ass")
        _make_ass_file(ass_path, ["Hello", "World"])

        settings = MagicMock()
        settings.hi_removal_enabled = False
        settings.source_language = "en"
        settings.target_language = "de"
        # Return only 1 translation for 2 dialog lines
        tr_result = _make_result(["Hallo"])

        with (
            patch("translator.core._pkg") as mock_pkg,
            patch("translator.core.get_output_path_for_lang") as mock_out,
            patch("translator.core.check_disk_space"),
        ):
            mock_out.return_value = str(tmp_path / "source.de.ass")
            pkg = MagicMock()
            pkg.extract_subtitle_stream = MagicMock(
                side_effect=lambda mkv, si, out: __import__("shutil").copy(ass_path, out)
            )
            pkg.get_settings = MagicMock(return_value=settings)
            pkg._translate_with_manager = MagicMock(return_value=(["Hallo"], tr_result))
            pkg._get_quality_config = MagicMock(return_value=(False, 50, 2))
            mock_pkg.return_value = pkg

            result = translate_ass("/m.mkv", {"index": 0}, {}, target_language="de")

        assert result["success"] is False
        assert "mismatch" in result["error"]


# ---------------------------------------------------------------------------
# _translate_srt (via translate_srt_from_file)
# ---------------------------------------------------------------------------


class TestTranslateSrt:
    """Tests for SRT translation functions."""

    @patch("translator.core._write_quality_sidecar")
    @patch("translator.core._compute_quality_stats", return_value={})
    @patch("translator.core._check_translation_quality", return_value=[])
    @patch("translator.core.validate_translation_output", return_value=(True, []))
    @patch("nfo_export.maybe_write_nfo")
    def test_translate_srt_from_file_happy_path(
        self, mock_nfo, mock_validate, mock_quality, mock_stats, mock_sidecar, tmp_path
    ):
        from translator.core import translate_srt_from_file

        srt_path = str(tmp_path / "source.srt")
        _make_srt_file(srt_path, ["Hello", "World"])

        settings = MagicMock()
        settings.hi_removal_enabled = False
        settings.source_language = "en"
        settings.target_language = "de"

        tr_result = _make_result(["Hallo", "Welt"])

        with (
            patch("translator.core._pkg") as mock_pkg,
            patch("translator.core.get_output_path_for_lang") as mock_out,
            patch("translator.core.check_disk_space"),
        ):
            mock_out.return_value = str(tmp_path / "source.de.srt")
            pkg = MagicMock()
            pkg.get_settings = MagicMock(return_value=settings)
            pkg._translate_with_manager = MagicMock(return_value=(["Hallo", "Welt"], tr_result))
            pkg._get_quality_config = MagicMock(return_value=(False, 50, 2))
            mock_pkg.return_value = pkg

            result = translate_srt_from_file("/media/test.mkv", srt_path, target_language="de")

        assert result["success"] is True
        assert result["stats"]["format"] == "srt"
        assert result["stats"]["translated"] == 2

    @patch("translator.core._pkg")
    @patch("translator.core.get_output_path_for_lang", return_value="/tmp/out.srt")
    @patch("translator.core.check_disk_space")
    def test_translate_srt_from_file_exception(self, mock_disk, mock_out, mock_pkg, tmp_path):
        from translator.core import translate_srt_from_file

        # Non-existent SRT file
        result = translate_srt_from_file("/m.mkv", "/nonexistent.srt")

        assert result["success"] is False

    @patch("translator.core._write_quality_sidecar")
    @patch("translator.core._compute_quality_stats", return_value={})
    @patch("translator.core._check_translation_quality", return_value=[])
    @patch("translator.core.validate_translation_output", return_value=(True, []))
    @patch("nfo_export.maybe_write_nfo")
    def test_translate_srt_no_dialog(
        self, mock_nfo, mock_validate, mock_quality, mock_stats, mock_sidecar, tmp_path
    ):
        from translator.core import translate_srt_from_file

        srt_path = str(tmp_path / "empty.srt")
        # SRT with only empty lines
        with open(srt_path, "w") as f:
            f.write("1\n00:00:01,000 --> 00:00:02,000\n\n\n")

        with (
            patch("translator.core._pkg") as mock_pkg,
            patch("translator.core.get_output_path_for_lang") as mock_out,
            patch("translator.core.check_disk_space"),
        ):
            mock_out.return_value = str(tmp_path / "empty.de.srt")
            pkg = MagicMock()
            pkg.get_settings = MagicMock(
                return_value=MagicMock(
                    hi_removal_enabled=False, source_language="en", target_language="de"
                )
            )
            mock_pkg.return_value = pkg

            result = translate_srt_from_file("/m.mkv", srt_path, target_language="de")

        assert result["success"] is False
        assert "No dialog lines" in result["error"]

    @patch("translator.core._write_quality_sidecar")
    @patch("translator.core._compute_quality_stats", return_value={})
    @patch("translator.core._check_translation_quality", return_value=[])
    @patch("translator.core.validate_translation_output", return_value=(True, []))
    @patch("nfo_export.maybe_write_nfo")
    def test_translate_srt_count_mismatch(
        self, mock_nfo, mock_validate, mock_quality, mock_stats, mock_sidecar, tmp_path
    ):
        from translator.core import translate_srt_from_file

        srt_path = str(tmp_path / "source.srt")
        _make_srt_file(srt_path, ["Hello", "World"])

        settings = MagicMock()
        settings.hi_removal_enabled = False
        settings.source_language = "en"
        settings.target_language = "de"

        tr_result = _make_result(["Hallo"])

        with (
            patch("translator.core._pkg") as mock_pkg,
            patch("translator.core.get_output_path_for_lang") as mock_out,
            patch("translator.core.check_disk_space"),
        ):
            mock_out.return_value = str(tmp_path / "source.de.srt")
            pkg = MagicMock()
            pkg.get_settings = MagicMock(return_value=settings)
            # Return only 1 line for 2 source lines
            pkg._translate_with_manager = MagicMock(return_value=(["Hallo"], tr_result))
            pkg._get_quality_config = MagicMock(return_value=(False, 50, 2))
            mock_pkg.return_value = pkg

            result = translate_srt_from_file("/m.mkv", srt_path, target_language="de")

        assert result["success"] is False
        assert "mismatch" in result["error"]


# ---------------------------------------------------------------------------
# translate_srt_from_stream
# ---------------------------------------------------------------------------


class TestTranslateSrtFromStream:
    """Tests for translate_srt_from_stream."""

    @patch("translator.core._translate_srt")
    @patch("translator.core._pkg")
    @patch("translator.core.get_output_path_for_lang", return_value="/tmp/out.srt")
    @patch("translator.core.check_disk_space")
    def test_happy_path(self, mock_disk, mock_out, mock_pkg, mock_translate_srt, tmp_path):
        from translator.core import translate_srt_from_stream

        mock_translate_srt.return_value = {"success": True}
        pkg = MagicMock()
        pkg.extract_subtitle_stream = MagicMock()
        mock_pkg.return_value = pkg

        result = translate_srt_from_stream(
            "/m.mkv", {"index": 2, "format": "srt"}, target_language="de"
        )

        assert result["success"] is True

    @patch("translator.core._pkg")
    @patch("translator.core.get_output_path_for_lang", return_value="/tmp/out.srt")
    @patch("translator.core.check_disk_space")
    def test_extraction_error(self, mock_disk, mock_out, mock_pkg):
        from translator.core import translate_srt_from_stream

        pkg = MagicMock()
        pkg.extract_subtitle_stream = MagicMock(side_effect=RuntimeError("ffmpeg error"))
        mock_pkg.return_value = pkg

        result = translate_srt_from_stream("/m.mkv", {"index": 2}, target_language="de")

        assert result["success"] is False
        assert "ffmpeg error" in result["error"]


# ---------------------------------------------------------------------------
# translate_file — case routing
# ---------------------------------------------------------------------------


class TestTranslateFile:
    """Tests for translate_file case routing."""

    def _setup_pkg(self, mock_pkg, settings=None):
        """Set up common _pkg mock."""
        if settings is None:
            settings = MagicMock()
            settings.target_language = "de"
            settings.target_language_name = "German"
            settings.source_language = "en"
            settings.source_language_name = "English"

        pkg = MagicMock()
        pkg.get_settings = MagicMock(return_value=settings)
        pkg.get_media_streams = MagicMock(return_value={"streams": []})
        pkg.select_best_subtitle_stream = MagicMock(return_value=None)
        mock_pkg.return_value = pkg
        return pkg

    def test_file_not_found_raises(self):
        from translator.core import translate_file

        with pytest.raises(FileNotFoundError):
            translate_file("/nonexistent/video.mkv")

    @patch("translator.core.find_external_source_sub", return_value=None)
    @patch("translator.core._search_providers_for_source_sub", return_value=(None, None, 0))
    @patch("translator.core._search_providers_for_target_ass", return_value=None)
    @patch("translator.core._is_whisper_enabled", return_value=False)
    @patch("translator.core._get_whisper_fallback_min_score", return_value=0)
    @patch("translator.core.detect_existing_target_for_lang", return_value="ass")
    @patch("translator.core._pkg")
    def test_case_a_target_ass_exists(
        self,
        mock_pkg,
        mock_detect,
        mock_score,
        mock_whisper,
        mock_target,
        mock_source,
        mock_ext,
        tmp_path,
    ):
        from translator.core import translate_file

        mkv = str(tmp_path / "test.mkv")
        with open(mkv, "wb") as f:
            f.write(b"\x00")

        self._setup_pkg(mock_pkg)
        result = translate_file(mkv)

        assert result["success"] is True
        assert result["stats"]["skipped"] is True
        assert "already exists" in result["stats"]["reason"]

    @patch("translator.core.find_external_source_sub", return_value=None)
    @patch("translator.core._search_providers_for_source_sub", return_value=(None, None, 0))
    @patch("translator.core._search_providers_for_target_ass", return_value=None)
    @patch("translator.core._is_whisper_enabled", return_value=False)
    @patch("translator.core._get_whisper_fallback_min_score", return_value=0)
    @patch("translator.core.detect_existing_target_for_lang", return_value="srt")
    @patch("translator.core._pkg")
    def test_case_b3_srt_exists_no_upgrade(
        self,
        mock_pkg,
        mock_detect,
        mock_score,
        mock_whisper,
        mock_target,
        mock_source,
        mock_ext,
        tmp_path,
    ):
        from translator.core import translate_file

        mkv = str(tmp_path / "test.mkv")
        with open(mkv, "wb") as f:
            f.write(b"\x00")

        pkg = self._setup_pkg(mock_pkg)
        pkg.select_best_subtitle_stream.return_value = None  # no embedded ASS

        result = translate_file(mkv)

        assert result["success"] is True
        assert result["stats"]["skipped"] is True
        assert "no ass upgrade" in result["stats"]["reason"].lower()

    @patch("translator.core.find_external_source_sub", return_value=None)
    @patch("translator.core._search_providers_for_source_sub", return_value=(None, None, 0))
    @patch("translator.core._search_providers_for_target_ass", return_value=None)
    @patch("translator.core._is_whisper_enabled", return_value=False)
    @patch("translator.core._get_whisper_fallback_min_score", return_value=0)
    @patch("translator.core.detect_existing_target_for_lang", return_value=None)
    @patch("translator.core._pkg")
    def test_case_c4_no_subtitle_found(
        self,
        mock_pkg,
        mock_detect,
        mock_score,
        mock_whisper,
        mock_target,
        mock_source,
        mock_ext,
        tmp_path,
    ):
        from translator.core import translate_file

        mkv = str(tmp_path / "test.mkv")
        with open(mkv, "wb") as f:
            f.write(b"\x00")

        pkg = self._setup_pkg(mock_pkg)
        pkg.select_best_subtitle_stream.return_value = None

        result = translate_file(mkv)

        assert result["success"] is False
        assert "No" in result["error"]

    @patch("translator.jobs._notify_integrations")
    @patch("translator.jobs._record_config_hash_for_result")
    @patch("translator.core.translate_ass")
    @patch("translator.core.find_external_source_sub", return_value=None)
    @patch("translator.core._search_providers_for_source_sub", return_value=(None, None, 0))
    @patch("translator.core._search_providers_for_target_ass", return_value=None)
    @patch("translator.core._is_whisper_enabled", return_value=False)
    @patch("translator.core._get_whisper_fallback_min_score", return_value=0)
    @patch("translator.core.detect_existing_target_for_lang", return_value=None)
    @patch("translator.core._pkg")
    def test_case_c1_embedded_ass(
        self,
        mock_pkg,
        mock_detect,
        mock_score,
        mock_whisper,
        mock_target,
        mock_source,
        mock_ext,
        mock_translate_ass,
        mock_record,
        mock_notify,
        tmp_path,
    ):
        from translator.core import translate_file

        mkv = str(tmp_path / "test.mkv")
        with open(mkv, "wb") as f:
            f.write(b"\x00")

        pkg = self._setup_pkg(mock_pkg)
        pkg.select_best_subtitle_stream.return_value = {"format": "ass", "index": 0}

        mock_translate_ass.return_value = {"success": True, "stats": {}}

        result = translate_file(mkv)

        assert result["success"] is True
        mock_translate_ass.assert_called_once()
        mock_record.assert_called_once()
        mock_notify.assert_called_once()

    @patch("translator.jobs._notify_integrations")
    @patch("translator.jobs._record_config_hash_for_result")
    @patch("translator.core.translate_srt_from_stream")
    @patch("translator.core.find_external_source_sub", return_value=None)
    @patch("translator.core._search_providers_for_source_sub", return_value=(None, None, 0))
    @patch("translator.core._search_providers_for_target_ass", return_value=None)
    @patch("translator.core._is_whisper_enabled", return_value=False)
    @patch("translator.core._get_whisper_fallback_min_score", return_value=0)
    @patch("translator.core.detect_existing_target_for_lang", return_value=None)
    @patch("translator.core._pkg")
    def test_case_c2_embedded_srt(
        self,
        mock_pkg,
        mock_detect,
        mock_score,
        mock_whisper,
        mock_target,
        mock_source,
        mock_ext,
        mock_translate_srt,
        mock_record,
        mock_notify,
        tmp_path,
    ):
        from translator.core import translate_file

        mkv = str(tmp_path / "test.mkv")
        with open(mkv, "wb") as f:
            f.write(b"\x00")

        pkg = self._setup_pkg(mock_pkg)
        pkg.select_best_subtitle_stream.return_value = {"format": "srt", "index": 1}

        mock_translate_srt.return_value = {"success": True, "stats": {}}

        result = translate_file(mkv)

        assert result["success"] is True
        mock_translate_srt.assert_called_once()

    @patch("translator.core._submit_whisper_job")
    @patch("translator.core.find_external_source_sub", return_value=None)
    @patch("translator.core._search_providers_for_source_sub", return_value=(None, None, 0))
    @patch("translator.core._search_providers_for_target_ass", return_value=None)
    @patch("translator.core._is_whisper_enabled", return_value=True)
    @patch("translator.core._get_whisper_fallback_min_score", return_value=0)
    @patch("translator.core.detect_existing_target_for_lang", return_value=None)
    @patch("translator.core._pkg")
    def test_case_d_whisper_fallback(
        self,
        mock_pkg,
        mock_detect,
        mock_score,
        mock_whisper_enabled,
        mock_target,
        mock_source,
        mock_ext,
        mock_submit,
        tmp_path,
    ):
        from translator.core import translate_file

        mkv = str(tmp_path / "test.mkv")
        with open(mkv, "wb") as f:
            f.write(b"\x00")

        pkg = self._setup_pkg(mock_pkg)
        pkg.select_best_subtitle_stream.return_value = None

        mock_submit.return_value = {
            "success": True,
            "status": "whisper_pending",
            "whisper_job_id": "abc123",
        }

        result = translate_file(mkv)

        assert result["status"] == "whisper_pending"
        mock_submit.assert_called_once()

    @patch("translator.core.find_external_source_sub", return_value=None)
    @patch("translator.core._search_providers_for_source_sub", return_value=(None, None, 0))
    @patch("translator.core._search_providers_for_target_ass", return_value=None)
    @patch("translator.core._is_whisper_enabled", return_value=False)
    @patch("translator.core._get_whisper_fallback_min_score", return_value=0)
    @patch("translator.core.detect_existing_target_for_lang", return_value=None)
    @patch("translator.core._pkg")
    def test_force_skips_target_detection(
        self,
        mock_pkg,
        mock_detect,
        mock_score,
        mock_whisper,
        mock_target,
        mock_source,
        mock_ext,
        tmp_path,
    ):
        from translator.core import translate_file

        mkv = str(tmp_path / "test.mkv")
        with open(mkv, "wb") as f:
            f.write(b"\x00")

        pkg = self._setup_pkg(mock_pkg)
        pkg.select_best_subtitle_stream.return_value = None

        translate_file(mkv, force=True)

        # detect_existing_target_for_lang should NOT be called when force=True
        mock_detect.assert_not_called()


# ---------------------------------------------------------------------------
# _translate_external_ass
# ---------------------------------------------------------------------------


class TestTranslateExternalAss:
    """Tests for _translate_external_ass."""

    @patch("translator.core._write_quality_sidecar")
    @patch("translator.core._compute_quality_stats", return_value={})
    @patch("translator.core._check_translation_quality", return_value=[])
    @patch("translator.core.validate_translation_output", return_value=(True, []))
    @patch("nfo_export.maybe_write_nfo")
    def test_happy_path(
        self, mock_nfo, mock_validate, mock_quality, mock_stats, mock_sidecar, tmp_path
    ):
        from translator.core import _translate_external_ass

        ass_path = str(tmp_path / "ext.ass")
        _make_ass_file(ass_path, ["Hello", "World"])

        settings = MagicMock()
        settings.hi_removal_enabled = False
        settings.source_language = "en"
        settings.target_language = "de"

        tr_result = _make_result(["Hallo", "Welt"])

        with (
            patch("translator.core._pkg") as mock_pkg,
            patch("translator.core.get_output_path_for_lang") as mock_out,
            patch("translator.core.check_disk_space"),
        ):
            mock_out.return_value = str(tmp_path / "ext.de.ass")
            pkg = MagicMock()
            pkg.get_settings = MagicMock(return_value=settings)
            pkg._translate_with_manager = MagicMock(return_value=(["Hallo", "Welt"], tr_result))
            pkg._get_quality_config = MagicMock(return_value=(False, 50, 2))
            mock_pkg.return_value = pkg

            result = _translate_external_ass("/m.mkv", ass_path, target_language="de")

        assert result["success"] is True
        assert result["stats"]["source"] == "provider_source_ass"

    @patch("translator.core.get_output_path_for_lang", return_value="/tmp/out.ass")
    @patch("translator.core.check_disk_space")
    def test_nonexistent_file_returns_error(self, mock_disk, mock_out):
        from translator.core import _translate_external_ass

        result = _translate_external_ass("/m.mkv", "/nonexistent.ass")

        assert result["success"] is False
