"""Tests for remaining uncovered modules.

Covers: services/retranslation.py, services/audio_visualizer.py, openapi.py.
"""

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest


# ===========================================================================
# services/audio_visualizer.py
# ===========================================================================


class TestGetAudioDuration:
    @patch("services.audio_visualizer.subprocess.run")
    def test_successful_duration(self, mock_run):
        from services.audio_visualizer import get_audio_duration

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"format": {"duration": "123.456"}}),
            stderr="",
        )
        duration = get_audio_duration("/audio.wav")
        assert duration == 123.456

    @patch("services.audio_visualizer.subprocess.run")
    def test_ffprobe_failure(self, mock_run):
        from services.audio_visualizer import get_audio_duration

        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        with pytest.raises(RuntimeError, match="FFprobe failed"):
            get_audio_duration("/audio.wav")

    @patch(
        "services.audio_visualizer.subprocess.run",
        side_effect=subprocess.TimeoutExpired("ffprobe", 30),
    )
    def test_ffprobe_timeout(self, _mock):
        from services.audio_visualizer import get_audio_duration

        with pytest.raises(RuntimeError, match="Failed to get audio duration"):
            get_audio_duration("/audio.wav")

    @patch("services.audio_visualizer.subprocess.run")
    def test_invalid_json(self, mock_run):
        from services.audio_visualizer import get_audio_duration

        mock_run.return_value = MagicMock(returncode=0, stdout="not json", stderr="")
        with pytest.raises(RuntimeError, match="Failed to get audio duration"):
            get_audio_duration("/audio.wav")

    @patch("services.audio_visualizer.subprocess.run")
    def test_missing_duration_field(self, mock_run):
        from services.audio_visualizer import get_audio_duration

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"format": {}}),
            stderr="",
        )
        duration = get_audio_duration("/audio.wav")
        assert duration == 0.0


class TestExtractAudioTrack:
    @patch("services.audio_visualizer.subprocess.run")
    def test_file_not_found(self, _mock):
        from services.audio_visualizer import extract_audio_track

        with pytest.raises(RuntimeError, match="not found"):
            extract_audio_track("/nonexistent/video.mkv")

    @patch("services.audio_visualizer.os.path.exists", side_effect=[True, True])
    @patch("services.audio_visualizer.subprocess.run")
    def test_successful_extraction(self, mock_run, _exists):
        from services.audio_visualizer import extract_audio_track

        mock_run.return_value = MagicMock(returncode=0, stderr="")
        result = extract_audio_track("/video.mkv", output_path="/out.wav")
        assert result == "/out.wav"

    @patch("services.audio_visualizer.os.path.exists", return_value=True)
    @patch("services.audio_visualizer.subprocess.run")
    def test_ffmpeg_failure(self, mock_run, _exists):
        from services.audio_visualizer import extract_audio_track

        mock_run.return_value = MagicMock(returncode=1, stderr="conversion error")
        with pytest.raises(RuntimeError, match="FFmpeg audio extraction failed"):
            extract_audio_track("/video.mkv", output_path="/out.wav")

    @patch("services.audio_visualizer.os.path.exists", return_value=True)
    @patch(
        "services.audio_visualizer.subprocess.run",
        side_effect=subprocess.TimeoutExpired("ffmpeg", 300),
    )
    def test_ffmpeg_timeout(self, _run, _exists):
        from services.audio_visualizer import extract_audio_track

        with pytest.raises(RuntimeError, match="timed out"):
            extract_audio_track("/video.mkv", output_path="/out.wav")

    @patch("services.audio_visualizer.os.path.exists", return_value=True)
    @patch(
        "services.audio_visualizer.subprocess.run",
        side_effect=FileNotFoundError("ffmpeg"),
    )
    def test_ffmpeg_not_installed(self, _run, _exists):
        from services.audio_visualizer import extract_audio_track

        with pytest.raises(RuntimeError, match="ffmpeg not found"):
            extract_audio_track("/video.mkv", output_path="/out.wav")

    @patch("services.audio_visualizer.os.path.exists", side_effect=[True, False])
    @patch("services.audio_visualizer.subprocess.run")
    def test_no_output_file(self, mock_run, _exists):
        from services.audio_visualizer import extract_audio_track

        mock_run.return_value = MagicMock(returncode=0, stderr="")
        with pytest.raises(RuntimeError, match="did not produce output"):
            extract_audio_track("/video.mkv", output_path="/out.wav")

    @patch("services.audio_visualizer.os.path.exists", side_effect=[True, True])
    @patch("services.audio_visualizer.subprocess.run")
    def test_audio_track_index(self, mock_run, _exists):
        """Selecting specific audio track adds -map flag."""
        from services.audio_visualizer import extract_audio_track

        mock_run.return_value = MagicMock(returncode=0, stderr="")
        extract_audio_track("/video.mkv", audio_track_index=2, output_path="/out.wav")
        cmd = mock_run.call_args[0][0]
        assert "-map" in cmd
        assert "0:a:2" in cmd


class TestGenerateWaveformSimple:
    @patch("services.audio_visualizer.subprocess.run")
    def test_zero_samples(self, _mock):
        from services.audio_visualizer import _generate_waveform_simple

        result = _generate_waveform_simple("/audio.wav", 10.0, 0)
        assert result == []

    @patch("services.audio_visualizer.subprocess.run")
    def test_fallback_on_subprocess_error(self, mock_run):
        from services.audio_visualizer import _generate_waveform_simple

        mock_run.side_effect = subprocess.TimeoutExpired("ffmpeg", 300)
        result = _generate_waveform_simple("/audio.wav", 10.0, 5)
        assert len(result) == 5
        assert all(d["amplitude"] == 0.5 for d in result)

    @patch("services.audio_visualizer.subprocess.run")
    def test_parses_rms_output(self, mock_run):
        from services.audio_visualizer import _generate_waveform_simple

        stderr = "\n".join(
            [
                "RMS level dB: -30.0 dB",
                "RMS level dB: -20.0 dB",
                "RMS level dB: -10.0 dB",
            ]
        )
        mock_run.return_value = MagicMock(returncode=0, stderr=stderr)
        result = _generate_waveform_simple("/audio.wav", 3.0, 3)
        assert len(result) == 3
        assert abs(result[0]["amplitude"] - 0.5) < 0.01


class TestGenerateWaveformJson:
    @patch("services.audio_visualizer.os.path.exists", return_value=False)
    @patch("services.audio_visualizer.os.unlink")
    @patch("services.audio_visualizer._generate_waveform_simple")
    @patch("services.audio_visualizer.get_audio_duration", return_value=5.0)
    @patch("services.audio_visualizer.extract_audio_track", return_value="/tmp/audio.wav")
    def test_successful_generation(
        self, _extract, _duration, mock_waveform, _unlink, _exists
    ):
        from services.audio_visualizer import generate_waveform_json

        mock_waveform.return_value = [{"time": 0, "amplitude": 0.5}]
        result = generate_waveform_json("/video.mkv")
        assert result["duration"] == 5.0
        assert result["samples"] == 1
        assert len(result["data"]) == 1


# ===========================================================================
# services/retranslation.py
# ===========================================================================


class TestRetranslateItem:
    @patch("db.wanted.get_wanted_item", return_value=None)
    def test_item_not_found(self, _mock, app_ctx):
        from services.retranslation import retranslate_item

        assert retranslate_item(999) is None

    @patch("db.wanted.get_wanted_item")
    def test_file_path_missing(self, mock_get, app_ctx):
        from services.retranslation import retranslate_item

        mock_get.return_value = {"id": 1}
        assert retranslate_item(1) is None

    @patch("services.retranslation.os.path.exists", return_value=False)
    @patch("db.wanted.get_wanted_item")
    def test_file_not_exists(self, mock_get, _exists, app_ctx):
        from services.retranslation import retranslate_item

        mock_get.return_value = {"id": 1, "file_path": "/media/video.mkv"}
        assert retranslate_item(1) is None

    @patch("security_utils.is_safe_path", return_value=False)
    @patch("services.retranslation.os.path.exists", return_value=True)
    @patch("db.wanted.get_wanted_item")
    def test_path_traversal_rejected(self, mock_get, _exists, _safe, app_ctx):
        from services.retranslation import retranslate_item

        mock_get.return_value = {"id": 1, "file_path": "/etc/shadow"}
        assert retranslate_item(1) is None

    @patch("db.wanted.get_wanted_item")
    def test_uses_path_key_fallback(self, mock_get, app_ctx):
        """Falls back to 'path' key if 'file_path' is missing."""
        from services.retranslation import retranslate_item

        mock_get.return_value = {"id": 1, "path": "/nonexistent/video.mkv"}
        assert retranslate_item(1) is None

    @patch("threading.Thread")
    @patch("db.jobs.create_job", return_value={"id": "job-123"})
    @patch("services.retranslation.os.remove")
    @patch("services.retranslation.os.path.exists", return_value=True)
    @patch("security_utils.is_safe_path", return_value=True)
    @patch("db.wanted.get_wanted_item")
    def test_successful_retranslation(
        self, mock_get, _safe, _exists, _remove, mock_job, mock_thread, app_ctx
    ):
        from services.retranslation import retranslate_item

        mock_settings = MagicMock(
            media_path="/media",
            get_target_patterns=lambda fmt: [f".de.{fmt}"],
        )
        mock_get.return_value = {"id": 1, "file_path": "/media/video.mkv"}

        with patch("config.get_settings", return_value=mock_settings):
            result = retranslate_item(1)

        assert result == "job-123"
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()


# ===========================================================================
# openapi.py
# ===========================================================================


class TestOpenApiSpec:
    def test_spec_instance(self):
        from openapi import spec

        assert spec.title == "Sublarr API"
        # openapi_version may be a Version object
        assert str(spec.openapi_version) == "3.0.3"
        assert "apiKeyAuth" in spec.to_dict()["components"]["securitySchemes"]

    def test_register_all_paths(self, app_ctx):
        from openapi import register_all_paths, spec

        register_all_paths(app_ctx)
        api_dict = spec.to_dict()
        assert "info" in api_dict
        assert "openapi" in api_dict

    def test_spec_security_scheme(self):
        from openapi import spec

        schemes = spec.to_dict()["components"]["securitySchemes"]
        assert schemes["apiKeyAuth"]["type"] == "apiKey"
        assert schemes["apiKeyAuth"]["in"] == "header"
        assert schemes["apiKeyAuth"]["name"] == "X-Api-Key"
