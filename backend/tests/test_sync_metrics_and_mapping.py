"""Regression tests for two latent fixes shipped 2026-05-12:

1. M3 — `services.sync_engines.events._record_metrics` bumps the Prometheus
   counters/histograms alongside every sync_job_runs audit row, giving the
   bulk auto-sync flow first-class observability.

2. M5 — `routes/audio.py` and `routes/ocr.py` previously checked
   `hasattr(settings, "media_path_mapping")`, a Pydantic field that doesn't
   exist (the real field is `path_mapping: str`). Both files now call
   `config.map_path` directly so the mapping actually applies. Pin that
   behaviour so a future refactor cannot silently regress it again.
"""

from __future__ import annotations

from unittest.mock import patch


def test_record_metrics_bumps_counter_and_histograms():
    """OK-status sync writes increment counter + both histograms."""
    from monitoring.metrics import (
        sync_jobs_duration_seconds,
        sync_jobs_offset_ms,
        sync_jobs_total,
    )
    from services.sync_engines.events import _record_metrics

    before_total = sync_jobs_total.labels(engine="ffsubsync", status="ok")._value.get()
    before_dur = sync_jobs_duration_seconds.labels(engine="ffsubsync")._sum.get()
    before_off = sync_jobs_offset_ms.labels(engine="ffsubsync")._sum.get()

    _record_metrics(engine="ffsubsync", status="ok", offset_ms=1234, duration_ms=5000)

    assert sync_jobs_total.labels(engine="ffsubsync", status="ok")._value.get() == before_total + 1
    assert sync_jobs_duration_seconds.labels(engine="ffsubsync")._sum.get() == before_dur + 5.0
    # offset_ms histogram observes absolute value, so a negative shift still bumps the same bucket.
    assert sync_jobs_offset_ms.labels(engine="ffsubsync")._sum.get() == before_off + 1234


def test_record_metrics_skips_offset_histogram_on_error():
    """Error-status writes bump counter + duration, but not the offset histogram —
    a failed sync has no meaningful shift to record."""
    from monitoring.metrics import sync_jobs_offset_ms, sync_jobs_total
    from services.sync_engines.events import _record_metrics

    before_total = sync_jobs_total.labels(engine="alass", status="error")._value.get()
    before_off = sync_jobs_offset_ms.labels(engine="alass")._sum.get()

    _record_metrics(engine="alass", status="error", offset_ms=None, duration_ms=300)

    assert sync_jobs_total.labels(engine="alass", status="error")._value.get() == before_total + 1
    assert sync_jobs_offset_ms.labels(engine="alass")._sum.get() == before_off  # unchanged


def test_record_metrics_handles_negative_offset():
    """A negative shift (sub appears too early) should observe the absolute value
    so the histogram buckets reflect drift magnitude, not direction."""
    from monitoring.metrics import sync_jobs_offset_ms
    from services.sync_engines.events import _record_metrics

    before = sync_jobs_offset_ms.labels(engine="ffsubsync")._sum.get()
    _record_metrics(engine="ffsubsync", status="ok", offset_ms=-1500, duration_ms=2000)
    assert sync_jobs_offset_ms.labels(engine="ffsubsync")._sum.get() == before + 1500


def test_record_metrics_never_raises():
    """Even when the metrics module is unavailable, the writer must not break the
    audit-row path (defensive contract — the comment in the source spells this out)."""
    from services.sync_engines.events import _record_metrics

    with patch("monitoring.metrics.sync_jobs_total", side_effect=RuntimeError("boom")):
        _record_metrics(engine="ffsubsync", status="ok", offset_ms=0, duration_ms=1)


def test_audio_route_calls_map_path(client, tmp_path):
    """audio.py POST /audio/extract previously checked
    ``settings.media_path_mapping`` — a non-existent field — so path mapping
    silently never applied. Verify it now routes through ``config.map_path``.
    """
    sub = tmp_path / "video.mkv"
    sub.write_text("placeholder")

    with patch("routes.audio.map_path", return_value=str(sub)) as mp:
        # The endpoint also calls is_safe_path + os.path.exists; map_path is
        # what we care about — its single invocation per request proves wiring.
        client.post("/api/v1/audio/extract", json={"file_path": "/remote/video.mkv"})

    mp.assert_called_once_with("/remote/video.mkv")


def test_ocr_route_calls_map_path(client, tmp_path):
    """ocr.py POST /ocr/extract previously had the same dead-code pattern.
    Same regression guard as the audio route above.
    """
    sub = tmp_path / "video.mkv"
    sub.write_text("placeholder")

    with patch("routes.ocr.map_path", return_value=str(sub)) as mp:
        client.post(
            "/api/v1/ocr/extract",
            json={"file_path": "/remote/video.mkv", "stream_index": 0, "language": "eng"},
        )

    mp.assert_called_once_with("/remote/video.mkv")
