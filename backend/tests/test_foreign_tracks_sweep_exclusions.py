"""Final-review I4 + I7 at the sweep: failing ids are named, and folders of
series/movies with ``cleanup_foreign_tracks=False`` are never stripped —
in the probe phase AND in the strip phase."""

import os

from db.models import foreign_tracks as ft
from services.foreign_tracks.policy import OverrideSet

CFG = {"keep_languages": ["de", "en"], "keep_und": True}


def _repo():
    from db.repositories.foreign_track_scan import ForeignTrackScanRepository

    return ForeignTrackScanRepository()


def test_the_paused_reason_names_the_failing_ids(app_ctx, tmp_path, monkeypatch):
    from services.foreign_tracks import sweep as sw

    repo = _repo()
    repo.upsert_seen("/media/a.mkv", 10, 1.0, generation=1)
    repo.mark_probed("/media/a.mkv", ["spa"])  # affected
    monkeypatch.setattr(sw, "iter_video_files", lambda *a, **k: iter([]))
    monkeypatch.setattr(
        sw,
        "override_paths",
        lambda: OverrideSet(pairs=[], excluded=[], complete=False, failed=("series 21", "movie 4")),
    )
    monkeypatch.setattr(sw, "_strip_file", lambda *a, **kw: ("/trash.bak", 5))

    result = sw.run_slice(str(tmp_path), CFG, budget_s=60, repo=repo)

    assert "series 21" in result["paused_reason"]
    assert "movie 4" in result["paused_reason"]


def test_a_file_in_an_excluded_folder_is_probed_clean_without_ffprobe(
    app_ctx, tmp_path, monkeypatch
):
    from services.foreign_tracks import sweep as sw

    repo = _repo()
    folder = str(tmp_path / "Off")
    path = os.path.join(folder, "e1.mkv")
    repo.upsert_seen(path, 10, 1.0, generation=1)
    monkeypatch.setattr(sw, "iter_video_files", lambda *a, **k: iter([]))
    monkeypatch.setattr(
        sw,
        "override_paths",
        lambda: OverrideSet(pairs=[], excluded=[folder], complete=True, failed=()),
    )
    probed = []
    monkeypatch.setattr(
        sw,
        "_probe_file",
        lambda p: (
            probed.append(p)
            or {"streams": [{"index": 1, "codec_type": "subtitle", "tags": {"language": "spa"}}]}
        ),
    )
    stripped = []
    monkeypatch.setattr(sw, "_strip_file", lambda *a, **kw: stripped.append(a) or ("/b", 5))

    sw.run_slice(str(tmp_path), CFG, budget_s=60, repo=repo)

    assert probed == []
    assert stripped == []
    assert repo.counts_by_state().get(ft.STATE_CLEAN) == 1


def test_an_affected_file_in_a_now_excluded_folder_is_never_stripped(
    app_ctx, tmp_path, monkeypatch
):
    """A row probed affected before the series was switched off must not be
    rewritten when the strip phase reaches it."""
    from services.foreign_tracks import sweep as sw

    repo = _repo()
    folder = str(tmp_path / "Off")
    path = os.path.join(folder, "e1.mkv")
    repo.upsert_seen(path, 10, 1.0, generation=1)
    repo.mark_probed(path, ["spa"])  # affected
    monkeypatch.setattr(sw, "iter_video_files", lambda *a, **k: iter([]))
    monkeypatch.setattr(
        sw,
        "override_paths",
        lambda: OverrideSet(pairs=[], excluded=[folder], complete=True, failed=()),
    )
    stripped = []
    monkeypatch.setattr(sw, "_strip_file", lambda *a, **kw: stripped.append(a) or ("/b", 5))

    sw.run_slice(str(tmp_path), CFG, budget_s=60, repo=repo)

    assert stripped == []
    counts = repo.counts_by_state()
    assert counts.get(ft.STATE_AFFECTED, 0) == 0
    assert counts.get(ft.STATE_CLEAN) == 1


def test_a_file_outside_the_excluded_folder_is_still_stripped(app_ctx, tmp_path, monkeypatch):
    from services.foreign_tracks import sweep as sw

    repo = _repo()
    path = str(tmp_path / "On" / "e1.mkv")
    repo.upsert_seen(path, 10, 1.0, generation=1)
    repo.mark_probed(path, ["spa"])  # affected
    monkeypatch.setattr(sw, "iter_video_files", lambda *a, **k: iter([]))
    monkeypatch.setattr(
        sw,
        "override_paths",
        lambda: OverrideSet(pairs=[], excluded=[str(tmp_path / "Off")], complete=True, failed=()),
    )
    stripped = []
    monkeypatch.setattr(sw, "_strip_file", lambda *a, **kw: stripped.append(a) or ("/b", 5))

    sw.run_slice(str(tmp_path), CFG, budget_s=60, repo=repo)

    assert len(stripped) == 1


def test_the_sweep_is_not_gated_on_the_global_download_cleanup_default(
    app_ctx, tmp_path, monkeypatch
):
    """Ruling I7 (revised): the sweep has its own switch; the download-time
    cleanup default being off must not stop it."""
    from config import get_settings
    from services.foreign_tracks import sweep as sw

    monkeypatch.setattr(get_settings(), "cleanup_foreign_tracks_default", False)
    repo = _repo()
    path = str(tmp_path / "e1.mkv")
    repo.upsert_seen(path, 10, 1.0, generation=1)
    repo.mark_probed(path, ["spa"])  # affected
    monkeypatch.setattr(sw, "iter_video_files", lambda *a, **k: iter([]))
    monkeypatch.setattr(
        sw, "override_paths", lambda: OverrideSet(pairs=[], excluded=[], complete=True, failed=())
    )
    stripped = []
    monkeypatch.setattr(sw, "_strip_file", lambda *a, **kw: stripped.append(a) or ("/b", 5))

    sw.run_slice(str(tmp_path), CFG, budget_s=60, repo=repo)

    assert len(stripped) == 1
