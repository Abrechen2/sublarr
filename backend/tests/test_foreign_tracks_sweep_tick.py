"""Tests for the batched foreign-track sweep state machine."""

import os

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
    every file it never reached look deleted."""
    repo.upsert_seen("/media/old.mkv", 10, 1.0, generation=1)

    def _explode(*a, **k):
        yield ("/media/a.mkv", 10, 1.0)
        raise OSError("share went away")

    monkeypatch.setattr(sw, "iter_video_files", _explode)
    sw.run_slice(str(tmp_path), CFG, budget_s=60, now_fn=FakeClock(), repo=repo)
    paths = {r.path for r in repo.next_pending(limit=10)}
    assert "/media/old.mkv" in paths


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


def test_strip_marks_rows_stripped(app, repo, tmp_path, monkeypatch):
    repo.upsert_seen("/media/a.mkv", 10, 1.0, generation=1)
    repo.mark_probed("/media/a.mkv", ["spa"])
    monkeypatch.setattr(sw, "iter_video_files", lambda *a, **k: iter([]))
    monkeypatch.setattr(sw, "_strip_file", lambda path, keep, keep_und: ("/trash/a.bak", 5))
    result = sw.run_slice(str(tmp_path), CFG, budget_s=60, now_fn=FakeClock(), repo=repo)
    assert repo.counts_by_state()[ft.STATE_STRIPPED] == 1
    assert result["stripped_files"] == 1


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
