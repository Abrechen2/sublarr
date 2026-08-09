"""Tests for the batched foreign-track sweep state machine."""

import os
from types import SimpleNamespace

import pytest

from db.models import foreign_tracks as ft
from services.foreign_tracks import sweep as sw
from services.foreign_tracks.state import (
    PHASE_ENUMERATE,
    PHASE_IDLE,
    PHASE_PROBE,
    PHASE_STRIP,
)


class FakeClock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


@pytest.fixture()
def app(tmp_path):
    """Create a Flask app with an isolated SQLite DB for testing."""
    from app import create_app
    from config import reload_settings

    db_path = str(tmp_path / "test.db")
    os.environ["SUBLARR_DB_PATH"] = db_path
    os.environ["SUBLARR_API_KEY"] = ""
    os.environ["SUBLARR_LOG_LEVEL"] = "ERROR"

    reload_settings()

    application = create_app(testing=True)
    application.config["TESTING"] = True

    with application.app_context():
        yield application

    os.environ.pop("SUBLARR_DB_PATH", None)
    os.environ.pop("SUBLARR_API_KEY", None)
    os.environ.pop("SUBLARR_LOG_LEVEL", None)


@pytest.fixture
def repo(app):
    from db.repositories.foreign_track_scan import ForeignTrackScanRepository

    return ForeignTrackScanRepository()


CFG = {"keep_languages": ["de", "en"], "keep_und": True}


def _enable_foreign_track_tick(monkeypatch, media_path):
    monkeypatch.setattr(
        "config.get_settings",
        lambda: SimpleNamespace(
            foreign_track_sweep_enabled=True,
            foreign_track_sweep_budget_s=60,
            media_path=media_path,
            cleanup_foreign_tracks_keep_languages=["de", "en"],
            cleanup_foreign_tracks_keep_und=True,
        ),
    )
    monkeypatch.setattr(sw, "_find_rule", lambda repo: {"config_json": CFG})


def test_enumerate_creates_rows_from_the_walk(app, repo, tmp_path, monkeypatch):
    """The walk creates a row for every file it finds. `run_slice` chains
    phases within one call (bounded only by the wall-clock budget, not by
    which phase it started in), so the row is also probed in this same
    call — with `_probe_file` stubbed clean, it ends up `clean`, not still
    waiting in `pending`."""
    monkeypatch.setattr(sw, "iter_video_files", lambda *a, **k: iter([("/media/a.mkv", 10, 1.0)]))
    monkeypatch.setattr(sw, "_probe_file", lambda path: {"streams": []})
    sw.run_slice(str(tmp_path), CFG, budget_s=60, now_fn=FakeClock(), repo=repo)
    assert repo.counts_by_state()[ft.STATE_CLEAN] == 1


def test_interrupted_enumeration_does_not_prune_unvisited_rows(app, repo, tmp_path, monkeypatch):
    """The most dangerous failure mode: a walk that dies halfway must not make
    every file it never reached look deleted.

    Seeded at generation=0 deliberately: `_enumerate` bumps `state.generation`
    to 1 before the walk starts, so `prune_stale(1)` deletes `generation < 1`.
    A row seeded at generation=1 would survive a wrongly-placed prune too
    (1 is never < 1), making the assertion pass regardless of whether the
    guard actually works. generation=0 is the only seed that can catch a
    prune hoisted above the try — verified by temporarily hoisting it (see
    the fix report)."""
    repo.upsert_seen("/media/old.mkv", 10, 1.0, generation=0)

    def _explode(*a, **k):
        yield ("/media/a.mkv", 10, 1.0)
        raise OSError("share went away")

    monkeypatch.setattr(sw, "iter_video_files", _explode)
    sw.run_slice(str(tmp_path), CFG, budget_s=60, now_fn=FakeClock(), repo=repo)
    paths = {r.path for r in repo.next_pending(limit=10)}
    assert "/media/old.mkv" in paths


def test_a_stop_during_enumeration_leaves_the_pass_incomplete(app, repo, tmp_path, monkeypatch):
    """Enumeration is the longest uninterruptible stretch — 754 s on the
    production library — so a stop that only takes effect afterwards is not a
    stop the operator will believe.

    Leaving the walk early must take the same exit as the OSError path: the
    pass stays incomplete and nothing is pruned. Pruning after a partial walk
    would mark every unvisited file as deleted and throw away its cached
    verdict, which is the worst failure this design has to avoid.
    """
    import threading

    from services.scheduler import cancellation

    repo.upsert_seen("/media/old.mkv", 10, 1.0, generation=0)
    event = threading.Event()
    walked: list[str] = []

    def _walk(*a, **k):
        walked.append("/media/a.mkv")
        yield ("/media/a.mkv", 10, 1.0)
        event.set()  # the stop arrives mid-walk
        walked.append("/media/b.mkv")
        yield ("/media/b.mkv", 10, 1.0)

    monkeypatch.setattr(sw, "iter_video_files", _walk)

    token = cancellation.activate(event)
    try:
        sw.run_slice(str(tmp_path), CFG, budget_s=60, now_fn=FakeClock(), repo=repo)
    finally:
        cancellation.deactivate(token)

    paths = {r.path for r in repo.next_pending(limit=10)}
    assert "/media/old.mkv" in paths, (
        "a partial walk must not prune — the unvisited rows are not deleted files"
    )
    assert "/media/b.mkv" not in paths, f"enumeration kept walking after the stop: {walked}"


def test_probe_classifies_files_and_the_affected_one_gets_stripped(
    app, repo, tmp_path, monkeypatch
):
    """Probe correctly tells a foreign-track file (a.mkv, spa) apart from a
    clean one (b.mkv, ger only). Chaining then carries the affected file
    straight into strip within the same call — `_strip_file` is stubbed so
    that continuation exercises the state transition without a real remux."""
    repo.upsert_seen("/media/a.mkv", 10, 1.0, generation=1)
    repo.upsert_seen("/media/b.mkv", 10, 1.0, generation=1)
    monkeypatch.setattr(sw, "iter_video_files", lambda *a, **k: iter([]))
    probes = {
        "/media/a.mkv": {"streams": [{"codec_type": "subtitle", "tags": {"language": "spa"}}]},
        "/media/b.mkv": {"streams": [{"codec_type": "subtitle", "tags": {"language": "ger"}}]},
    }
    monkeypatch.setattr(sw, "_probe_file", lambda path: probes[path])
    monkeypatch.setattr(sw, "_strip_file", lambda path, keep, keep_und: ("/trash/a.bak", 5))
    sw.run_slice(str(tmp_path), CFG, budget_s=60, now_fn=FakeClock(), repo=repo)
    counts = repo.counts_by_state()
    assert counts[ft.STATE_STRIPPED] == 1
    assert counts[ft.STATE_CLEAN] == 1


def test_budget_stops_the_probe_pass_and_keeps_progress(app, repo, tmp_path, monkeypatch):
    for i in range(5):
        repo.upsert_seen(f"/media/{i}.mkv", 10, 1.0, generation=1)
    monkeypatch.setattr(sw, "iter_video_files", lambda *a, **k: iter([]))
    clock = FakeClock()

    def _slow_probe(path):
        clock.advance(40)
        return {"streams": []}

    monkeypatch.setattr(sw, "_probe_file", _slow_probe)
    sw.run_slice(str(tmp_path), CFG, budget_s=60, now_fn=clock, repo=repo)
    counts = repo.counts_by_state()
    assert counts[ft.STATE_CLEAN] == 2
    assert counts[ft.STATE_PENDING] == 3


def test_stop_request_ends_the_probe_slice_like_the_budget(app, repo, tmp_path, monkeypatch):
    """The stop arrives during the first ffprobe.

    The real slice is driven; the second pending row must remain pending
    because the production probe loop joins cancellation into the same
    between-file boundary as the wall-clock budget.
    """
    import threading

    from services.scheduler import cancellation

    repo.upsert_seen("/media/a.mkv", 10, 1.0, generation=1)
    repo.upsert_seen("/media/b.mkv", 10, 1.0, generation=1)
    monkeypatch.setattr(sw, "iter_video_files", lambda *a, **k: iter([]))

    event = threading.Event()
    probed: list[str] = []

    def fake_probe(path):
        probed.append(path)
        event.set()  # the stop arrives while the first ffprobe is in flight
        return {"streams": []}

    monkeypatch.setattr(sw, "_probe_file", fake_probe)
    _enable_foreign_track_tick(monkeypatch, str(tmp_path))

    token = cancellation.activate(event)
    try:
        sw.foreign_track_sweep_tick()
    finally:
        cancellation.deactivate(token)

    assert probed == ["/media/a.mkv"], (
        f"the sweep kept probing after being asked to stop: probed {probed}"
    )
    counts = repo.counts_by_state()
    assert counts[ft.STATE_CLEAN] == 1
    assert counts[ft.STATE_PENDING] == 1


def test_strip_marks_rows_stripped(app, repo, tmp_path, monkeypatch):
    repo.upsert_seen("/media/a.mkv", 10, 1.0, generation=1)
    repo.mark_probed("/media/a.mkv", ["spa"])
    monkeypatch.setattr(sw, "iter_video_files", lambda *a, **k: iter([]))
    monkeypatch.setattr(sw, "_strip_file", lambda path, keep, keep_und: ("/trash/a.bak", 5))
    result = sw.run_slice(str(tmp_path), CFG, budget_s=60, now_fn=FakeClock(), repo=repo)
    assert repo.counts_by_state()[ft.STATE_STRIPPED] == 1
    assert result["stripped_files"] == 1


def test_stop_request_ends_the_strip_slice_like_the_budget(app, repo, tmp_path, monkeypatch):
    """The stop arrives during the first remux.

    The real slice is driven; the second affected row must remain affected
    because the production strip loop joins cancellation into the same
    between-file boundary as the wall-clock budget.
    """
    import threading

    from services.scheduler import cancellation

    repo.upsert_seen("/media/a.mkv", 10, 1.0, generation=1)
    repo.upsert_seen("/media/b.mkv", 10, 1.0, generation=1)
    repo.mark_probed("/media/a.mkv", ["spa"])
    repo.mark_probed("/media/b.mkv", ["ita"])
    monkeypatch.setattr(sw, "iter_video_files", lambda *a, **k: iter([]))
    monkeypatch.setattr(sw, "_free_bytes", lambda root: 1_000 * 1024**3)
    _enable_foreign_track_tick(monkeypatch, str(tmp_path))

    event = threading.Event()
    stripped: list[str] = []

    def fake_strip(path, keep_languages, keep_und):
        stripped.append(path)
        event.set()  # the stop arrives while the first remux is in flight
        return ("/trash/a.bak", 5)

    monkeypatch.setattr(sw, "_strip_file", fake_strip)

    token = cancellation.activate(event)
    try:
        sw.foreign_track_sweep_tick()
    finally:
        cancellation.deactivate(token)

    assert stripped == ["/media/a.mkv"], (
        f"the sweep kept remuxing after being asked to stop: stripped {stripped}"
    )
    counts = repo.counts_by_state()
    assert counts[ft.STATE_STRIPPED] == 1
    assert counts[ft.STATE_AFFECTED] == 1


def test_disk_floor_pauses_the_sweep_and_fails_no_file(app, repo, tmp_path, monkeypatch):
    repo.upsert_seen("/media/a.mkv", 10, 1.0, generation=1)
    repo.mark_probed("/media/a.mkv", ["spa"])
    monkeypatch.setattr(sw, "iter_video_files", lambda *a, **k: iter([]))
    monkeypatch.setattr(sw, "_free_bytes", lambda root: 1)
    cfg = dict(CFG, min_free_gb=500)
    result = sw.run_slice(str(tmp_path), cfg, budget_s=60, now_fn=FakeClock(), repo=repo)
    assert result["paused_reason"]
    assert repo.counts_by_state().get(ft.STATE_FAILED, 0) == 0
    assert repo.counts_by_state()[ft.STATE_AFFECTED] == 1


def test_empty_keep_list_aborts_without_touching_anything(app, repo, tmp_path, monkeypatch):
    repo.upsert_seen("/media/a.mkv", 10, 1.0, generation=1)
    monkeypatch.setattr(sw, "iter_video_files", lambda *a, **k: iter([]))
    result = sw.run_slice(
        str(tmp_path), {"keep_languages": []}, budget_s=60, now_fn=FakeClock(), repo=repo
    )
    assert "keep" in (result["paused_reason"] or "").lower()
    assert repo.counts_by_state()[ft.STATE_PENDING] == 1


def test_config_change_resets_every_verdict(app, repo, tmp_path, monkeypatch):
    """A changed keep-list invalidates an already-stripped verdict — even a
    `stripped` row must come back into play, since narrowing the keep-list
    can make an already-cleaned file carry a foreign track again. Chaining
    means the reset row is re-probed within the same second slice, so what
    matters is that it no longer sits in `stripped`, not that it is caught
    mid-flight in `pending`. `_probe_file` is stubbed so that re-probe does
    not reach a real ffprobe."""
    monkeypatch.setattr(sw, "iter_video_files", lambda *a, **k: iter([]))
    monkeypatch.setattr(sw, "_probe_file", lambda path: {"streams": []})
    repo.upsert_seen("/media/a.mkv", 10, 1.0, generation=1)
    repo.mark_probed("/media/a.mkv", ["spa"])
    repo.claim_next_affected()
    repo.mark_stripped("/media/a.mkv")
    sw.run_slice(str(tmp_path), CFG, budget_s=60, now_fn=FakeClock(), repo=repo)
    sw.run_slice(
        str(tmp_path), dict(CFG, keep_languages=["de"]), budget_s=60, now_fn=FakeClock(), repo=repo
    )
    assert repo.counts_by_state().get(ft.STATE_STRIPPED, 0) == 0


def test_sweep_reaches_idle_when_nothing_is_left(app, repo, tmp_path, monkeypatch):
    monkeypatch.setattr(sw, "iter_video_files", lambda *a, **k: iter([]))
    result = sw.run_slice(str(tmp_path), CFG, budget_s=60, now_fn=FakeClock(), repo=repo)
    assert result["phase"] in (PHASE_IDLE, PHASE_ENUMERATE, PHASE_PROBE, PHASE_STRIP)
    result = sw.run_slice(str(tmp_path), CFG, budget_s=60, now_fn=FakeClock(), repo=repo)
    assert result["phase"] == PHASE_IDLE


def test_abandoned_stripping_rows_are_released_on_the_next_slice(app, repo, tmp_path, monkeypatch):
    repo.upsert_seen("/media/a.mkv", 10, 1.0, generation=1)
    repo.mark_probed("/media/a.mkv", ["spa"])
    repo.claim_next_affected()
    monkeypatch.setattr(sw, "iter_video_files", lambda *a, **k: iter([]))
    monkeypatch.setattr(sw, "_strip_file", lambda path, keep, keep_und: ("/trash/a.bak", 5))
    sw.run_slice(str(tmp_path), CFG, budget_s=60, now_fn=FakeClock(), repo=repo)
    assert repo.counts_by_state()[ft.STATE_STRIPPED] == 1


def test_one_slice_chains_enumerate_probe_and_strip_to_idle(app, repo, tmp_path, monkeypatch):
    """Pins the chaining policy so it cannot silently regress: `run_slice`
    bounds a tick by wall-clock budget, not by phase count. A single call
    over a one-file walk — with both `_probe_file` and `_strip_file`
    stubbed — must run enumerate, probe AND strip and land on `idle`,
    proving all three phases ran in this one tick."""
    monkeypatch.setattr(sw, "iter_video_files", lambda *a, **k: iter([("/media/a.mkv", 10, 1.0)]))
    monkeypatch.setattr(
        sw,
        "_probe_file",
        lambda path: {"streams": [{"codec_type": "subtitle", "tags": {"language": "spa"}}]},
    )
    monkeypatch.setattr(sw, "_strip_file", lambda path, keep, keep_und: ("/trash/a.bak", 5))
    result = sw.run_slice(str(tmp_path), CFG, budget_s=60, now_fn=FakeClock(), repo=repo)
    assert result["phase"] == PHASE_IDLE
    assert result["stripped_files"] == 1
    assert repo.counts_by_state()[ft.STATE_STRIPPED] == 1


# ---------------------------------------------------------------------------
# Global-settings inheritance for keep_languages / keep_und (finding 1).
#
# Mirrors cleanup_executors.execute_foreign_tracks: rules are created with
# config_json="{}", so an ABSENT key must inherit the global
# cleanup_foreign_tracks_* setting, or a freshly-seeded rule aborts forever.
# An EXPLICITLY empty/False value always wins over the global.
# ---------------------------------------------------------------------------


def test_absent_keep_und_inherits_the_global_true(app, repo, tmp_path, monkeypatch):
    repo.upsert_seen("/media/a.mkv", 10, 1.0, generation=1)
    monkeypatch.setattr(sw, "iter_video_files", lambda *a, **k: iter([]))
    monkeypatch.setattr(
        sw,
        "_probe_file",
        lambda path: {"streams": [{"codec_type": "subtitle", "tags": {"language": "und"}}]},
    )
    monkeypatch.setattr(
        "config.get_settings",
        lambda: SimpleNamespace(cleanup_foreign_tracks_keep_und=True),
    )
    cfg = {"keep_languages": ["de", "en"]}  # keep_und intentionally absent
    sw.run_slice(str(tmp_path), cfg, budget_s=60, now_fn=FakeClock(), repo=repo)
    counts = repo.counts_by_state()
    # A kept `und` track means the file is clean, not affected/stripped.
    assert counts.get(ft.STATE_CLEAN, 0) == 1
    assert counts.get(ft.STATE_AFFECTED, 0) == 0
    assert counts.get(ft.STATE_STRIPPED, 0) == 0


def test_explicit_keep_und_false_beats_a_true_global(app, repo, tmp_path, monkeypatch):
    repo.upsert_seen("/media/a.mkv", 10, 1.0, generation=1)
    monkeypatch.setattr(sw, "iter_video_files", lambda *a, **k: iter([]))
    monkeypatch.setattr(
        sw,
        "_probe_file",
        lambda path: {"streams": [{"codec_type": "subtitle", "tags": {"language": "und"}}]},
    )
    monkeypatch.setattr(sw, "_strip_file", lambda path, keep, keep_und: ("/trash/a.bak", 5))
    monkeypatch.setattr(
        "config.get_settings",
        lambda: SimpleNamespace(cleanup_foreign_tracks_keep_und=True),
    )
    cfg = {"keep_languages": ["de", "en"], "keep_und": False}
    sw.run_slice(str(tmp_path), cfg, budget_s=60, now_fn=FakeClock(), repo=repo)
    # An explicit False must strip the und track despite the True global —
    # chaining carries the now-affected file through to stripped.
    assert repo.counts_by_state()[ft.STATE_STRIPPED] == 1


def test_absent_keep_languages_inherits_the_global_list(app, repo, tmp_path, monkeypatch):
    repo.upsert_seen("/media/a.mkv", 10, 1.0, generation=1)
    monkeypatch.setattr(sw, "iter_video_files", lambda *a, **k: iter([]))
    monkeypatch.setattr(
        sw,
        "_probe_file",
        lambda path: {"streams": [{"codec_type": "subtitle", "tags": {"language": "spa"}}]},
    )
    monkeypatch.setattr(sw, "_strip_file", lambda path, keep, keep_und: ("/trash/a.bak", 5))
    monkeypatch.setattr(
        "config.get_settings",
        lambda: SimpleNamespace(
            cleanup_foreign_tracks_keep_languages=["de", "en"],
            cleanup_foreign_tracks_keep_und=True,
        ),
    )
    # A seeded rule's config_json is "{}" — no keep_languages key at all.
    result = sw.run_slice(str(tmp_path), {}, budget_s=60, now_fn=FakeClock(), repo=repo)
    assert result["paused_reason"] is None, "an absent key must inherit, not abort"
    assert repo.counts_by_state()[ft.STATE_STRIPPED] == 1


def test_explicit_empty_keep_languages_still_aborts_despite_a_global_list(
    app, repo, tmp_path, monkeypatch
):
    repo.upsert_seen("/media/a.mkv", 10, 1.0, generation=1)
    monkeypatch.setattr(sw, "iter_video_files", lambda *a, **k: iter([]))
    monkeypatch.setattr(
        "config.get_settings",
        lambda: SimpleNamespace(cleanup_foreign_tracks_keep_languages=["de", "en"]),
    )
    result = sw.run_slice(
        str(tmp_path), {"keep_languages": []}, budget_s=60, now_fn=FakeClock(), repo=repo
    )
    assert "keep" in (result["paused_reason"] or "").lower()
    assert repo.counts_by_state()[ft.STATE_PENDING] == 1


# ---------------------------------------------------------------------------
# A config change must not silently truncate an in-progress enumeration
# (finding 2).
# ---------------------------------------------------------------------------


def test_config_change_during_an_incomplete_enumeration_does_not_reach_idle_completed(
    app, repo, tmp_path, monkeypatch
):
    """An interrupted enumeration, followed by a config change before the
    walk finishes, must not let the slice reach `idle` with `completed_at`
    stamped — that would suppress re-enumeration for
    `foreign_track_sweep_rescan_days` and silently skip every file the walk
    never reached. Both slices see the same still-broken walk: the only way
    to reach `idle` at all would be by skipping straight from the reset to
    PROBE/STRIP without ever retrying ENUMERATE — which is exactly the bug
    this test pins."""

    def _explode(*a, **k):
        yield ("/media/a.mkv", 10, 1.0)
        raise OSError("share went away")

    monkeypatch.setattr(sw, "iter_video_files", _explode)
    # First slice: enumeration starts and is interrupted.
    sw.run_slice(str(tmp_path), CFG, budget_s=60, now_fn=FakeClock(), repo=repo)

    from services.foreign_tracks.state import load_state

    state = load_state()
    assert state.enumeration_complete is False
    assert state.completed_at is None

    # Second slice: config changes before the walk ever resumes, and the
    # share is still unreachable.
    result = sw.run_slice(
        str(tmp_path), dict(CFG, keep_languages=["de"]), budget_s=60, now_fn=FakeClock(), repo=repo
    )
    assert result["phase"] == PHASE_ENUMERATE
    assert load_state().completed_at is None


# ---------------------------------------------------------------------------
# The probe phase must degrade gracefully instead of parking the backlog
# `failed` (finding 3).
# ---------------------------------------------------------------------------


def test_unreachable_media_root_pauses_the_probe_and_fails_no_row(app, repo, tmp_path, monkeypatch):
    """Mirrors cleanup_executors' C0-3 guard: an NFS blip must pause the
    sweep, not make every pending row look genuinely broken."""
    repo.upsert_seen("/media/a.mkv", 10, 1.0, generation=1)
    monkeypatch.setattr(sw, "iter_video_files", lambda *a, **k: iter([]))
    missing_root = str(tmp_path / "does-not-exist")
    result = sw.run_slice(missing_root, CFG, budget_s=60, now_fn=FakeClock(), repo=repo)
    assert result["paused_reason"]
    counts = repo.counts_by_state()
    assert counts.get(ft.STATE_FAILED, 0) == 0
    assert counts[ft.STATE_PENDING] == 1


def test_ten_consecutive_probe_failures_pause_the_slice_with_rows_left_unparked(
    app, repo, tmp_path, monkeypatch
):
    for i in range(12):
        repo.upsert_seen(f"/media/{i}.mkv", 10, 1.0, generation=1)
    monkeypatch.setattr(sw, "iter_video_files", lambda *a, **k: iter([]))

    def _always_fails(path):
        raise RuntimeError("ffprobe failed: simulated NFS blip")

    monkeypatch.setattr(sw, "_probe_file", _always_fails)
    result = sw.run_slice(str(tmp_path), CFG, budget_s=60, now_fn=FakeClock(), repo=repo)
    assert result["paused_reason"]
    counts = repo.counts_by_state()
    # None of the 12 rows reach `failed` — each was only attempted once, well
    # under MAX_ATTEMPTS — the circuit breaker stops the tick, not the file.
    assert counts.get(ft.STATE_FAILED, 0) == 0
    assert counts[ft.STATE_PENDING] == 12


def test_a_single_probe_failure_among_successes_does_not_trip_the_breaker(
    app, repo, tmp_path, monkeypatch
):
    """The consecutive-failure counter resets on any success, so one bad
    file scattered among healthy ones must not pause the sweep — it still
    exhausts its own MAX_ATTEMPTS retries and parks `failed` (the frozen
    test clock lets the slice re-fetch and retry it to exhaustion within
    this one call), which is the pre-existing per-file mechanism, distinct
    from the new systemic circuit breaker."""
    for i in range(11):
        repo.upsert_seen(f"/media/{i}.mkv", 10, 1.0, generation=1)

    def _probe(path):
        if path == "/media/5.mkv":
            raise RuntimeError("transient blip")
        return {"streams": []}

    monkeypatch.setattr(sw, "iter_video_files", lambda *a, **k: iter([]))
    monkeypatch.setattr(sw, "_probe_file", _probe)
    result = sw.run_slice(str(tmp_path), CFG, budget_s=60, now_fn=FakeClock(), repo=repo)
    assert result["paused_reason"] is None
    counts = repo.counts_by_state()
    assert counts[ft.STATE_CLEAN] == 10
    assert counts.get(ft.STATE_FAILED, 0) == 1


# ---------------------------------------------------------------------------
# `run_slice` is the sweep's serialisation point (finding 5).
# ---------------------------------------------------------------------------


def test_concurrent_run_slice_raises_sweep_busy_error(app, repo, tmp_path, monkeypatch):
    monkeypatch.setattr(sw, "iter_video_files", lambda *a, **k: iter([]))
    sw._sweep_lock.acquire()
    try:
        with pytest.raises(sw.SweepBusyError):
            sw.run_slice(str(tmp_path), CFG, budget_s=60, now_fn=FakeClock(), repo=repo)
    finally:
        sw._sweep_lock.release()


# ---------------------------------------------------------------------------
# The strip phase needs the same media-root reachability guard as the probe
# phase — a sweep can resume directly at PHASE_STRIP on a later tick, never
# passing through probe's guard at all (out-of-scope for finding 3, pulled
# in deliberately in re-review).
# ---------------------------------------------------------------------------


def test_unreachable_media_root_pauses_the_strip_and_fails_no_row(app, repo, tmp_path, monkeypatch):
    """Mirrors the probe-phase guard, but for a sweep that resumes directly
    at PHASE_STRIP — persisted state from a prior tick, not something this
    call derives — so it must not park the affected backlog failed just
    because the mount died between ticks."""
    from services.foreign_tracks.state import SweepState, config_hash, save_state

    repo.upsert_seen("/media/a.mkv", 10, 1.0, generation=1)
    repo.mark_probed("/media/a.mkv", ["spa"])  # AFFECTED
    monkeypatch.setattr(sw, "iter_video_files", lambda *a, **k: iter([]))

    missing_root = str(tmp_path / "does-not-exist")
    # Persist state already at PHASE_STRIP with a matching config_hash, so
    # this slice resumes straight into _strip_phase without ever visiting
    # ENUMERATE or PROBE.
    save_state(
        SweepState(
            generation=1,
            phase=PHASE_STRIP,
            enumeration_complete=True,
            config_hash=config_hash(CFG, missing_root),
        )
    )

    result = sw.run_slice(missing_root, CFG, budget_s=60, now_fn=FakeClock(), repo=repo)
    assert result["phase"] == PHASE_STRIP
    assert result["paused_reason"]
    counts = repo.counts_by_state()
    assert counts.get(ft.STATE_FAILED, 0) == 0
    assert counts[ft.STATE_AFFECTED] == 1


# ---------------------------------------------------------------------------
# config_hash must reflect the RESOLVED keep_languages/keep_und, not the raw
# rule config, or a config_json="{}" rule can never notice a global setting
# change (the review's follow-up to finding 1).
# ---------------------------------------------------------------------------


def test_global_keep_languages_change_resets_cached_verdicts_for_an_empty_rule_config(
    app, repo, tmp_path, monkeypatch
):
    """A config_json="{}" rule has no keep_languages of its own — the global
    setting is the ONLY control. Changing it between two slices must still
    invalidate cached verdicts: hashing the raw (empty) rule config would
    never notice the change, and a file probed clean under the old globals
    would stay clean forever."""
    repo.upsert_seen("/media/a.mkv", 10, 1.0, generation=1)
    monkeypatch.setattr(sw, "iter_video_files", lambda *a, **k: iter([]))
    monkeypatch.setattr(
        sw,
        "_probe_file",
        lambda path: {"streams": [{"codec_type": "subtitle", "tags": {"language": "spa"}}]},
    )
    monkeypatch.setattr(sw, "_strip_file", lambda path, keep, keep_und: ("/trash/a.bak", 5))

    monkeypatch.setattr(
        "config.get_settings",
        lambda: SimpleNamespace(
            cleanup_foreign_tracks_keep_languages=["spa"],  # spa is kept for now
            cleanup_foreign_tracks_keep_und=True,
        ),
    )
    sw.run_slice(str(tmp_path), {}, budget_s=60, now_fn=FakeClock(), repo=repo)
    assert repo.counts_by_state()[ft.STATE_CLEAN] == 1

    # Operator narrows the global keep-list; the rule's config is still {}.
    monkeypatch.setattr(
        "config.get_settings",
        lambda: SimpleNamespace(
            cleanup_foreign_tracks_keep_languages=["de", "en"],
            cleanup_foreign_tracks_keep_und=True,
        ),
    )
    sw.run_slice(str(tmp_path), {}, budget_s=60, now_fn=FakeClock(), repo=repo)
    counts = repo.counts_by_state()
    assert counts.get(ft.STATE_CLEAN, 0) == 0
    assert counts.get(ft.STATE_STRIPPED, 0) == 1
