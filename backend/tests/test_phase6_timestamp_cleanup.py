"""Phase 6 — Timestamp cleanup regression tests.

Verifies:
1. SubtitleHealthResult.checked_at accepts datetime objects (not strings)
2. QualityRepository.save_health_result accepts datetime objects
3. QualityRepository trend query uses datetime comparison, not string comparison
4. whisper/queue.py passes datetime objects to update_whisper_job
"""
import pytest
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch, call
from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped


# ── Test 1: Model column type ─────────────────────────────────────────────────

def test_subtitle_health_result_checked_at_is_datetime_column():
    """SubtitleHealthResult.checked_at must be DateTime(timezone=True), not Text."""
    from db.models.quality import SubtitleHealthResult
    col = SubtitleHealthResult.__table__.c["checked_at"]
    assert isinstance(col.type, DateTime), (
        f"checked_at column type is {type(col.type).__name__}, expected DateTime. "
        "Run the migration and update db/models/quality.py."
    )
    assert col.type.timezone is True, "checked_at must be DateTime(timezone=True)"


# ── Test 2: Repository accepts datetime, not string ───────────────────────────

def test_quality_repo_save_accepts_datetime(app_ctx):
    """save_health_result must accept datetime objects, not ISO strings."""
    from db.repositories.quality import QualityRepository

    repo = QualityRepository()
    now = datetime.now(UTC)
    result = repo.save_health_result(
        file_path="/fake/test.srt",
        score=95,
        issues_json="[]",
        checks_run=3,
        checked_at=now,  # datetime object, not string
    )
    # Result dict should contain an ISO string (via _to_dict serialization)
    assert isinstance(result["checked_at"], str), (
        "save_health_result should return checked_at as ISO string via _to_dict"
    )
    # Verify the string is parseable and close to now
    parsed = datetime.fromisoformat(result["checked_at"])
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    assert abs((parsed - now).total_seconds()) < 5


# ── Test 3: Trend query uses datetime comparison ──────────────────────────────

def test_quality_trend_query_does_not_isoformat(app_ctx):
    """get_quality_trends must NOT use .isoformat() in the WHERE clause.

    Verifies the source code of QualityRepository does not call .isoformat()
    for the trend WHERE comparison — it should pass a datetime object instead.
    """
    import inspect
    from db.repositories.quality import QualityRepository

    source = inspect.getsource(QualityRepository.get_quality_trends)
    # The WHERE comparison must NOT use .isoformat()
    assert ".isoformat()" not in source, (
        "get_quality_trends still calls .isoformat() for the WHERE cutoff comparison. "
        "Remove .isoformat() so a datetime object is passed instead of an ISO string."
    )


# ── Test 4: Whisper queue passes datetime to update_whisper_job ───────────────

def test_whisper_queue_passes_datetime_to_update(monkeypatch):
    """WhisperQueue._run_job must pass datetime objects, not isoformat strings,
    when calling update_whisper_job for completed_at."""
    from whisper.queue import WhisperQueue, WhisperJob
    from datetime import UTC, datetime

    queue = WhisperQueue()
    job_id = "test-abc"

    job = WhisperJob(job_id=job_id, file_path="/fake/video.mkv", language="de")
    queue._jobs[job_id] = job

    all_kwargs: list[dict] = []

    def fake_update_whisper_job(jid, **kwargs):
        all_kwargs.append(dict(kwargs))

    with patch("whisper.queue.update_whisper_job", fake_update_whisper_job):
        with patch("whisper.queue.create_whisper_job"):
            with patch("whisper.queue.select_audio_track", side_effect=RuntimeError("no audio")):
                with patch("whisper.queue.get_audio_track_by_index", side_effect=RuntimeError("no audio")):
                    whisper_mgr = MagicMock()
                    queue._run_job(
                        job_id=job_id,
                        file_path="/fake/video.mkv",
                        language="de",
                        source_language="ja",
                        audio_track_index=None,
                        whisper_manager=whisper_mgr,
                        socketio=None,
                    )

    # At least one call to update_whisper_job should have happened (the failure path)
    calls_with_completed_at = [kw for kw in all_kwargs if "completed_at" in kw]
    assert calls_with_completed_at, (
        "update_whisper_job was never called with completed_at. "
        "Check whisper/queue.py error handling path."
    )
    for kw in calls_with_completed_at:
        val = kw["completed_at"]
        assert isinstance(val, datetime), (
            f"update_whisper_job received completed_at={val!r} (type {type(val).__name__}), "
            "expected a datetime object. Remove .isoformat() calls in whisper/queue.py."
        )


# ── Test 5: WhisperJob dataclass field types ──────────────────────────────────

def test_whisper_job_dataclass_accepts_datetime_timestamps():
    """WhisperJob dataclass fields created_at/started_at/completed_at
    must accept datetime objects (not be typed as str)."""
    from whisper.queue import WhisperJob
    import dataclasses

    fields = {f.name: f for f in dataclasses.fields(WhisperJob)}
    for field_name in ("created_at", "started_at", "completed_at"):
        assert field_name in fields, f"WhisperJob missing field {field_name}"
        field = fields[field_name]
        annotation = WhisperJob.__annotations__.get(field_name, "")
        assert "str" not in str(annotation) or "None" in str(annotation), (
            f"WhisperJob.{field_name} is typed as '{annotation}'. "
            "Should be 'datetime | None' after the fix."
        )
