"""Integration tests for database operations."""

import pytest
from db.jobs import create_job, get_job, get_jobs
from db.wanted import get_wanted_items
from db.blacklist import add_blacklist_entry, get_blacklist_entries
from db.library import get_download_history


class TestJobOperations:
    """Tests for job database operations."""

    def test_create_job(self, app_ctx):
        """Test creating a job in database."""
        result = create_job(file_path="/test/path/file.mkv")
        assert result is not None
        assert "id" in result

    def test_get_job(self, app_ctx):
        """Test retrieving a job from database."""
        result = create_job(file_path="/test/path/file.mkv")
        job = get_job(result["id"])
        assert job is not None
        assert job["id"] == result["id"]
        assert job["file_path"] == "/test/path/file.mkv"

    def test_get_jobs(self, app_ctx):
        """Test retrieving multiple jobs."""
        create_job(file_path="/test/path1.mkv")
        create_job(file_path="/test/path2.mkv")

        jobs = get_jobs(per_page=10)
        assert isinstance(jobs, dict)
        assert "data" in jobs or "jobs" in jobs


class TestWantedOperations:
    """Tests for wanted items database operations."""

    def test_get_wanted_items(self, app_ctx):
        """Test retrieving wanted items."""
        items = get_wanted_items(page=1, per_page=50)
        assert "total" in items
        data_key = next((k for k in ("data", "items") if k in items), None)
        assert data_key is not None, f"Expected 'data' or 'items' key, got: {list(items.keys())}"
        assert isinstance(items[data_key], list)


class TestBlacklistOperations:
    """Tests for blacklist database operations."""

    def test_add_blacklist_entry(self, app_ctx):
        """Test adding a blacklist entry."""
        entry_id = add_blacklist_entry(
            provider_name="opensubtitles",
            subtitle_id="12345",
            reason="Test blacklist",
        )
        assert entry_id is not None

    def test_get_blacklist_entries(self, app_ctx):
        """Test retrieving blacklist entries."""
        add_blacklist_entry(
            provider_name="opensubtitles",
            subtitle_id="12345",
            reason="Test",
        )
        entries = get_blacklist_entries(page=1, per_page=50)
        assert "items" in entries or "data" in entries
        assert len(entries.get("items", entries.get("data", []))) >= 1


class TestHistoryOperations:
    """Tests for download history database operations."""

    def test_get_download_history(self, app_ctx):
        """Test retrieving download history."""
        history = get_download_history(page=1, per_page=50)
        data_key = next((k for k in ("data", "history", "items") if k in history), None)
        assert data_key is not None, f"Expected 'data', 'history', or 'items' key, got: {list(history.keys())}"
        assert isinstance(history[data_key], list)
