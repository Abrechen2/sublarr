"""Process-wide gate for heavy media subprocesses (remux, extract, sync).

Background: on 2026-09-04 a boot-time wanted search ran four foreign-track
remuxes of 7 GB files in parallel (81.8 GB rewritten in one hour) while the
automation queue read whole movies for ffsubsync. The array sat at load 14
with the XFS flush thread blocked for 46 minutes and ffprobe calls timed out.
One gate, one setting (``media_io_max_parallel``), every heavy launcher.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from services.media_io_gate import (
    MediaGateBusyError,
    MediaIOGate,
    media_io_gate,
)

# ---------------------------------------------------------------------------
# The primitive
# ---------------------------------------------------------------------------


def test_limit_one_serialises_two_holders():
    gate = MediaIOGate(limit=1)
    order: list[str] = []

    def first():
        with gate.slot("a"):
            order.append("a-in")
            time.sleep(0.2)
            order.append("a-out")

    def second():
        with gate.slot("b"):
            order.append("b-in")

    t1 = threading.Thread(target=first)
    t1.start()
    time.sleep(0.05)
    t2 = threading.Thread(target=second)
    t2.start()
    t1.join()
    t2.join()
    assert order == ["a-in", "a-out", "b-in"]


def test_limit_two_lets_two_run_together():
    gate = MediaIOGate(limit=2)
    both_inside = threading.Barrier(2, timeout=2)

    def worker():
        with gate.slot("x"):
            both_inside.wait()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=3)
    assert not any(t.is_alive() for t in threads)
    assert gate.in_use == 0


def test_acquire_timeout_returns_false_and_slot_raises_busy():
    gate = MediaIOGate(limit=1)
    assert gate.acquire(timeout=1) is True
    try:
        assert gate.acquire(timeout=0.05) is False
        with pytest.raises(MediaGateBusyError), gate.slot("late", timeout=0.05):
            pass
    finally:
        gate.release()
    assert gate.in_use == 0


def test_slot_releases_on_exception():
    gate = MediaIOGate(limit=1)
    with pytest.raises(RuntimeError), gate.slot("boom"):
        raise RuntimeError("boom")
    assert gate.in_use == 0
    assert gate.acquire(timeout=0.1) is True
    gate.release()


def test_release_without_acquire_is_an_error():
    gate = MediaIOGate(limit=1)
    with pytest.raises(ValueError):
        gate.release()


def test_raising_limit_wakes_a_waiter():
    gate = MediaIOGate(limit=1)
    gate.acquire(timeout=1)
    got_in = threading.Event()

    def waiter():
        with gate.slot("w", timeout=5):
            got_in.set()

    t = threading.Thread(target=waiter)
    t.start()
    time.sleep(0.05)
    assert not got_in.is_set()
    gate.set_limit(2)
    assert got_in.wait(timeout=2)
    t.join(timeout=2)
    gate.release()
    assert gate.in_use == 0


def test_lowering_limit_does_not_evict_but_caps_new_acquires():
    gate = MediaIOGate(limit=2)
    gate.acquire(timeout=1)
    gate.acquire(timeout=1)
    gate.set_limit(1)
    assert gate.in_use == 2
    assert gate.acquire(timeout=0.05) is False
    gate.release()
    # still at the cap: one holder remains, limit is one
    assert gate.acquire(timeout=0.05) is False
    gate.release()
    assert gate.acquire(timeout=0.1) is True
    gate.release()


@pytest.mark.parametrize("bad", [0, -1])
def test_limit_below_one_is_clamped(bad):
    gate = MediaIOGate(limit=bad)
    assert gate.limit == 1
    gate.set_limit(bad)
    assert gate.limit == 1


def test_context_manager_protocol_matches_the_old_sync_lock():
    """``with gate:`` plus ``acquire(timeout=)``/``release()`` keep the sync
    engines and the sync preview working unchanged."""
    gate = MediaIOGate(limit=1)
    with gate:
        assert gate.in_use == 1
    assert gate.in_use == 0


# ---------------------------------------------------------------------------
# Settings binding
# ---------------------------------------------------------------------------


def test_limit_follows_settings_on_acquire():
    gate = MediaIOGate(limit=1)
    settings = MagicMock(media_io_max_parallel=3)
    with patch("services.media_io_gate.peek_settings", return_value=settings):
        assert gate.acquire(timeout=0.1)
        assert gate.limit == 3
    gate.release()


def test_no_settings_yet_keeps_last_limit():
    gate = MediaIOGate(limit=2)
    with patch("services.media_io_gate.peek_settings", return_value=None):
        assert gate.acquire(timeout=0.1)
        assert gate.limit == 2
    gate.release()


def test_cap_workers_never_exceeds_the_gate():
    gate = MediaIOGate(limit=1)
    with patch("services.media_io_gate.peek_settings", return_value=None):
        assert gate.cap_workers(4) == 1
        gate.set_limit(3)
        assert gate.cap_workers(4) == 3
        assert gate.cap_workers(2) == 2
        assert gate.cap_workers(0) == 1


# ---------------------------------------------------------------------------
# Wait policy: an HTTP request never queues for long behind a remux
# ---------------------------------------------------------------------------


@pytest.fixture
def app():
    return Flask("media-io-gate-test")


def test_default_wait_is_short_inside_a_request_and_long_outside(app):
    gate = MediaIOGate(limit=1)
    assert gate.default_wait_s() == gate.BACKGROUND_WAIT_S
    with app.test_request_context("/api/v1/health"):
        assert gate.default_wait_s() == gate.REQUEST_WAIT_S
    assert gate.REQUEST_WAIT_S < gate.BACKGROUND_WAIT_S


def test_request_context_slot_fails_fast_when_busy(app, monkeypatch):
    gate = MediaIOGate(limit=1)
    monkeypatch.setattr(gate, "REQUEST_WAIT_S", 0.05)
    gate.acquire(timeout=1)
    try:
        with app.test_request_context("/api/v1/health"):
            started = time.monotonic()
            with pytest.raises(MediaGateBusyError), gate.slot("ui"):
                pass
            assert time.monotonic() - started < 1
    finally:
        gate.release()


# ---------------------------------------------------------------------------
# Wiring: every heavy launcher goes through the module-level gate
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _pin_module_gate_limit():
    """The module-level gate reads settings on acquire; pin it so the wiring
    tests do not depend on whatever the test app configured."""
    with patch("services.media_io_gate.peek_settings", return_value=None):
        media_io_gate.set_limit(1)
        yield


def _fake_run_recording_gate(seen: list[int]):
    def _run(*args, **kwargs):
        seen.append(media_io_gate.in_use)
        return MagicMock(returncode=0, stdout="", stderr="")

    return _run


def test_mkvmerge_remux_runs_inside_the_gate():
    from remux import _remux_mkvmerge

    seen: list[int] = []
    with patch("remux.subprocess.run", side_effect=_fake_run_recording_gate(seen)):
        _remux_mkvmerge("/tmp/in.mkv", [3], "/tmp/out.mkv")
    assert seen == [1]
    assert media_io_gate.in_use == 0


def test_ffmpeg_remux_runs_inside_the_gate():
    from remux import _remux_ffmpeg

    seen: list[int] = []
    with (
        patch("remux._which", return_value=True),
        patch("remux.subprocess.run", side_effect=_fake_run_recording_gate(seen)),
    ):
        _remux_ffmpeg("/tmp/in.mkv", [3], "/tmp/out.mkv")
    assert seen == [1]
    assert media_io_gate.in_use == 0


def test_remux_reports_a_busy_gate_as_remux_error():
    from remux import RemuxError, _remux_mkvmerge

    media_io_gate.acquire(timeout=1)
    try:
        with (
            patch.object(media_io_gate, "default_wait_s", return_value=0.05),
            pytest.raises(RemuxError, match="busy"),
        ):
            _remux_mkvmerge("/tmp/in.mkv", [3], "/tmp/out.mkv")
    finally:
        media_io_gate.release()


def test_extract_subtitle_stream_runs_inside_the_gate(tmp_path):
    from ass_probe import extract_subtitle_stream

    seen: list[int] = []
    out = tmp_path / "ep.de.srt"

    def _run(*args, **kwargs):
        seen.append(media_io_gate.in_use)
        # ffmpeg writes to the tempfile named last in argv
        with open(args[0][-1], "w", encoding="utf-8") as fh:
            fh.write("1\n00:00:01,000 --> 00:00:02,000\nhi\n")
        return MagicMock(returncode=0, stdout="", stderr="")

    with (
        patch("ass_probe.subprocess.run", side_effect=_run),
        patch("ass_probe.get_settings", return_value=MagicMock(ffmpeg_timeout=5)),
    ):
        extract_subtitle_stream(str(tmp_path / "ep.mkv"), {"sub_index": 0}, str(out))
    assert seen == [1]
    assert media_io_gate.in_use == 0
    assert out.exists()


def test_extract_reports_a_busy_gate_as_runtime_error(tmp_path):
    from ass_probe import extract_subtitle_stream

    media_io_gate.acquire(timeout=1)
    try:
        with (
            patch.object(media_io_gate, "default_wait_s", return_value=0.05),
            patch("ass_probe.get_settings", return_value=MagicMock(ffmpeg_timeout=5)),
            pytest.raises(RuntimeError, match="busy"),
        ):
            extract_subtitle_stream(
                str(tmp_path / "ep.mkv"), {"sub_index": 0}, str(tmp_path / "o.srt")
            )
    finally:
        media_io_gate.release()
    assert not list(tmp_path.iterdir()), "no temp file may survive a refused extraction"


def test_sync_lock_is_the_media_gate():
    from services.sync_engines.concurrency import sync_subprocess_lock

    assert sync_subprocess_lock is media_io_gate


def test_scanner_batch_probe_workers_are_capped_by_the_gate():
    from services import wanted_item_scanner

    settings = MagicMock(scan_metadata_max_workers=4, media_io_max_parallel=1)
    with (
        patch("services.wanted_item_scanner.get_settings", return_value=settings),
        patch("services.media_io_gate.peek_settings", return_value=settings),
        patch("services.wanted_item_scanner.get_media_streams", return_value={"streams": []}),
        patch("services.wanted_item_scanner.ThreadPoolExecutor") as pool,
        patch("services.wanted_item_scanner.as_completed", return_value=[]),
    ):
        wanted_item_scanner.batch_probe(["/m/a.mkv", "/m/b.mkv"])
    pool.assert_called_once_with(max_workers=1)


def test_route_batch_probe_workers_are_capped_by_the_gate():
    from routes.wanted import batch_probe as route

    settings = MagicMock(scan_metadata_max_workers=4, media_io_max_parallel=2)
    with (
        patch("routes.wanted.batch_probe.get_settings", return_value=settings),
        patch("services.media_io_gate.peek_settings", return_value=settings),
        patch("routes.wanted.batch_probe.ThreadPoolExecutor") as pool,
        patch("routes.wanted.batch_probe._init_batch_probe_state"),
        patch("routes.wanted.batch_probe._finalize_batch_probe"),
        patch("routes.wanted.batch_probe.as_completed", return_value=[]),
    ):
        route._run_batch_probe([], MagicMock())
    pool.assert_called_once_with(max_workers=2)


def test_waiter_notices_a_raised_setting_without_a_release():
    """Codex review finding: a thread already asleep in the wait loop must see
    a raised ``media_io_max_parallel`` even if nobody releases or touches the
    gate afterwards."""
    gate = MediaIOGate(limit=1)
    settings = MagicMock(media_io_max_parallel=1)
    with patch("services.media_io_gate.peek_settings", return_value=settings):
        gate.acquire(timeout=1)
        got_in = threading.Event()

        def waiter():
            with gate.slot("w", timeout=10):
                got_in.set()

        t = threading.Thread(target=waiter)
        t.start()
        time.sleep(0.1)
        assert not got_in.is_set()
        settings.media_io_max_parallel = 2  # nobody calls set_limit, nobody releases
        assert got_in.wait(timeout=3)
        t.join(timeout=2)
        gate.release()
    assert gate.in_use == 0


def test_non_blocking_acquire_with_timeout_is_rejected_like_a_semaphore():
    gate = MediaIOGate(limit=1)
    with pytest.raises(ValueError):
        gate.acquire(blocking=False, timeout=1)
    assert gate.acquire(blocking=False) is True
    assert gate.acquire(blocking=False) is False
    gate.release()


def test_request_wait_is_bounded_well_below_the_gunicorn_thread_budget():
    """Four request threads; a holder that keeps the gate for minutes must not
    be able to park them for long."""
    assert MediaIOGate.REQUEST_WAIT_S <= 10


def test_probe_batches_run_each_probe_inside_the_gate():
    """Codex review finding: sizing each pool by the limit still lets two
    concurrent batches exceed it. Every batch probe holds a slot."""
    from services import wanted_item_scanner

    settings = MagicMock(scan_metadata_max_workers=2, media_io_max_parallel=1)
    seen: list[int] = []

    def _probe(path, use_cache):
        seen.append(media_io_gate.in_use)
        return {"streams": []}

    with (
        patch("services.wanted_item_scanner.get_settings", return_value=settings),
        patch("services.media_io_gate.peek_settings", return_value=settings),
        patch("services.wanted_item_scanner.get_media_streams", side_effect=_probe),
    ):
        out = wanted_item_scanner.batch_probe(["/m/a.mkv", "/m/b.mkv", "/m/c.mkv"])
    assert len(out) == 3
    assert seen == [1, 1, 1]
    assert media_io_gate.in_use == 0


def test_route_batch_probe_submits_gated_probes():
    from routes.wanted import batch_probe as route

    settings = MagicMock(scan_metadata_max_workers=2, media_io_max_parallel=1)
    submitted: list = []

    class _Pool:
        def __init__(self, max_workers):
            self.max_workers = max_workers

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def submit(self, fn, *args):
            submitted.append((fn, args))
            return MagicMock()

    with (
        patch("routes.wanted.batch_probe.get_settings", return_value=settings),
        patch("services.media_io_gate.peek_settings", return_value=settings),
        patch("routes.wanted.batch_probe.ThreadPoolExecutor", _Pool),
        patch("routes.wanted.batch_probe._init_batch_probe_state"),
        patch("routes.wanted.batch_probe._finalize_batch_probe"),
        patch("routes.wanted.batch_probe.as_completed", return_value=[]),
    ):
        route._run_batch_probe([{"file_path": "/m/a.mkv"}], MagicMock())
    assert len(submitted) == 1
    fn, args = submitted[0]
    assert fn is route._gated_probe
    assert args == ("/m/a.mkv",)


def test_sync_preview_waits_less_than_the_request_budget():
    from services import sync_preview

    assert sync_preview._LOCK_WAIT_TIMEOUT <= MediaIOGate.REQUEST_WAIT_S


def test_setting_exists_with_a_conservative_default_and_is_in_the_media_view():
    from config_settings import UISettings
    from config_views import MediaServerSettings

    assert UISettings.model_fields["media_io_max_parallel"].default == 1
    assert "media_io_max_parallel" in MediaServerSettings._fields
