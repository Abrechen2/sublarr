"""Integration tests for database operations."""

import pytest
from db.jobs import create_job, get_job, get_jobs
from db.wanted import get_wanted_items
from db.blacklist import add_blacklist_entry, get_blacklist_entries
from db.library import get_download_history


class TestJobOperations:
    """Tests for job database operations."""

    def test_create_job(self, temp_db):
        """Test creating a job in database."""
        job_id = create_job(
            job_type="translate",
            file_path="/test/path/file.mkv",
            target_language="de",
        )
        assert job_id is not None
        assert isinstance(job_id, int)

    def test_get_job(self, temp_db):
        """Test retrieving a job from database."""
        job_id = create_job(
            job_type="translate",
            file_path="/test/path/file.mkv",
            target_language="de",
        )
        job = get_job(job_id)
        assert job is not None
        assert job["id"] == job_id
        assert job["job_type"] == "translate"

    def test_get_jobs(self, temp_db):
        """Test retrieving multiple jobs."""
        create_job(job_type="translate", file_path="/test/path1.mkv", target_language="de")
        create_job(job_type="translate", file_path="/test/path2.mkv", target_language="de")
        
        jobs = get_jobs(limit=10)
        assert len(jobs) >= 2


class TestWantedOperations:
    """Tests for wanted items database operations."""

    def test_get_wanted_items(self, temp_db):
        """Test retrieving wanted items."""
        items = get_wanted_items(page=1, per_page=50)
        assert "items" in items
        assert "total" in items
        assert isinstance(items["items"], list)


class TestBlacklistOperations:
    """Tests for blacklist database operations."""

    def test_add_blacklist_entry(self, temp_db):
        """Test adding a blacklist entry."""
        entry_id = add_blacklist_entry(
            provider_name="opensubtitles",
            subtitle_id="12345",
            reason="Test blacklist",
        )
        assert entry_id is not None

    def test_get_blacklist_entries(self, temp_db):
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

    def test_get_download_history(self, temp_db):
        """Test retrieving download history."""
        history = get_download_history(page=1, per_page=50)
        assert "history" in history or "items" in history
        assert isinstance(history.get("history", history.get("items", [])), list)
