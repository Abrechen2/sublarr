"""Tests for whisper/queue.py (WhisperQueue unit tests) and routes/whisper.py (HTTP tests)."""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from whisper.queue import WhisperJob, WhisperQueue

# ---------------------------------------------------------------------------
# TestWhisperQueueInit
# ---------------------------------------------------------------------------


class TestWhisperQueueInit:
    """Tests for WhisperQueue initialisation defaults."""

    def test_default_max_concurrent_is_1(self, app_ctx):
        q = WhisperQueue()
        assert q._max_concurrent == 1

    def test_custom_max_concurrent(self, app_ctx):
        q = WhisperQueue(max_concurrent=4)
        assert q._max_concurrent == 4

    def test_starts_with_empty_jobs_dict(self, app_ctx):
        q = WhisperQueue()
        assert q._jobs == {}


# ---------------------------------------------------------------------------
# TestWhisperQueueGetJob
# ---------------------------------------------------------------------------


class TestWhisperQueueGetJob:
    """Tests for get_job() and get_all_jobs()."""

    def test_get_job_returns_none_for_unknown_id(self, app_ctx):
        q = WhisperQueue()
        assert q.get_job("nonexistent-id") is None

    def test_get_all_jobs_returns_empty_list_initially(self, app_ctx):
        q = WhisperQueue()
        assert q.get_all_jobs() == []


# ---------------------------------------------------------------------------
# TestWhisperQueueSubmit
# ---------------------------------------------------------------------------


class TestWhisperQueueSubmit:
    """Tests for submit() — job creation and in-memory tracking."""

    def test_submit_returns_job_id(self, app_ctx):
        q = WhisperQueue()
        mock_manager = MagicMock()

        with (
            patch("db.whisper.create_whisper_job"),
            patch("whisper.queue.create_whisper_job"),
            patch("threading.Thread") as mock_thread_cls,
        ):
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread

            result = q.submit(
                job_id="abc123",
                file_path="/media/test.mkv",
                language="ja",
                source_language="ja",
                whisper_manager=mock_manager,
            )

        assert result == "abc123"

    def test_submitted_job_appears_in_get_job(self, app_ctx):
        q = WhisperQueue()
        mock_manager = MagicMock()

        with (
            patch("whisper.queue.create_whisper_job"),
            patch("threading.Thread") as mock_thread_cls,
        ):
            mock_thread_cls.return_value = MagicMock()
            q.submit(
                job_id="job-xyz",
                file_path="/media/test.mkv",
                language="en",
                source_language="en",
                whisper_manager=mock_manager,
            )

        job = q.get_job("job-xyz")
        assert job is not None

    def test_submitted_job_has_correct_file_path(self, app_ctx):
        q = WhisperQueue()
        mock_manager = MagicMock()

        with (
            patch("whisper.queue.create_whisper_job"),
            patch("threading.Thread") as mock_thread_cls,
        ):
            mock_thread_cls.return_value = MagicMock()
            q.submit(
                job_id="job-fp",
                file_path="/media/anime.mkv",
                language="ja",
                source_language="ja",
                whisper_manager=mock_manager,
            )

        job = q.get_job("job-fp")
        assert job.file_path == "/media/anime.mkv"

    def test_submitted_job_has_correct_language(self, app_ctx):
        q = WhisperQueue()
        mock_manager = MagicMock()

        with (
            patch("whisper.queue.create_whisper_job"),
            patch("threading.Thread") as mock_thread_cls,
        ):
            mock_thread_cls.return_value = MagicMock()
            q.submit(
                job_id="job-lang",
                file_path="/media/anime.mkv",
                language="de",
                source_language="ja",
                whisper_manager=mock_manager,
            )

        job = q.get_job("job-lang")
        assert job.language == "de"

    def test_initial_status_is_queued(self, app_ctx):
        q = WhisperQueue()
        mock_manager = MagicMock()
        valid_statuses = {
            "queued",
            "extracting",
            "transcribing",
            "saving",
            "completed",
            "failed",
            "cancelled",
        }

        with (
            patch("whisper.queue.create_whisper_job"),
            patch("threading.Thread") as mock_thread_cls,
        ):
            mock_thread_cls.return_value = MagicMock()
            q.submit(
                job_id="job-status",
                file_path="/media/anime.mkv",
                language="ja",
                source_language="ja",
                whisper_manager=mock_manager,
            )

        job = q.get_job("job-status")
        assert job.status in valid_statuses


# ---------------------------------------------------------------------------
# TestWhisperQueueCancelJob
# ---------------------------------------------------------------------------


class TestWhisperQueueCancelJob:
    """Tests for cancel_job() with direct job injection into _jobs."""

    def _make_job(self, job_id: str, status: str) -> WhisperJob:
        return WhisperJob(job_id=job_id, file_path="/media/test.mkv", status=status)

    def test_cancel_nonexistent_returns_false(self, app_ctx):
        q = WhisperQueue()
        result = q.cancel_job("does-not-exist")
        assert result is False

    def test_cancel_queued_job_returns_true_and_sets_cancelled(self, app_ctx):
        q = WhisperQueue()
        job = self._make_job("j1", "queued")
        q._jobs["j1"] = job

        with patch("whisper.queue.update_whisper_job"):
            result = q.cancel_job("j1")

        assert result is True
        assert q._jobs["j1"].status == "cancelled"

    def test_cancel_completed_job_returns_false(self, app_ctx):
        q = WhisperQueue()
        job = self._make_job("j2", "completed")
        q._jobs["j2"] = job

        result = q.cancel_job("j2")
        assert result is False

    def test_cancel_failed_job_returns_false(self, app_ctx):
        q = WhisperQueue()
        job = self._make_job("j3", "failed")
        q._jobs["j3"] = job

        result = q.cancel_job("j3")
        assert result is False

    def test_cancel_already_cancelled_returns_false(self, app_ctx):
        q = WhisperQueue()
        job = self._make_job("j4", "cancelled")
        q._jobs["j4"] = job

        result = q.cancel_job("j4")
        assert result is False

    def test_cancel_in_progress_statuses_returns_true(self, app_ctx):
        """Jobs in extracting/transcribing/saving can be marked cancelled (best-effort)."""
        for status in ("extracting", "transcribing", "saving"):
            q = WhisperQueue()
            job = self._make_job(f"j-{status}", status)
            q._jobs[f"j-{status}"] = job

            with patch("whisper.queue.update_whisper_job"):
                result = q.cancel_job(f"j-{status}")

            assert result is True, f"Expected True for status={status}"
            assert q._jobs[f"j-{status}"].status == "cancelled"


# ---------------------------------------------------------------------------
# TestListQueue — GET /api/v1/whisper/queue
# ---------------------------------------------------------------------------


class TestListQueue:
    """HTTP tests for GET /api/v1/whisper/queue."""

    def test_returns_list_of_jobs(self, client):
        fake_jobs = [
            {"job_id": "abc", "status": "completed", "progress": 1.0},
            {"job_id": "def", "status": "queued", "progress": 0.0},
        ]
        with patch("db.whisper.get_whisper_jobs", return_value=fake_jobs):
            resp = client.get("/api/v1/whisper/queue")

        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) == 2

    def test_status_filter_forwarded_to_db(self, client):
        with patch("db.whisper.get_whisper_jobs", return_value=[]) as mock_get:
            resp = client.get("/api/v1/whisper/queue?status=completed")

        assert resp.status_code == 200
        mock_get.assert_called_once_with(status="completed", limit=50)

    def test_limit_param_forwarded(self, client):
        with patch("db.whisper.get_whisper_jobs", return_value=[]) as mock_get:
            resp = client.get("/api/v1/whisper/queue?limit=10")

        assert resp.status_code == 200
        mock_get.assert_called_once_with(status=None, limit=10)

    def test_limit_capped_at_200(self, client):
        with patch("db.whisper.get_whisper_jobs", return_value=[]) as mock_get:
            resp = client.get("/api/v1/whisper/queue?limit=9999")

        assert resp.status_code == 200
        mock_get.assert_called_once_with(status=None, limit=200)

    def test_returns_empty_list_when_no_jobs(self, client):
        with patch("db.whisper.get_whisper_jobs", return_value=[]):
            resp = client.get("/api/v1/whisper/queue")

        assert resp.status_code == 200
        assert resp.get_json() == []


# ---------------------------------------------------------------------------
# TestTranscribeEndpoint — POST /api/v1/whisper/transcribe
# ---------------------------------------------------------------------------


class TestTranscribeEndpoint:
    """HTTP tests for POST /api/v1/whisper/transcribe."""

    def test_missing_file_path_returns_400(self, client):
        resp = client.post(
            "/api/v1/whisper/transcribe",
            json={},
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data

    def test_file_outside_media_path_returns_403(self, client):
        with (
            patch("routes.whisper.is_safe_path", return_value=False),
            patch("config.map_path", return_value="/etc/passwd"),
        ):
            resp = client.post(
                "/api/v1/whisper/transcribe",
                json={"file_path": "/etc/passwd"},
                content_type="application/json",
            )
        assert resp.status_code == 403
        data = resp.get_json()
        assert "error" in data

    def test_nonexistent_file_returns_404(self, client):
        with (
            patch("routes.whisper.is_safe_path", return_value=True),
            patch("config.map_path", return_value="/media/does_not_exist.mkv"),
        ):
            resp = client.post(
                "/api/v1/whisper/transcribe",
                json={"file_path": "/media/does_not_exist.mkv"},
                content_type="application/json",
            )
        assert resp.status_code == 404
        data = resp.get_json()
        assert "error" in data

    def test_valid_file_returns_202_with_job_id(self, client):
        # Create a real temporary file so os.path.exists() passes
        with tempfile.NamedTemporaryFile(
            suffix=".mkv", dir=tempfile.gettempdir(), delete=False
        ) as tmp:
            tmp_path = tmp.name

        try:
            mock_manager = MagicMock()
            mock_queue = MagicMock()
            mock_queue.submit.return_value = "generated-job-id"

            with (
                patch("routes.whisper.is_safe_path", return_value=True),
                patch("config.map_path", return_value=tmp_path),
                patch("whisper.get_whisper_manager", return_value=mock_manager),
                patch("routes.whisper._get_queue", return_value=mock_queue),
            ):
                resp = client.post(
                    "/api/v1/whisper/transcribe",
                    json={"file_path": tmp_path, "language": "ja"},
                    content_type="application/json",
                )
        finally:
            os.unlink(tmp_path)

        assert resp.status_code == 202
        data = resp.get_json()
        assert "job_id" in data
        assert data["status"] == "queued"

    def test_invalid_audio_track_index_returns_400(self, client):
        with tempfile.NamedTemporaryFile(suffix=".mkv", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            with (
                patch("routes.whisper.is_safe_path", return_value=True),
                patch("config.map_path", return_value=tmp_path),
            ):
                resp = client.post(
                    "/api/v1/whisper/transcribe",
                    json={"file_path": tmp_path, "audio_track_index": -1},
                    content_type="application/json",
                )
        finally:
            os.unlink(tmp_path)
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data

    def test_audio_track_index_string_returns_400(self, client):
        with tempfile.NamedTemporaryFile(suffix=".mkv", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            with (
                patch("routes.whisper.is_safe_path", return_value=True),
                patch("config.map_path", return_value=tmp_path),
            ):
                resp = client.post(
                    "/api/v1/whisper/transcribe",
                    json={"file_path": tmp_path, "audio_track_index": "bad"},
                    content_type="application/json",
                )
        finally:
            os.unlink(tmp_path)
        # String type fails the isinstance(audio_track_index, int) check → 400
        assert resp.status_code == 400
