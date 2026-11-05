"""A foreign-track walk that is stopped must still get somewhere (Forgejo #68).

Every run started a new generation and walked from the root; the prune and
the probe phase only follow a completed walk. A walk longer than the job's
ceiling — a Raspberry Pi on an SD card, a slow network mount, a very large
library — was stopped every time and never finished.
"""

import threading

from services.foreign_tracks import sweep as sw
from services.foreign_tracks.state import load_state
from services.scheduler import cancellation
from tests.test_foreign_tracks_sweep_tick import CFG, FakeClock
from tests.test_foreign_tracks_sweep_tick import app as app  # noqa: F401 — fixture
from tests.test_foreign_tracks_sweep_tick import repo as repo  # noqa: F401 — fixture

FILES = [(f"/media/{n}.mkv", 10, 1.0) for n in "abcd"]


def _slice(tmp_path, repo, monkeypatch, *, stop_after=None):
    """One slice over FILES; asked to stop once ``stop_after`` files were yielded."""
    event = threading.Event()
    upserted = []
    real_upsert = repo.upsert_seen

    def upsert(path, *a, **k):
        upserted.append(path)
        return real_upsert(path, *a, **k)

    def walk(*a, **k):
        for n, item in enumerate(FILES, 1):
            yield item
            if stop_after is not None and n >= stop_after:
                event.set()

    monkeypatch.setattr(repo, "upsert_seen", upsert)
    monkeypatch.setattr(sw, "iter_video_files", walk)
    monkeypatch.setattr(sw, "_probe_file", lambda path: {"streams": []})
    token = cancellation.activate(event)
    try:
        sw.run_slice(str(tmp_path), CFG, budget_s=60, now_fn=FakeClock(), repo=repo)
    finally:
        cancellation.deactivate(token)
    return upserted


def test_a_stopped_walk_keeps_its_generation(app, repo, tmp_path, monkeypatch):
    _slice(tmp_path, repo, monkeypatch, stop_after=2)
    generation = load_state().generation
    _slice(tmp_path, repo, monkeypatch)

    assert load_state().generation == generation
    assert load_state().enumeration_complete


def test_the_next_walk_only_records_what_the_last_one_did_not(app, repo, tmp_path, monkeypatch):
    _slice(tmp_path, repo, monkeypatch, stop_after=2)
    upserted = _slice(tmp_path, repo, monkeypatch)

    assert upserted == ["/media/c.mkv", "/media/d.mkv"]


def test_the_finished_walk_prunes_only_files_no_part_saw(app, repo, tmp_path, monkeypatch):
    repo.upsert_seen("/media/gone.mkv", 10, 1.0, generation=0)
    _slice(tmp_path, repo, monkeypatch, stop_after=2)
    _slice(tmp_path, repo, monkeypatch)

    from db.models.foreign_tracks import ForeignTrackScan

    paths = {r.path for r in repo.session.query(ForeignTrackScan).all()}
    assert paths == {f[0] for f in FILES}


def test_rows_under_an_unreadable_folder_survive_the_prune(app, repo, tmp_path, monkeypatch):
    """os.walk skips a folder it cannot list; its files are not deleted ones."""
    repo.upsert_seen("/media/flaky/x.mkv", 10, 1.0, generation=0)
    repo.upsert_seen("/media/gone.mkv", 10, 1.0, generation=0)

    def walk(*a, unreadable=None, **k):
        unreadable.append("/media/flaky")
        yield from FILES

    monkeypatch.setattr(sw, "iter_video_files", walk)
    monkeypatch.setattr(sw, "_probe_file", lambda path: {"streams": []})
    sw.run_slice(str(tmp_path), CFG, budget_s=60, now_fn=FakeClock(), repo=repo)

    from db.models.foreign_tracks import ForeignTrackScan

    paths = {r.path for r in repo.session.query(ForeignTrackScan).all()}
    assert "/media/flaky/x.mkv" in paths
    assert "/media/gone.mkv" not in paths


def test_safe_walk_reports_folders_it_cannot_read(tmp_path):
    from services.cleanup_executors import _safe_walk

    locked = tmp_path / "locked"
    locked.mkdir()
    (locked / "a.mkv").write_bytes(b"x")
    locked.chmod(0)
    unreadable: list[str] = []
    try:
        list(_safe_walk(str(tmp_path), unreadable))
    finally:
        locked.chmod(0o755)

    assert unreadable == [str(locked)]
