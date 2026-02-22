"""Tests for backend/routes/video_sync.py and backend/services/video_sync.py."""

from unittest.mock import patch, MagicMock


# ─── Engine endpoint ─────────────────────────────────────────────────────────

def test_get_engines_returns_dict(client):
    """GET /engines returns a JSON object with engine availability."""
    with patch("services.video_sync.get_available_engines",
               return_value={"ffsubsync": False, "alass": False}):
        resp = client.get("/api/v1/tools/video-sync/engines")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "ffsubsync" in data
    assert "alass" in data


# ─── Validation ──────────────────────────────────────────────────────────────

def test_start_sync_missing_file_path(client):
    """POST without file_path returns 400."""
    resp = client.post("/api/v1/tools/video-sync", json={"video_path": "/v.mkv"})
    assert resp.status_code == 400
    assert "file_path" in resp.get_json()["error"]


def test_start_sync_nonexistent_subtitle(client):
    """POST with non-existent subtitle file returns 404."""
    resp = client.post("/api/v1/tools/video-sync", json={
        "file_path": "/nonexistent.srt",
        "video_path": "/v.mkv",
        "engine": "ffsubsync",
    })
    assert resp.status_code == 404


def test_start_sync_ffsubsync_missing_video_path(client, tmp_path):
    """ffsubsync without video_path returns 400."""
    sub = tmp_path / "ep.de.srt"
    sub.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")
    resp = client.post("/api/v1/tools/video-sync", json={
        "file_path": str(sub),
        "engine": "ffsubsync",
    })
    assert resp.status_code == 400
    assert "video_path" in resp.get_json()["error"]


def test_start_sync_alass_missing_reference(client, tmp_path):
    """alass without reference_path or reference_track_index returns 400."""
    sub = tmp_path / "ep.de.srt"
    sub.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")
    resp = client.post("/api/v1/tools/video-sync", json={
        "file_path": str(sub),
        "engine": "alass",
    })
    assert resp.status_code == 400


def test_start_sync_unknown_engine(client, tmp_path):
    """Unknown engine returns 400."""
    sub = tmp_path / "ep.de.srt"
    sub.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")
    resp = client.post("/api/v1/tools/video-sync", json={
        "file_path": str(sub),
        "engine": "imaginary-engine",
    })
    assert resp.status_code == 400


# ─── Job creation ────────────────────────────────────────────────────────────

def test_start_sync_queues_job(client, tmp_path):
    """Valid request queues a background job and returns 202 with job_id."""
    sub = tmp_path / "ep.de.srt"
    sub.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")
    with patch("routes.video_sync._executor") as mock_exec:
        resp = client.post("/api/v1/tools/video-sync", json={
            "file_path": str(sub),
            "video_path": "/media/ep.mkv",
            "engine": "ffsubsync",
        })
    assert resp.status_code == 202
    data = resp.get_json()
    assert "job_id" in data
    assert len(data["job_id"]) == 36  # UUID format
    mock_exec.submit.assert_called_once()


def test_start_sync_alass_with_reference_path(client, tmp_path):
    """alass with explicit reference_path queues a job."""
    sub = tmp_path / "ep.de.srt"
    ref = tmp_path / "ep.jpn.srt"
    sub.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")
    ref.write_text("1\n00:00:01,200 --> 00:00:02,200\nHello ref\n", encoding="utf-8")
    with patch("routes.video_sync._executor") as mock_exec:
        resp = client.post("/api/v1/tools/video-sync", json={
            "file_path": str(sub),
            "engine": "alass",
            "reference_path": str(ref),
        })
    assert resp.status_code == 202
    mock_exec.submit.assert_called_once()


# ─── Status ──────────────────────────────────────────────────────────────────

def test_sync_status_not_found(client):
    """GET status for unknown job_id returns 404."""
    resp = client.get("/api/v1/tools/video-sync/nonexistent-uuid-1234")
    assert resp.status_code == 404
    assert "error" in resp.get_json()


def test_sync_status_reflects_queued_state(client, tmp_path):
    """Status endpoint returns 'queued' right after job creation."""
    sub = tmp_path / "ep.de.srt"
    sub.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")
    with patch("routes.video_sync._executor"):
        resp = client.post("/api/v1/tools/video-sync", json={
            "file_path": str(sub),
            "video_path": "/media/ep.mkv",
            "engine": "ffsubsync",
        })
    job_id = resp.get_json()["job_id"]

    status_resp = client.get(f"/api/v1/tools/video-sync/{job_id}")
    assert status_resp.status_code == 200
    data = status_resp.get_json()
    assert data["job_id"] == job_id
    assert data["status"] == "queued"


# ─── Service unit tests ───────────────────────────────────────────────────────

def test_sync_unavailable_error_when_ffsubsync_missing(tmp_path):
    """sync_with_ffsubsync raises SyncUnavailableError when not installed."""
    from services.video_sync import sync_with_ffsubsync, SyncUnavailableError
    sub = tmp_path / "ep.srt"
    sub.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")
    with patch("services.video_sync.FFSUBSYNC_AVAILABLE", False):
        try:
            sync_with_ffsubsync(str(sub), "/video.mkv")
            assert False, "Expected SyncUnavailableError"
        except SyncUnavailableError:
            pass


def test_sync_unavailable_error_when_alass_missing(tmp_path):
    """sync_with_alass raises SyncUnavailableError when not installed."""
    from services.video_sync import sync_with_alass, SyncUnavailableError
    sub = tmp_path / "ep.srt"
    sub.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")
    with patch("services.video_sync.ALASS_AVAILABLE", False):
        try:
            sync_with_alass(str(sub), "/ref.srt")
            assert False, "Expected SyncUnavailableError"
        except SyncUnavailableError:
            pass


def test_parse_ffsubsync_shift():
    """_parse_ffsubsync_shift extracts ms from ffsubsync output."""
    from services.video_sync import _parse_ffsubsync_shift
    assert _parse_ffsubsync_shift("offset: 1.234 s applied") == 1234
    assert _parse_ffsubsync_shift("no offset info") == 0
    assert _parse_ffsubsync_shift("Offset: -0.5 s") == -500


def test_get_available_engines_returns_bools():
    """get_available_engines returns bool values for each engine."""
    from services.video_sync import get_available_engines
    engines = get_available_engines()
    assert isinstance(engines["ffsubsync"], bool)
    assert isinstance(engines["alass"], bool)
