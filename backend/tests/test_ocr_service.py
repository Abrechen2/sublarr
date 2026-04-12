"""Tests for services/ocr_extractor.py and routes/ocr.py.

Mocks ffmpeg/pytesseract since they may not be installed in CI.
Covers: extract_frame, extract_frames_sequence, ocr_image,
ocr_subtitle_stream, batch_ocr_track, preview_frame, and OCR routes.
"""

import os
import subprocess
import tempfile
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# extract_frame
# ---------------------------------------------------------------------------


class TestExtractFrame:
    @patch("services.ocr_extractor.subprocess.run")
    def test_file_not_found(self, _mock_run):
        from services.ocr_extractor import extract_frame

        with pytest.raises(RuntimeError, match="not found"):
            extract_frame("/nonexistent/video.mkv", 5.0)

    @patch("services.ocr_extractor.os.path.exists", side_effect=[True, True])
    @patch("services.ocr_extractor.subprocess.run")
    def test_successful_extraction(self, mock_run, _exists):
        from services.ocr_extractor import extract_frame

        mock_run.return_value = MagicMock(returncode=0, stderr="")
        result = extract_frame("/video.mkv", 5.0, "/output.png")
        assert result == "/output.png"

    @patch("services.ocr_extractor.os.path.exists", return_value=True)
    @patch("services.ocr_extractor.subprocess.run")
    def test_ffmpeg_failure(self, mock_run, _exists):
        from services.ocr_extractor import extract_frame

        mock_run.return_value = MagicMock(returncode=1, stderr="error")
        with pytest.raises(RuntimeError, match="FFmpeg frame extraction failed"):
            extract_frame("/video.mkv", 5.0, "/output.png")

    @patch("services.ocr_extractor.os.path.exists", return_value=True)
    @patch(
        "services.ocr_extractor.subprocess.run",
        side_effect=subprocess.TimeoutExpired("ffmpeg", 30),
    )
    def test_ffmpeg_timeout(self, _run, _exists):
        from services.ocr_extractor import extract_frame

        with pytest.raises(RuntimeError, match="timed out"):
            extract_frame("/video.mkv", 5.0, "/output.png")

    @patch("services.ocr_extractor.os.path.exists", return_value=True)
    @patch(
        "services.ocr_extractor.subprocess.run",
        side_effect=FileNotFoundError("ffmpeg"),
    )
    def test_ffmpeg_not_installed(self, _run, _exists):
        from services.ocr_extractor import extract_frame

        with pytest.raises(RuntimeError, match="ffmpeg not found"):
            extract_frame("/video.mkv", 5.0, "/output.png")

    @patch("services.ocr_extractor.os.path.exists", side_effect=[True, False])
    @patch("services.ocr_extractor.subprocess.run")
    def test_no_output_file(self, mock_run, _exists):
        from services.ocr_extractor import extract_frame

        mock_run.return_value = MagicMock(returncode=0, stderr="")
        with pytest.raises(RuntimeError, match="did not produce output"):
            extract_frame("/video.mkv", 5.0, "/output.png")


# ---------------------------------------------------------------------------
# extract_frames_sequence
# ---------------------------------------------------------------------------


class TestExtractFramesSequence:
    @patch("services.ocr_extractor.extract_frame")
    def test_extracts_correct_count(self, mock_extract):
        from services.ocr_extractor import extract_frames_sequence

        mock_extract.side_effect = lambda vp, ts, op: op

        with tempfile.TemporaryDirectory() as td:
            paths = extract_frames_sequence("/video.mkv", 0, 3, interval=1.0, output_dir=td)
            assert len(paths) == 4

    @patch("services.ocr_extractor.extract_frame", side_effect=Exception("fail"))
    def test_failed_frame_skipped(self, _mock):
        from services.ocr_extractor import extract_frames_sequence

        with tempfile.TemporaryDirectory() as td:
            paths = extract_frames_sequence("/video.mkv", 0, 2, interval=1.0, output_dir=td)
            assert paths == []

    @patch("services.ocr_extractor.extract_frame")
    def test_creates_output_dir(self, mock_extract):
        from services.ocr_extractor import extract_frames_sequence

        mock_extract.side_effect = lambda vp, ts, op: op

        with tempfile.TemporaryDirectory() as parent:
            out_dir = os.path.join(parent, "sub", "frames")
            paths = extract_frames_sequence("/video.mkv", 0, 0, interval=1.0, output_dir=out_dir)
            assert len(paths) == 1
            assert os.path.isdir(out_dir)


# ---------------------------------------------------------------------------
# ocr_image (requires pytesseract — test TESSERACT_AVAILABLE=False path)
# ---------------------------------------------------------------------------


class TestOcrImage:
    def test_tesseract_not_available(self):
        import services.ocr_extractor as oe

        original = oe.TESSERACT_AVAILABLE
        oe.TESSERACT_AVAILABLE = False
        try:
            with pytest.raises(RuntimeError, match="pytesseract not available"):
                oe.ocr_image("/frame.png")
        finally:
            oe.TESSERACT_AVAILABLE = original

    def test_image_not_found(self):
        import services.ocr_extractor as oe

        original = oe.TESSERACT_AVAILABLE
        oe.TESSERACT_AVAILABLE = True
        try:
            with pytest.raises(RuntimeError, match="not found"):
                oe.ocr_image("/nonexistent/frame.png")
        finally:
            oe.TESSERACT_AVAILABLE = original


# ---------------------------------------------------------------------------
# ocr_subtitle_stream
# ---------------------------------------------------------------------------


class TestOcrSubtitleStream:
    def test_tesseract_not_available(self):
        import services.ocr_extractor as oe

        original = oe.TESSERACT_AVAILABLE
        oe.TESSERACT_AVAILABLE = False
        try:
            with pytest.raises(RuntimeError, match="pytesseract not available"):
                oe.ocr_subtitle_stream("/video.mkv", 0)
        finally:
            oe.TESSERACT_AVAILABLE = original

    @patch("services.ocr_extractor.extract_frames_sequence", return_value=[])
    def test_no_frames_extracted(self, _frames):
        import services.ocr_extractor as oe

        original = oe.TESSERACT_AVAILABLE
        oe.TESSERACT_AVAILABLE = True
        try:
            with patch("services.audio_visualizer.get_audio_duration", return_value=10.0):
                with pytest.raises(RuntimeError, match="No frames"):
                    oe.ocr_subtitle_stream("/video.mkv", 0)
        finally:
            oe.TESSERACT_AVAILABLE = original

    def test_zero_duration(self):
        import services.ocr_extractor as oe

        original = oe.TESSERACT_AVAILABLE
        oe.TESSERACT_AVAILABLE = True
        try:
            with patch("services.audio_visualizer.get_audio_duration", return_value=0):
                with patch("ass_utils.run_ffprobe", return_value={"format": {"duration": "0"}}):
                    with pytest.raises(RuntimeError, match="Invalid video duration"):
                        oe.ocr_subtitle_stream("/video.mkv", 0)
        finally:
            oe.TESSERACT_AVAILABLE = original


# ---------------------------------------------------------------------------
# batch_ocr_track
# ---------------------------------------------------------------------------


class TestBatchOcrTrack:
    def test_tesseract_not_available(self):
        import services.ocr_extractor as oe

        original = oe.TESSERACT_AVAILABLE
        oe.TESSERACT_AVAILABLE = False
        try:
            with pytest.raises(RuntimeError, match="not available"):
                oe.batch_ocr_track("/video.mkv", 0)
        finally:
            oe.TESSERACT_AVAILABLE = original

    @patch("services.ocr_extractor.subprocess.run")
    def test_ffmpeg_failure(self, mock_run):
        import services.ocr_extractor as oe

        original = oe.TESSERACT_AVAILABLE
        oe.TESSERACT_AVAILABLE = True
        try:
            mock_run.return_value = MagicMock(
                returncode=1, stderr=b"extraction error"
            )
            with pytest.raises(RuntimeError, match="ffmpeg subtitle extraction failed"):
                oe.batch_ocr_track("/video.mkv", 0)
        finally:
            oe.TESSERACT_AVAILABLE = original

    @patch("services.ocr_extractor.subprocess.run")
    def test_no_frames_returns_empty(self, mock_run):
        import services.ocr_extractor as oe

        original = oe.TESSERACT_AVAILABLE
        oe.TESSERACT_AVAILABLE = True
        try:
            mock_run.return_value = MagicMock(returncode=0)
            result = oe.batch_ocr_track("/video.mkv", 0)
            assert result == []
        finally:
            oe.TESSERACT_AVAILABLE = original


# ---------------------------------------------------------------------------
# preview_frame
# ---------------------------------------------------------------------------


class TestPreviewFrame:
    @patch("services.ocr_extractor.extract_frame", return_value="/tmp/frame.png")
    def test_without_tesseract(self, _extract):
        import services.ocr_extractor as oe

        original = oe.TESSERACT_AVAILABLE
        oe.TESSERACT_AVAILABLE = False
        try:
            result = oe.preview_frame("/video.mkv", 5.0)
            assert result["frame_path"] == "/tmp/frame.png"
            assert result["preview_text"] == ""
        finally:
            oe.TESSERACT_AVAILABLE = original


# ---------------------------------------------------------------------------
# OCR Routes
# ---------------------------------------------------------------------------


class TestOcrRoutes:
    def test_extract_no_file_path(self, client):
        resp = client.post("/api/v1/ocr/extract", json={})
        assert resp.status_code == 400
        assert "required" in resp.get_json()["error"]

    def test_extract_file_not_found(self, client):
        media = os.environ.get("SUBLARR_MEDIA_PATH", "/tmp")
        resp = client.post(
            "/api/v1/ocr/extract",
            json={"file_path": os.path.join(media, "nonexistent.mkv")},
        )
        assert resp.status_code == 404

    @patch("routes.ocr.is_safe_path", return_value=False)
    def test_extract_path_traversal(self, _mock, client):
        resp = client.post(
            "/api/v1/ocr/extract",
            json={"file_path": "/etc/passwd"},
        )
        assert resp.status_code == 403

    @patch("routes.ocr.TESSERACT_AVAILABLE", False)
    @patch("routes.ocr.is_safe_path", return_value=True)
    @patch("routes.ocr.os.path.exists", return_value=True)
    def test_extract_no_tesseract(self, _exists, _safe, client):
        resp = client.post(
            "/api/v1/ocr/extract",
            json={"file_path": "/media/video.mkv"},
        )
        assert resp.status_code == 500
        assert "not available" in resp.get_json()["error"]

    def test_preview_no_file_path(self, client):
        resp = client.get("/api/v1/ocr/preview")
        assert resp.status_code == 400

    def test_preview_no_timestamp(self, client):
        resp = client.get("/api/v1/ocr/preview?file_path=/video.mkv")
        assert resp.status_code == 400

    def test_preview_file_not_found(self, client):
        media = os.environ.get("SUBLARR_MEDIA_PATH", "/tmp")
        resp = client.get(
            f"/api/v1/ocr/preview?file_path={media}/nonexistent.mkv&timestamp=5"
        )
        assert resp.status_code == 404

    @patch("routes.ocr.is_safe_path", return_value=False)
    def test_preview_path_traversal(self, _mock, client):
        resp = client.get(
            "/api/v1/ocr/preview?file_path=/etc/passwd&timestamp=5"
        )
        assert resp.status_code == 403

    def test_batch_extract_missing_params(self, client):
        resp = client.post("/api/v1/ocr/batch-extract", json={})
        assert resp.status_code == 400

    def test_batch_extract_file_not_found(self, client):
        media = os.environ.get("SUBLARR_MEDIA_PATH", "/tmp")
        resp = client.post(
            "/api/v1/ocr/batch-extract",
            json={"video_path": os.path.join(media, "nonexistent.mkv"), "stream_index": 0},
        )
        assert resp.status_code == 404

    def test_batch_status_not_found(self, client):
        resp = client.get("/api/v1/ocr/batch-extract/nonexistent-job-id")
        assert resp.status_code == 404
