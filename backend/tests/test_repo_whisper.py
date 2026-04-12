"""Tests for db.repositories.whisper.WhisperRepository.

Covers: whisper job create/update/get/delete, listing with status filter,
aggregated stats with counts by status and average processing time.
"""

import pytest

from db.repositories.whisper import WhisperRepository


@pytest.fixture
def repo(app_ctx):
    """Create a WhisperRepository instance within app context."""
    return WhisperRepository()


# ---------------------------------------------------------------------------
# Whisper Job CRUD
# ---------------------------------------------------------------------------


class TestWhisperJobCRUD:
    def test_create_whisper_job_returns_dict(self, repo):
        """Creating a whisper job returns a dict with expected keys."""
        result = repo.create_whisper_job(
            job_id="wh_001",
            file_path="/media/episode.mkv",
            language="ja",
            audio_track_index=2,
        )
        assert isinstance(result, dict)
        assert result["id"] == "wh_001"
        assert result["file_path"] == "/media/episode.mkv"
        assert result["language"] == "ja"
        assert result["audio_track_index"] == 2
        assert result["status"] == "queued"
        assert result["progress"] == 0.0

    def test_create_whisper_job_defaults(self, repo):
        """Creating a job with defaults uses empty language and no audio track."""
        result = repo.create_whisper_job(job_id="wh_002", file_path="/media/test.mkv")
        assert result["language"] == ""
        assert result["audio_track_index"] is None

    def test_get_whisper_job_by_id(self, repo):
        """Getting a whisper job by ID returns the correct job."""
        repo.create_whisper_job(job_id="wh_get", file_path="/media/test.mkv")
        result = repo.get_whisper_job("wh_get")
        assert result is not None
        assert result["id"] == "wh_get"
        assert result["file_path"] == "/media/test.mkv"

    def test_get_whisper_job_not_found(self, repo):
        """Getting a non-existent job returns None."""
        assert repo.get_whisper_job("nonexistent") is None

    def test_update_whisper_job_status(self, repo):
        """Updating a whisper job changes its status."""
        repo.create_whisper_job(job_id="wh_upd", file_path="/media/test.mkv")
        repo.update_whisper_job("wh_upd", status="running", progress=0.5)

        job = repo.get_whisper_job("wh_upd")
        assert job["status"] == "running"
        assert job["progress"] == 0.5

    def test_update_whisper_job_completed(self, repo):
        """Updating a job to completed sets all result fields."""
        repo.create_whisper_job(job_id="wh_done", file_path="/media/test.mkv")
        repo.update_whisper_job(
            "wh_done",
            status="completed",
            progress=1.0,
            detected_language="ja",
            language_probability=0.95,
            srt_content="1\n00:00:01,000 --> 00:00:03,000\nHello\n",
            segment_count=1,
            duration_seconds=120.5,
            processing_time_ms=5000.0,
        )

        job = repo.get_whisper_job("wh_done")
        assert job["status"] == "completed"
        assert job["progress"] == 1.0
        assert job["detected_language"] == "ja"
        assert job["language_probability"] == pytest.approx(0.95)
        assert job["segment_count"] == 1
        assert job["duration_seconds"] == pytest.approx(120.5)
        assert job["processing_time_ms"] == pytest.approx(5000.0)

    def test_update_whisper_job_no_kwargs(self, repo):
        """Calling update with no kwargs is a no-op."""
        repo.create_whisper_job(job_id="wh_noop", file_path="/media/test.mkv")
        repo.update_whisper_job("wh_noop")

        job = repo.get_whisper_job("wh_noop")
        assert job["status"] == "queued"

    def test_update_whisper_job_nonexistent(self, repo):
        """Updating a non-existent job does not raise."""
        repo.update_whisper_job("nonexistent", status="failed")

    def test_delete_whisper_job(self, repo):
        """Deleting a whisper job removes it."""
        repo.create_whisper_job(job_id="wh_del", file_path="/media/test.mkv")
        assert repo.delete_whisper_job("wh_del") is True
        assert repo.get_whisper_job("wh_del") is None

    def test_delete_whisper_job_not_found(self, repo):
        """Deleting a non-existent job returns False."""
        assert repo.delete_whisper_job("nonexistent") is False


# ---------------------------------------------------------------------------
# Whisper Job Listing
# ---------------------------------------------------------------------------


class TestWhisperJobListing:
    def test_get_whisper_jobs_all(self, repo):
        """get_whisper_jobs returns all jobs ordered by created_at desc."""
        repo.create_whisper_job(job_id="wh_a", file_path="/media/a.mkv")
        repo.create_whisper_job(job_id="wh_b", file_path="/media/b.mkv")
        repo.create_whisper_job(job_id="wh_c", file_path="/media/c.mkv")

        jobs = repo.get_whisper_jobs()
        assert len(jobs) == 3
        # Most recent first
        assert jobs[0]["id"] == "wh_c"

    def test_get_whisper_jobs_filter_by_status(self, repo):
        """get_whisper_jobs filters by status."""
        repo.create_whisper_job(job_id="wh_q", file_path="/media/q.mkv")
        repo.create_whisper_job(job_id="wh_r", file_path="/media/r.mkv")
        repo.update_whisper_job("wh_r", status="running")

        queued = repo.get_whisper_jobs(status="queued")
        assert len(queued) == 1
        assert queued[0]["id"] == "wh_q"

        running = repo.get_whisper_jobs(status="running")
        assert len(running) == 1
        assert running[0]["id"] == "wh_r"

    def test_get_whisper_jobs_with_limit(self, repo):
        """get_whisper_jobs respects limit parameter."""
        for i in range(10):
            repo.create_whisper_job(job_id=f"wh_{i}", file_path=f"/media/f{i}.mkv")

        jobs = repo.get_whisper_jobs(limit=3)
        assert len(jobs) == 3

    def test_get_whisper_jobs_empty(self, repo):
        """get_whisper_jobs returns empty list when no jobs exist."""
        assert repo.get_whisper_jobs() == []


# ---------------------------------------------------------------------------
# Whisper Stats
# ---------------------------------------------------------------------------


class TestWhisperStats:
    def test_get_whisper_stats_empty(self, repo):
        """Stats with no jobs returns zeroes."""
        stats = repo.get_whisper_stats()
        assert stats["total"] == 0
        assert stats["by_status"] == {}
        assert stats["avg_processing_time_ms"] == 0.0

    def test_get_whisper_stats_counts_by_status(self, repo):
        """Stats correctly count jobs by status."""
        repo.create_whisper_job(job_id="wh_1", file_path="/media/1.mkv")
        repo.create_whisper_job(job_id="wh_2", file_path="/media/2.mkv")
        repo.create_whisper_job(job_id="wh_3", file_path="/media/3.mkv")
        repo.update_whisper_job("wh_2", status="running")
        repo.update_whisper_job("wh_3", status="completed", processing_time_ms=3000.0)

        stats = repo.get_whisper_stats()
        assert stats["total"] == 3
        assert stats["by_status"]["queued"] == 1
        assert stats["by_status"]["running"] == 1
        assert stats["by_status"]["completed"] == 1

    def test_get_whisper_stats_avg_processing_time(self, repo):
        """Stats correctly compute average processing time for completed jobs."""
        repo.create_whisper_job(job_id="wh_a", file_path="/media/a.mkv")
        repo.update_whisper_job("wh_a", status="completed", processing_time_ms=2000.0)

        repo.create_whisper_job(job_id="wh_b", file_path="/media/b.mkv")
        repo.update_whisper_job("wh_b", status="completed", processing_time_ms=4000.0)

        # A queued job should not affect the average
        repo.create_whisper_job(job_id="wh_c", file_path="/media/c.mkv")

        stats = repo.get_whisper_stats()
        assert stats["avg_processing_time_ms"] == pytest.approx(3000.0)

    def test_get_whisper_stats_excludes_zero_processing_time(self, repo):
        """Average processing time excludes completed jobs with 0ms processing time."""
        repo.create_whisper_job(job_id="wh_a", file_path="/media/a.mkv")
        repo.update_whisper_job("wh_a", status="completed", processing_time_ms=0.0)

        repo.create_whisper_job(job_id="wh_b", file_path="/media/b.mkv")
        repo.update_whisper_job("wh_b", status="completed", processing_time_ms=6000.0)

        stats = repo.get_whisper_stats()
        # Only wh_b counts (processing_time > 0)
        assert stats["avg_processing_time_ms"] == pytest.approx(6000.0)

    def test_get_whisper_stats_no_completed_jobs(self, repo):
        """Average processing time is 0.0 when no completed jobs with processing time exist."""
        repo.create_whisper_job(job_id="wh_1", file_path="/media/1.mkv")
        repo.update_whisper_job("wh_1", status="failed", error="Something went wrong")

        stats = repo.get_whisper_stats()
        assert stats["avg_processing_time_ms"] == 0.0
