"""I6: the enumeration walk (754 s on prod) and the temp-file walk before it
logged nothing, and the tick summary left out why a sweep was paused."""

from __future__ import annotations

import logging
from types import SimpleNamespace

from services.foreign_tracks import sweep as sw
from services.foreign_tracks.state import SweepState


class _Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def _fake_repo():
    seen = []
    return SimpleNamespace(
        upsert_seen=lambda path, size, mtime, generation: seen.append(path),
        prune_stale=lambda generation: 0,
        seen=seen,
    )


def _run_enumerate(monkeypatch, files, clock, step_s=0.0):
    monkeypatch.setattr(sw, "save_state", lambda state: None)
    monkeypatch.setattr(sw, "sweep_stale_temp_files", lambda *a, **k: 2)
    monkeypatch.setattr(
        "config.get_settings", lambda: SimpleNamespace(foreign_track_min_file_age_s=0)
    )
    monkeypatch.setattr(sw, "_monotonic", clock)

    def _walk(*_a, **_k):
        for path in files:
            clock.t += step_s
            yield path, 1, 1.0

    monkeypatch.setattr(sw, "iter_video_files", _walk)
    state = SweepState(generation=4)
    sw._enumerate("/media", {}, state, _fake_repo())
    return state


def _messages(caplog):
    return [r.getMessage() for r in caplog.records if r.name == sw.logger.name]


def test_walk_logs_start_and_completion(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=sw.logger.name)

    _run_enumerate(monkeypatch, [f"/media/{i}.mkv" for i in range(3)], _Clock())

    msgs = _messages(caplog)
    assert any("temp-file cleanup started" in m for m in msgs)
    assert any("temp-file cleanup complete" in m and "removed=2" in m for m in msgs)
    assert any("enumeration started gen=5 root=/media" in m for m in msgs)
    assert any("enumeration complete files=3" in m for m in msgs)


def test_walk_reports_progress_by_file_count(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=sw.logger.name)
    monkeypatch.setattr(sw, "_ENUM_PROGRESS_FILES", 2)

    _run_enumerate(monkeypatch, [f"/media/{i}.mkv" for i in range(5)], _Clock())

    progress = [m for m in _messages(caplog) if "enumeration progress" in m]
    assert len(progress) == 2
    assert "files=2" in progress[0]


def test_walk_reports_progress_by_elapsed_time(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=sw.logger.name)

    _run_enumerate(monkeypatch, ["/media/a.mkv", "/media/b.mkv"], _Clock(), step_s=61.0)

    progress = [m for m in _messages(caplog) if "enumeration progress" in m]
    assert len(progress) == 2
    assert "elapsed=" in progress[0]


def test_tick_summary_names_the_paused_reason(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=sw.logger.name)
    monkeypatch.setattr(
        "config.get_settings",
        lambda: SimpleNamespace(
            foreign_track_sweep_enabled=True, foreign_track_sweep_budget_s=60, media_path="/m"
        ),
    )
    monkeypatch.setattr(sw, "_find_rule", lambda repo: {"config_json": {}})
    monkeypatch.setattr("db.repositories.cleanup.CleanupRepository", lambda: None)
    monkeypatch.setattr(
        sw,
        "run_slice",
        lambda *a, **k: {
            "phase": "enumerate",
            "probed": 0,
            "stripped_files": 0,
            "pending": 0,
            "affected": 0,
            "paused_reason": "low disk space",
        },
    )

    sw.foreign_track_sweep_tick()

    summary = [m for m in _messages(caplog) if m.startswith("foreign_track_sweep: phase=")]
    assert summary and "paused_reason=low disk space" in summary[0]
