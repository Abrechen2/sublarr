"""Tests for backend/routes/video_sync.py and backend/services/video_sync.py."""

from unittest.mock import MagicMock, patch

# ─── Engine endpoint ─────────────────────────────────────────────────────────


def test_get_engines_returns_dict(client):
    """GET /engines returns a JSON object with engine availability."""
    with patch(
        "services.video_sync.get_available_engines",
        return_value={"ffsubsync": False, "alass": False},
    ):
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
    resp = client.post(
        "/api/v1/tools/video-sync",
        json={
            "file_path": "/nonexistent.srt",
            "video_path": "/v.mkv",
            "engine": "ffsubsync",
        },
    )
    assert resp.status_code == 404


def test_start_sync_ffsubsync_missing_video_path(client, tmp_path):
    """ffsubsync without video_path returns 400."""
    sub = tmp_path / "ep.de.srt"
    sub.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")
    resp = client.post(
        "/api/v1/tools/video-sync",
        json={
            "file_path": str(sub),
            "engine": "ffsubsync",
        },
    )
    assert resp.status_code == 400
    assert "video_path" in resp.get_json()["error"]


def test_start_sync_alass_missing_reference(client, tmp_path):
    """alass without reference_path or reference_track_index returns 400."""
    sub = tmp_path / "ep.de.srt"
    sub.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")
    resp = client.post(
        "/api/v1/tools/video-sync",
        json={
            "file_path": str(sub),
            "engine": "alass",
        },
    )
    assert resp.status_code == 400


def test_start_sync_unknown_engine(client, tmp_path):
    """Unknown engine returns 400."""
    sub = tmp_path / "ep.de.srt"
    sub.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")
    resp = client.post(
        "/api/v1/tools/video-sync",
        json={
            "file_path": str(sub),
            "engine": "imaginary-engine",
        },
    )
    assert resp.status_code == 400


# ─── Job creation ────────────────────────────────────────────────────────────


def test_start_sync_queues_job(client, tmp_path):
    """Valid request queues a background job and returns 202 with job_id."""
    sub = tmp_path / "ep.de.srt"
    sub.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")
    # video_path must be under SUBLARR_MEDIA_PATH (set to temp dir in tests)
    video = tmp_path / "ep.mkv"
    with patch("routes.video_sync._executor") as mock_exec:
        resp = client.post(
            "/api/v1/tools/video-sync",
            json={
                "file_path": str(sub),
                "video_path": str(video),
                "engine": "ffsubsync",
            },
        )
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
        resp = client.post(
            "/api/v1/tools/video-sync",
            json={
                "file_path": str(sub),
                "engine": "alass",
                "reference_path": str(ref),
            },
        )
    assert resp.status_code == 202
    mock_exec.submit.assert_called_once()


# ─── /auto-sync/bulk — scope branches + sidecar coverage ────────────────────


def _bulk_make_video(tmp_path, name: str, langs=("de", "en")):
    """Helper: create a fake video + one or more sidecars next to it. Returns the video path."""
    video = tmp_path / f"{name}.mkv"
    video.write_text("video")
    for lang in langs:
        (tmp_path / f"{name}.{lang}.srt").write_text(f"1\n00:00:01,000 --> 00:00:02,000\n{lang}\n")
    return str(video)


def test_bulk_rejects_unknown_scope(client):
    """scope must be one of the documented values — anything else returns 400."""
    resp = client.post("/api/v1/tools/auto-sync/bulk", json={"scope": "imaginary"})
    assert resp.status_code == 400
    assert "scope" in resp.get_json()["error"]


def test_bulk_rejects_series_without_id(client):
    """scope='series' requires series_id — otherwise the call is ambiguous."""
    resp = client.post("/api/v1/tools/auto-sync/bulk", json={"scope": "series"})
    assert resp.status_code == 400
    assert "series_id" in resp.get_json()["error"]


def test_bulk_queues_one_job_per_sidecar(client, tmp_path):
    """The previous bulk implementation queued only the first sidecar per video.
    Two-language episodes lost half the work. Lock in: every sidecar gets a job.
    """
    video_path = _bulk_make_video(tmp_path, "ep01", langs=("de", "en", "ja"))

    with (
        patch("routes.video_sync._bulk_videos_from_sonarr", return_value=[video_path]),
        patch("routes.video_sync._submit_sync") as mock_submit,
    ):
        resp = client.post(
            "/api/v1/tools/auto-sync/bulk", json={"scope": "library", "engine": "ffsubsync"}
        )

    assert resp.status_code == 202
    data = resp.get_json()
    assert data["queued"] == 3, "expected one job per sidecar (de + en + ja)"
    assert mock_submit.call_count == 3
    # Deduplication guard: same sub never queued twice within one bulk request.
    submitted_subs = {call.args[3] for call in mock_submit.call_args_list}
    assert len(submitted_subs) == 3


def test_bulk_scope_radarr_uses_radarr_helper(client, tmp_path):
    """scope='radarr' MUST source paths from the Radarr helper, not Sonarr."""
    video_path = _bulk_make_video(tmp_path, "movie")

    with (
        patch(
            "routes.video_sync._bulk_videos_from_radarr", return_value=[video_path]
        ) as mock_radarr,
        patch("routes.video_sync._bulk_videos_from_sonarr") as mock_sonarr,
        patch("routes.video_sync._submit_sync"),
    ):
        resp = client.post("/api/v1/tools/auto-sync/bulk", json={"scope": "radarr"})

    assert resp.status_code == 202
    mock_radarr.assert_called_once()
    mock_sonarr.assert_not_called()
    assert resp.get_json()["videos_considered"] == {"radarr": 1}


def test_bulk_scope_standalone_uses_standalone_helper(client, tmp_path):
    """scope='standalone' walks standalone folders, not the *arr APIs."""
    video_path = _bulk_make_video(tmp_path, "standalone_ep")

    with (
        patch(
            "routes.video_sync._bulk_videos_from_standalone", return_value=[video_path]
        ) as mock_sa,
        patch("routes.video_sync._bulk_videos_from_sonarr") as mock_sonarr,
        patch("routes.video_sync._bulk_videos_from_radarr") as mock_radarr,
        patch("routes.video_sync._submit_sync"),
    ):
        resp = client.post("/api/v1/tools/auto-sync/bulk", json={"scope": "standalone"})

    assert resp.status_code == 202
    mock_sa.assert_called_once()
    mock_sonarr.assert_not_called()
    mock_radarr.assert_not_called()
    assert resp.get_json()["videos_considered"] == {"standalone": 1}


def test_bulk_scope_all_unions_all_three_sources(client, tmp_path):
    """scope='all' must hit all three helpers and combine the video lists."""
    v1 = _bulk_make_video(tmp_path, "sonarr_ep")
    v2 = _bulk_make_video(tmp_path, "movie")
    v3 = _bulk_make_video(tmp_path, "standalone_ep")

    with (
        patch("routes.video_sync._bulk_videos_from_sonarr", return_value=[v1]),
        patch("routes.video_sync._bulk_videos_from_radarr", return_value=[v2]),
        patch("routes.video_sync._bulk_videos_from_standalone", return_value=[v3]),
        patch("routes.video_sync._submit_sync") as mock_submit,
    ):
        resp = client.post("/api/v1/tools/auto-sync/bulk", json={"scope": "all"})

    assert resp.status_code == 202
    data = resp.get_json()
    assert data["videos_considered"] == {"sonarr": 1, "radarr": 1, "standalone": 1}
    # 3 videos × 2 sidecars each (de + en defaults from _bulk_make_video).
    assert data["queued"] == 6
    assert mock_submit.call_count == 6


def test_bulk_reports_skip_reasons(client, tmp_path):
    """Skipped videos are tallied by reason so the user can diagnose drop-offs."""
    real_video = _bulk_make_video(tmp_path, "real_ep")
    missing_video = str(tmp_path / "nonexistent.mkv")
    # No sidecars next to this one — should land in 'no_sidecar' bucket.
    bare_video = str(tmp_path / "bare.mkv")
    (tmp_path / "bare.mkv").write_text("x")

    with (
        patch(
            "routes.video_sync._bulk_videos_from_sonarr",
            return_value=[real_video, missing_video, bare_video],
        ),
        patch("routes.video_sync._submit_sync"),
    ):
        resp = client.post("/api/v1/tools/auto-sync/bulk", json={"scope": "library"})

    data = resp.get_json()
    assert data["skipped"]["missing_file"] == 1
    assert data["skipped"]["no_sidecar"] == 1
    assert data["queued"] == 2  # 2 sidecars on the real video


# ─── app_context regression (worker thread DB writes + after_sync hooks) ────


def test_submit_sync_wraps_worker_in_app_context(app_ctx):
    """_submit_sync MUST push the Flask app context inside the worker thread,
    otherwise sync_with_ffsubsync's write_sync_job_run and after_sync triggers
    silently fail with "Working outside of application context"
    (see feedback_flask_app_context_in_threads memory).
    """
    from flask import current_app, has_app_context

    from routes import video_sync as vs

    captured: dict = {"runner": None}

    class _CapturingExecutor:
        def submit(self, fn, *args, **kwargs):
            captured["runner"] = (fn, args, kwargs)

    seen: dict = {"has_ctx": False, "current_app_name": None}

    def _fake_run_sync(*args, **kwargs):
        seen["has_ctx"] = has_app_context()
        seen["current_app_name"] = current_app.name

    with (
        patch.object(vs, "_executor", _CapturingExecutor()),
        patch.object(vs, "_run_sync", _fake_run_sync),
    ):
        vs._submit_sync(app_ctx, "job-1", "ffsubsync", "/sub.srt", "/v.mkv", None, None)
        # Executor was called with our generated wrapper
        fn, _args, _kwargs = captured["runner"]
        # Invoke the wrapper as the worker would — must be inside the patch
        # scope so the fake _run_sync (which captures the context state) runs
        fn()

    assert seen["has_ctx"] is True, "worker ran outside app context — DB writes will fail"
    assert seen["current_app_name"]


def test_start_sync_uses_submit_sync_with_current_app(client, tmp_path):
    """POST /video-sync routes through _submit_sync (not _executor.submit directly)
    so the captured app is the live Flask app, not a None placeholder.
    """
    sub = tmp_path / "ep.de.srt"
    sub.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")
    video = tmp_path / "ep.mkv"

    with patch("routes.video_sync._submit_sync") as mock_submit:
        resp = client.post(
            "/api/v1/tools/video-sync",
            json={"file_path": str(sub), "video_path": str(video), "engine": "ffsubsync"},
        )

    assert resp.status_code == 202
    mock_submit.assert_called_once()
    # First positional arg is the app — must be a real Flask app, not None / a string
    submitted_app = mock_submit.call_args[0][0]
    assert submitted_app is not None
    assert hasattr(submitted_app, "app_context")


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
    video = tmp_path / "ep.mkv"
    with patch("routes.video_sync._executor"):
        resp = client.post(
            "/api/v1/tools/video-sync",
            json={
                "file_path": str(sub),
                "video_path": str(video),
                "engine": "ffsubsync",
            },
        )
    job_id = resp.get_json()["job_id"]

    status_resp = client.get(f"/api/v1/tools/video-sync/{job_id}")
    assert status_resp.status_code == 200
    data = status_resp.get_json()
    assert data["job_id"] == job_id
    assert data["status"] == "queued"


# ─── Service unit tests ───────────────────────────────────────────────────────


def test_sync_unavailable_error_when_ffsubsync_missing(tmp_path):
    """sync_with_ffsubsync raises SyncUnavailableError when not installed."""
    from services.video_sync import SyncUnavailableError, sync_with_ffsubsync

    sub = tmp_path / "ep.srt"
    sub.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")
    # Availability is checked dynamically via shutil.which / _check_module
    with (
        patch("services.video_sync.shutil.which", return_value=None),
        patch("services.video_sync._check_module", return_value=False),
    ):
        try:
            sync_with_ffsubsync(str(sub), "/video.mkv")
            assert False, "Expected SyncUnavailableError"
        except SyncUnavailableError:
            pass


def test_sync_unavailable_error_when_alass_missing(tmp_path):
    """sync_with_alass raises SyncUnavailableError when not installed."""
    from services.video_sync import SyncUnavailableError, sync_with_alass

    sub = tmp_path / "ep.srt"
    sub.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")
    # Availability is checked dynamically via shutil.which
    with patch("services.video_sync.shutil.which", return_value=None):
        try:
            sync_with_alass(str(sub), "/ref.srt")
            assert False, "Expected SyncUnavailableError"
        except SyncUnavailableError:
            pass


def test_ffsubsync_rejects_shift_above_sanity_threshold(tmp_path):
    """sync_with_ffsubsync raises SyncSanityThresholdError when the engine
    returns a shift larger than sync_sanity_threshold_ms — the destination
    sidecar must be left untouched (bulk callers depend on this; mis-locks
    in the ±56-60s band would otherwise corrupt the library at scale).

    Mirrors the gate already enforced by
    ``services.sync_engines.orchestrator.SyncOrchestrator``.
    """
    from services.video_sync import SyncSanityThresholdError, sync_with_ffsubsync

    sub = tmp_path / "ep.srt"
    original = "1\n00:00:01,000 --> 00:00:02,000\nHello\n"
    sub.write_text(original)

    # ffsubsync "succeeded" but with an insane 55.7s shift (in the ±56-60s
    # mis-lock band) — threshold is 45_000 ms.
    fake_result = MagicMock(returncode=0, stderr="INFO offset seconds: 55.720", stdout="")
    fake_settings = MagicMock(sync_sanity_threshold_ms=45_000)

    try:
        with (
            patch("services.video_sync.shutil.which", return_value="/usr/bin/ffsubsync"),
            patch("services.video_sync.subprocess.run", return_value=fake_result),
            patch("config.get_settings", return_value=fake_settings),
        ):
            sync_with_ffsubsync(str(sub), "/video.mkv")
        raise AssertionError("Expected SyncSanityThresholdError")
    except SyncSanityThresholdError as exc:
        assert "55720" in str(exc) or "55,720" in str(exc)
        assert "45000" in str(exc) or "45,000" in str(exc)

    # Sidecar must not have been overwritten with the bad ffsubsync output.
    assert sub.read_text() == original


def test_ffsubsync_accepts_shift_below_sanity_threshold(tmp_path):
    """sync_with_ffsubsync proceeds normally when shift is under the threshold."""
    from services.video_sync import sync_with_ffsubsync

    sub = tmp_path / "ep.srt"
    sub.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")
    fake_result = MagicMock(returncode=0, stderr="INFO offset seconds: 1.234", stdout="")
    fake_settings = MagicMock(sync_sanity_threshold_ms=45_000)

    with (
        patch("services.video_sync.shutil.which", return_value="/usr/bin/ffsubsync"),
        patch("services.video_sync.subprocess.run", return_value=fake_result),
        patch("config.get_settings", return_value=fake_settings),
    ):
        result = sync_with_ffsubsync(str(sub), "/video.mkv")
    assert result["shift_ms"] == 1234
    assert result["engine"] == "ffsubsync"


def test_parse_ffsubsync_shift():
    """_parse_ffsubsync_shift extracts ms from ffsubsync output (legacy + modern)."""
    from services.video_sync import _parse_ffsubsync_shift

    assert _parse_ffsubsync_shift("offset: 1.234 s applied") == 1234
    assert _parse_ffsubsync_shift("no offset info") == 0
    assert _parse_ffsubsync_shift("Offset: -0.5 s") == -500
    # ffsubsync ≥0.4 — rich-logger format with trailing source-location annotation
    assert (
        _parse_ffsubsync_shift(
            "[13:51:53] INFO     offset seconds: 22.960                      ffsubsync.py:189"
        )
        == 22960
    )
    assert (
        _parse_ffsubsync_shift(
            "           INFO     offset seconds: -0.990                      ffsubsync.py:189"
        )
        == -990
    )
    assert _parse_ffsubsync_shift("offset seconds: 0.000") == 0


def test_parse_ffsubsync_shift_engine_class():
    """sync_engines.ffsubsync_engine._parse_ffsubsync_shift mirrors the legacy parser."""
    from services.sync_engines.ffsubsync_engine import _parse_ffsubsync_shift

    assert _parse_ffsubsync_shift("offset: 1.234 s applied") == 1234
    assert _parse_ffsubsync_shift("no offset info") == 0
    assert _parse_ffsubsync_shift("Offset: -0.5 s") == -500
    assert _parse_ffsubsync_shift("estimated shift: 0.42s") == 420
    assert (
        _parse_ffsubsync_shift(
            "[13:51:53] INFO     offset seconds: 22.960                      ffsubsync.py:189"
        )
        == 22960
    )
    assert (
        _parse_ffsubsync_shift(
            "           INFO     offset seconds: -0.990                      ffsubsync.py:189"
        )
        == -990
    )
    assert _parse_ffsubsync_shift("offset seconds: 0.000") == 0


def test_get_available_engines_returns_bools():
    """get_available_engines returns bool values for each engine."""
    from services.video_sync import get_available_engines

    engines = get_available_engines()
    assert isinstance(engines["ffsubsync"], bool)
    assert isinstance(engines["alass"], bool)
