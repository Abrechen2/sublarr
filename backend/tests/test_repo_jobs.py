"""Tests for db.repositories.jobs.JobRepository.

Covers: job CRUD, pagination, status filtering, pending count, old job deletion,
cancel queued, outdated config hash detection, daily stats recording and aggregation.
"""

from datetime import date
from unittest.mock import patch

import pytest

from db.repositories.jobs import JobRepository


@pytest.fixture
def repo(app_ctx):
    """Create a JobRepository instance within app context."""
    return JobRepository()


# ---------------------------------------------------------------------------
# Job CRUD
# ---------------------------------------------------------------------------


class TestJobCRUD:
    def test_create_job_returns_dict(self, repo):
        """Creating a job returns a dict with expected keys."""
        result = repo.create_job("/media/test.ass", force=False)
        assert isinstance(result, dict)
        assert result["file_path"] == "/media/test.ass"
        assert result["status"] == "queued"
        assert result["force"] is False
        assert result["arr_context"] is None
        assert result["completed_at"] is None
        assert result["result"] is None
        assert result["error"] is None
        assert "id" in result
        assert len(result["id"]) == 8

    def test_create_job_with_force(self, repo):
        """Creating a forced job sets force=True."""
        result = repo.create_job("/media/test.ass", force=True)
        assert result["force"] is True

    def test_create_job_with_arr_context(self, repo):
        """Creating a job with arr_context stores it as JSON."""
        context = {"series_id": 1, "episode_id": 5}
        result = repo.create_job("/media/test.ass", arr_context=context)
        assert result["arr_context"] == context

    def test_get_job_by_id(self, repo):
        """Getting a job by ID returns the correct job."""
        created = repo.create_job("/media/test.ass")
        result = repo.get_job(created["id"])
        assert result is not None
        assert result["file_path"] == "/media/test.ass"
        assert result["stats"] == {}
        assert result["arr_context"] is None
        assert result["force"] is False

    def test_get_job_not_found(self, repo):
        """Getting a non-existent job returns None."""
        assert repo.get_job("nonexist") is None

    def test_update_job_completed(self, repo):
        """Updating a job to completed sets status, result, and completed_at."""
        created = repo.create_job("/media/test.ass")
        result_data = {
            "output_path": "/media/test.de.ass",
            "stats": {"format": "ass", "config_hash": "abc123"},
        }
        repo.update_job(created["id"], status="completed", result=result_data)

        job = repo.get_job(created["id"])
        assert job["status"] == "completed"
        assert job["output_path"] == "/media/test.de.ass"
        assert job["completed_at"] is not None
        assert job["stats"]["format"] == "ass"

    def test_update_job_failed(self, repo):
        """Updating a job to failed sets the error and completed_at."""
        created = repo.create_job("/media/test.ass")
        repo.update_job(created["id"], status="failed", error="Something went wrong")

        job = repo.get_job(created["id"])
        assert job["status"] == "failed"
        assert job["error"] == "Something went wrong"
        assert job["completed_at"] is not None

    def test_update_job_running_no_completed_at(self, repo):
        """Updating a job to running does not set completed_at."""
        created = repo.create_job("/media/test.ass")
        repo.update_job(created["id"], status="running")

        job = repo.get_job(created["id"])
        assert job["status"] == "running"
        assert job["completed_at"] is None

    def test_delete_job(self, repo):
        """Deleting a job removes it."""
        created = repo.create_job("/media/test.ass")
        assert repo.delete_job(created["id"]) is True
        assert repo.get_job(created["id"]) is None

    def test_delete_job_not_found(self, repo):
        """Deleting a non-existent job returns False."""
        assert repo.delete_job("nonexist") is False


# ---------------------------------------------------------------------------
# Job Listing and Pagination
# ---------------------------------------------------------------------------


class TestJobListing:
    def test_get_jobs_paginated(self, repo):
        """get_jobs returns paginated results."""
        for i in range(15):
            repo.create_job(f"/media/file_{i}.ass")

        result = repo.get_jobs(page=1, per_page=10)
        assert len(result["data"]) == 10
        assert result["page"] == 1
        assert result["per_page"] == 10
        assert result["total"] == 15
        assert result["total_pages"] == 2

    def test_get_jobs_second_page(self, repo):
        """get_jobs returns the correct second page."""
        for i in range(15):
            repo.create_job(f"/media/file_{i}.ass")

        result = repo.get_jobs(page=2, per_page=10)
        assert len(result["data"]) == 5

    def test_get_jobs_filter_by_status(self, repo):
        """get_jobs filters by status."""
        j1 = repo.create_job("/media/a.ass")
        repo.create_job("/media/b.ass")  # stays queued
        repo.update_job(j1["id"], status="completed", result={"stats": {}, "output_path": ""})

        result = repo.get_jobs(status="completed")
        assert result["total"] == 1
        assert result["data"][0]["status"] == "completed"

    def test_get_jobs_empty(self, repo):
        """get_jobs with no jobs returns empty data."""
        result = repo.get_jobs()
        assert result["data"] == []
        assert result["total"] == 0
        assert result["total_pages"] == 1

    def test_get_recent_jobs(self, repo):
        """get_recent_jobs returns limited recent jobs."""
        for i in range(20):
            repo.create_job(f"/media/file_{i}.ass")

        recent = repo.get_recent_jobs(limit=5)
        assert len(recent) == 5

    def test_get_recent_jobs_default_limit(self, repo):
        """get_recent_jobs uses default limit of 10."""
        for i in range(15):
            repo.create_job(f"/media/file_{i}.ass")

        recent = repo.get_recent_jobs()
        assert len(recent) == 10


# ---------------------------------------------------------------------------
# Job Status Queries
# ---------------------------------------------------------------------------


class TestJobStatusQueries:
    def test_get_pending_job_count(self, repo):
        """get_pending_job_count counts queued and running jobs."""
        repo.create_job("/media/a.ass")  # queued
        repo.create_job("/media/b.ass")  # queued
        j3 = repo.create_job("/media/c.ass")
        repo.update_job(j3["id"], status="running")
        j4 = repo.create_job("/media/d.ass")
        repo.update_job(j4["id"], status="completed", result={"stats": {}, "output_path": ""})

        assert repo.get_pending_job_count() == 3

    def test_get_pending_job_count_zero(self, repo):
        """get_pending_job_count returns 0 when no pending jobs exist."""
        assert repo.get_pending_job_count() == 0

    def test_cancel_queued_jobs(self, repo):
        """cancel_queued_jobs marks all queued jobs as cancelled."""
        repo.create_job("/media/a.ass")
        repo.create_job("/media/b.ass")
        j3 = repo.create_job("/media/c.ass")
        repo.update_job(j3["id"], status="running")

        cancelled = repo.cancel_queued_jobs()
        assert cancelled == 2
        assert repo.get_pending_job_count() == 1  # only the running one

    def test_cancel_queued_jobs_none(self, repo):
        """cancel_queued_jobs returns 0 when no queued jobs exist."""
        assert repo.cancel_queued_jobs() == 0

    def test_delete_old_jobs(self, repo):
        """delete_old_jobs removes jobs older than N days."""
        repo.create_job("/media/recent.ass")
        # Recently created, so nothing should be deleted with 30-day cutoff
        deleted = repo.delete_old_jobs(days=30)
        assert deleted == 0

    def test_get_outdated_jobs_count(self, repo):
        """get_outdated_jobs_count counts jobs with a different config hash."""
        j1 = repo.create_job("/media/a.ass")
        repo.update_job(
            j1["id"],
            status="completed",
            result={"stats": {"config_hash": "old_hash"}, "output_path": "/out"},
        )
        j2 = repo.create_job("/media/b.ass")
        repo.update_job(
            j2["id"],
            status="completed",
            result={"stats": {"config_hash": "current"}, "output_path": "/out"},
        )

        count = repo.get_outdated_jobs_count("current")
        assert count == 1

    def test_get_outdated_jobs(self, repo):
        """get_outdated_jobs returns jobs with a different config hash."""
        j1 = repo.create_job("/media/a.ass")
        repo.update_job(
            j1["id"],
            status="completed",
            result={"stats": {"config_hash": "old"}, "output_path": "/out"},
        )

        outdated = repo.get_outdated_jobs("current")
        assert len(outdated) == 1
        assert outdated[0]["config_hash"] == "old"

    def test_get_outdated_jobs_empty(self, repo):
        """get_outdated_jobs returns empty when all hashes match."""
        j1 = repo.create_job("/media/a.ass")
        repo.update_job(
            j1["id"],
            status="completed",
            result={"stats": {"config_hash": "same"}, "output_path": "/out"},
        )

        assert repo.get_outdated_jobs("same") == []


# ---------------------------------------------------------------------------
# Daily Stats
# ---------------------------------------------------------------------------


class TestDailyStats:
    def test_record_daily_stats_new_day_success(self, repo):
        """Recording a success on a new day creates a stats entry."""
        repo.record_daily_stats(success=True, fmt="ass", source="ollama")

        stats = repo.get_daily_stats(days=1)
        assert len(stats) == 1
        assert stats[0]["translated"] == 1
        assert stats[0]["failed"] == 0

    def test_record_daily_stats_new_day_failure(self, repo):
        """Recording a failure on a new day creates a stats entry."""
        repo.record_daily_stats(success=False)

        stats = repo.get_daily_stats(days=1)
        assert len(stats) == 1
        assert stats[0]["failed"] == 1
        assert stats[0]["translated"] == 0

    def test_record_daily_stats_new_day_skipped(self, repo):
        """Recording a skipped translation creates a stats entry with skipped=1."""
        repo.record_daily_stats(success=True, skipped=True)

        stats = repo.get_daily_stats(days=1)
        assert len(stats) == 1
        assert stats[0]["skipped"] == 1
        assert stats[0]["translated"] == 0

    def test_record_daily_stats_increments_existing(self, repo):
        """Multiple recordings on the same day increment the existing entry."""
        repo.record_daily_stats(success=True, fmt="ass")
        repo.record_daily_stats(success=True, fmt="srt")
        repo.record_daily_stats(success=False)

        stats = repo.get_daily_stats(days=1)
        assert len(stats) == 1
        assert stats[0]["translated"] == 2
        assert stats[0]["failed"] == 1

    def test_get_daily_stats_empty(self, repo):
        """get_daily_stats returns empty list when no stats exist."""
        assert repo.get_daily_stats() == []

    def test_get_stats_summary(self, repo):
        """get_stats_summary aggregates stats over 30 days."""
        repo.record_daily_stats(success=True, fmt="ass", source="ollama")
        repo.record_daily_stats(success=True, fmt="srt", source="deepl")
        repo.record_daily_stats(success=False)
        repo.record_daily_stats(success=True, skipped=True)

        summary = repo.get_stats_summary()
        assert summary["total_translated"] == 2
        assert summary["total_failed"] == 1
        assert summary["total_skipped"] == 1
        assert summary["today_translated"] == 2
        assert "ass" in summary["by_format"]
        assert "srt" in summary["by_format"]
        assert "ollama" in summary["by_source"]
        assert "deepl" in summary["by_source"]
        assert len(summary["daily"]) == 1  # all on same day
        assert "total_subtitles" in summary
        assert "average_score" in summary
        assert "low_score_count" in summary

    def test_get_stats_summary_empty(self, repo):
        """get_stats_summary with no stats returns zeroes."""
        summary = repo.get_stats_summary()
        assert summary["total_translated"] == 0
        assert summary["total_failed"] == 0
        assert summary["today_translated"] == 0
        assert summary["daily"] == []

    def test_get_stats_summary_no_subtitle_data(self, repo):
        """get_stats_summary with no subtitle downloads returns safe defaults."""
        summary = repo.get_stats_summary()
        assert summary["total_subtitles"] == 0
        assert summary["average_score"] is None
        assert summary["low_score_count"] == 0


# ---------------------------------------------------------------------------
# Job Row Conversion
# ---------------------------------------------------------------------------


class TestJobRowConversion:
    def test_row_to_job_force_bool(self, repo):
        """The force field is converted to a boolean."""
        created = repo.create_job("/media/test.ass", force=True)
        job = repo.get_job(created["id"])
        assert job["force"] is True

    def test_row_to_job_parses_context_json(self, repo):
        """arr_context is parsed from JSON string."""
        context = {"key": "value"}
        created = repo.create_job("/media/test.ass", arr_context=context)
        job = repo.get_job(created["id"])
        assert job["arr_context"] == {"key": "value"}

    def test_row_to_job_empty_context(self, repo):
        """Empty context JSON is parsed as None."""
        created = repo.create_job("/media/test.ass")
        job = repo.get_job(created["id"])
        assert job["arr_context"] is None

    def test_row_to_job_parses_stats_json(self, repo):
        """stats_json is parsed into a stats dict."""
        created = repo.create_job("/media/test.ass")
        repo.update_job(
            created["id"],
            status="completed",
            result={"stats": {"lines": 100}, "output_path": "/out"},
        )
        job = repo.get_job(created["id"])
        assert job["stats"]["lines"] == 100
