"""Tests for translation disable: job cancellation and /translate/disable endpoint."""

import pytest


def test_disable_endpoint_sets_flag_and_cancels_jobs(app_ctx, temp_db):
    """POST /translate/disable sets translation_enabled=false and cancels queued jobs."""
    from db.jobs import create_job, get_job

    job = create_job("/media/test.mkv")

    with app_ctx.test_client() as client:
        resp = client.post("/api/v1/translate/disable")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "disabled"
    assert data["cancelled_jobs"] >= 1
    assert get_job(job["id"])["status"] == "cancelled"


def test_disable_endpoint_returns_200_when_no_jobs(app_ctx, temp_db):
    """POST /translate/disable returns 200 even when no queued jobs exist."""
    with app_ctx.test_client() as client:
        resp = client.post("/api/v1/translate/disable")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["cancelled_jobs"] == 0


def test_cancel_queued_jobs_cancels_only_queued(app_ctx, temp_db):
    """cancel_queued_jobs() marks queued jobs as cancelled, leaves running/completed alone."""
    from db.jobs import cancel_queued_jobs, create_job, get_job, update_job

    queued_job = create_job("/media/queued.mkv")
    running_job = create_job("/media/running.mkv")
    update_job(running_job["id"], "running")
    done_job = create_job("/media/done.mkv")
    update_job(done_job["id"], "completed", result={})

    cancelled_count = cancel_queued_jobs()

    assert get_job(queued_job["id"])["status"] == "cancelled"
    assert get_job(running_job["id"])["status"] == "running"
    assert get_job(done_job["id"])["status"] == "completed"
    assert cancelled_count == 1


def test_cancel_queued_jobs_returns_zero_when_none(app_ctx, temp_db):
    """cancel_queued_jobs() returns 0 when no queued jobs exist."""
    from db.jobs import cancel_queued_jobs

    count = cancel_queued_jobs()
    assert count == 0


# ---------------------------------------------------------------------------
# Regression: every translation-initiating endpoint must honour the
# ``translation_enabled`` config flag.
#
# Pre-2026-04-30 audit: /translate/disable wrote translation_enabled=false
# and cancelled queued jobs, but no read-side path ever consulted the
# flag. So an API caller (or webhook re-entry, or scripted retry) could
# still kick off translation work after the user "disabled" the feature.
# ---------------------------------------------------------------------------


def test_translate_async_returns_503_when_disabled(client, tmp_path, monkeypatch):
    """POST /translate must 503 when translation_enabled is false."""
    from pathlib import Path

    monkeypatch.setenv("SUBLARR_MEDIA_PATH", str(tmp_path))
    from config import reload_settings

    reload_settings()

    sub_file = tmp_path / "ep.en.srt"
    sub_file.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")

    # _is_translation_enabled defaults to False — no patch needed.
    resp = client.post("/api/v1/translate", json={"file_path": str(sub_file)})
    assert resp.status_code == 503
    body = resp.get_json()
    assert "disabled" in body["error"].lower()


def test_translate_sync_returns_503_when_disabled(client, tmp_path, monkeypatch):
    """POST /translate/sync must 503 when translation_enabled is false."""
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", str(tmp_path))
    from config import reload_settings

    reload_settings()

    sub_file = tmp_path / "ep.en.srt"
    sub_file.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")

    resp = client.post("/api/v1/translate/sync", json={"file_path": str(sub_file)})
    assert resp.status_code == 503


def test_batch_returns_503_when_disabled_for_real_run(client, tmp_path, monkeypatch):
    """POST /batch must 503 for a non-dry-run when disabled."""
    from unittest.mock import patch as _patch

    monkeypatch.setenv("SUBLARR_MEDIA_PATH", str(tmp_path))
    from config import reload_settings

    reload_settings()

    fake_files = [
        {
            "path": str(tmp_path / "ep.mkv"),
            "target_status": "missing",
            "size_mb": 0.0,
        }
    ]
    with _patch("translator.scan_directory", return_value=fake_files):
        resp = client.post(
            "/api/v1/batch",
            json={"directory": str(tmp_path), "dry_run": False},
        )
    # The bug we're guarding against is "directly proceeded to a real
    # batch run" — which would have been a 202. The gate must intercept.
    assert resp.status_code == 503


def test_batch_dry_run_still_works_when_disabled(client, tmp_path, monkeypatch):
    """POST /batch?dry_run=true is a preview; gate must NOT block it so
    the user can still see what would be translated after re-enabling."""
    from unittest.mock import patch as _patch

    monkeypatch.setenv("SUBLARR_MEDIA_PATH", str(tmp_path))
    from config import reload_settings

    reload_settings()

    media = tmp_path / "ep.mkv"
    media.write_bytes(b"\x00")

    fake_files = [{"path": str(media), "target_status": "missing", "size_mb": 0.0}]
    with _patch("translator.scan_directory", return_value=fake_files):
        resp = client.post(
            "/api/v1/batch",
            json={"directory": str(tmp_path), "dry_run": True},
        )
    assert resp.status_code == 200
    assert resp.get_json()["dry_run"] is True


def test_retranslate_single_returns_503_when_disabled(client, tmp_path, monkeypatch):
    """POST /retranslate/<id> must 503 when translation_enabled is false."""
    from unittest.mock import patch as _patch

    monkeypatch.setenv("SUBLARR_MEDIA_PATH", str(tmp_path))
    from config import reload_settings

    reload_settings()

    media = tmp_path / "ep.mkv"
    media.write_text("x")

    fake_job = {"id": "j1", "status": "completed", "file_path": str(media)}
    with _patch("db.jobs.get_job", return_value=fake_job):
        resp = client.post("/api/v1/retranslate/1")
    assert resp.status_code == 503


def test_retranslate_batch_returns_503_when_disabled(client):
    """POST /retranslate/batch must 503 when translation_enabled is false."""
    resp = client.post("/api/v1/retranslate/batch")
    assert resp.status_code == 503


def test_retry_returns_503_when_disabled(client, tmp_path, monkeypatch):
    """POST /jobs/<id>/retry must 503 when translation_enabled is false."""
    from unittest.mock import patch as _patch

    monkeypatch.setenv("SUBLARR_MEDIA_PATH", str(tmp_path))
    from config import reload_settings

    reload_settings()

    media = tmp_path / "ep.mkv"
    media.write_text("x")

    fake_job = {
        "id": "j1",
        "status": "failed",
        "file_path": str(media),
        "arr_context": None,
    }
    with _patch("db.jobs.get_job", return_value=fake_job):
        resp = client.post("/api/v1/jobs/j1/retry")
    assert resp.status_code == 503
