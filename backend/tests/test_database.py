"""Tests for database.py — SQLite persistence."""

import os
import tempfile
import pytest
from config import reload_settings
from database import get_db, create_job, update_job, get_job, record_stat, get_stats_summary, close_db


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    
    # Override db_path in settings
    os.environ["SUBLARR_DB_PATH"] = db_path
    settings = reload_settings()
    
    yield
    
    # Cleanup
    close_db()
    if os.path.exists(db_path):
        os.unlink(db_path)
    if "SUBLARR_DB_PATH" in os.environ:
        del os.environ["SUBLARR_DB_PATH"]


def test_create_job(temp_db):
    """Test job creation."""
    job = create_job("/test/path.mkv", force=False, arr_context={"series_id": 123})
    assert job["id"] is not None
    assert job["file_path"] == "/test/path.mkv"
    assert job["status"] == "queued"
    assert job["arr_context"]["series_id"] == 123


def test_get_job(temp_db):
    """Test job retrieval."""
    job = create_job("/test/path.mkv")
    job_id = job["id"]
    
    retrieved = get_job(job_id)
    assert retrieved is not None
    assert retrieved["id"] == job_id
    assert retrieved["file_path"] == "/test/path.mkv"


def test_update_job(temp_db):
    """Test job status update."""
    job = create_job("/test/path.mkv")
    job_id = job["id"]
    
    result = {
        "success": True,
        "output_path": "/test/path.de.ass",
        "stats": {"format": "ass", "translated": 100},
    }
    update_job(job_id, "completed", result=result)
    
    updated = get_job(job_id)
    assert updated["status"] == "completed"
    assert updated["output_path"] == "/test/path.de.ass"
    assert updated["stats"]["format"] == "ass"


def test_record_stat(temp_db):
    """Test statistics recording."""
    record_stat(success=True, skipped=False, fmt="ass", source="embedded_ass")
    record_stat(success=True, skipped=False, fmt="srt", source="external_srt")
    record_stat(success=False)
    
    stats = get_stats_summary()
    assert stats["total_translated"] >= 2
    assert stats["total_failed"] >= 1
    assert "ass" in stats["by_format"]
    assert "srt" in stats["by_format"]


def test_get_stats_summary(temp_db):
    """Test stats summary aggregation."""
    # Record some stats
    for _ in range(5):
        record_stat(success=True, skipped=False, fmt="ass")
    for _ in range(2):
        record_stat(success=False)
    
    stats = get_stats_summary()
    assert stats["total_translated"] >= 5
    assert stats["total_failed"] >= 2
    assert stats["by_format"]["ass"] >= 5
