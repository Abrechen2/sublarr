"""Plan B7 — SyncJobRun ORM sanity test."""

from datetime import UTC, datetime


def test_sync_job_run_has_expected_columns():
    from db.models.core import SyncJobRun

    attrs = {
        "id",
        "engine",
        "offset_ms",
        "status",
        "duration_ms",
        "subtitle_path",
        "video_path",
        "reason",
        "created_at",
    }
    for attr in attrs:
        assert hasattr(SyncJobRun, attr), f"missing {attr}"


def test_sync_job_run_instantiation():
    from db.models.core import SyncJobRun

    row = SyncJobRun(
        engine="ffsubsync",
        status="ok",
        offset_ms=120,
        duration_ms=2500,
        subtitle_path="/m/s.srt",
        video_path="/m/v.mkv",
        reason=None,
        created_at=datetime.now(UTC),
    )
    assert row.engine == "ffsubsync"
    assert row.status == "ok"
    assert row.offset_ms == 120
    assert row.duration_ms == 2500
    assert row.reason is None
