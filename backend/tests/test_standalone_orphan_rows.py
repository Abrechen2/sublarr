"""No standalone row outlives the title it belongs to.

Found by the 1.18.0-rc.6 end-to-end test (R5): deleting a watched folder while
its scan was processing a title left that title's wanted rows behind, still
``wanted`` and pointing at a deleted standalone series. The route had already
deleted the title, the scanner kept writing its rows, and the scanner's prune
only looks at titles, so it found nothing to cascade from.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
import sqlalchemy as sa

_NOW = datetime(2026, 10, 1, tzinfo=UTC)


class _Resolver:
    def resolve_series(self, title, year=None, is_anime=False):
        return {"title": title.title(), "metadata_source": "filename"}

    def resolve_movie(self, title, year=None):
        return {"title": title, "metadata_source": "filename"}


@pytest.fixture
def api(app_ctx, monkeypatch):
    monkeypatch.setattr("routes.standalone.folders._hot_reload_standalone", lambda: None)
    monkeypatch.setattr("routes.standalone.folders._media_path", lambda: "")
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: None)
    monkeypatch.setattr("radarr_client.get_radarr_client", lambda *a, **kw: None)
    return app_ctx.test_client()


@pytest.fixture
def scanner(app_ctx):
    from standalone.scanner import StandaloneScanner

    with patch("standalone.scanner._probe_embedded_tracks", return_value=None):
        yield StandaloneScanner(metadata_resolver=_Resolver())


def _show(root, name="Alpha", episodes=3):
    season = root / name / "Season 1"
    season.mkdir(parents=True)
    for n in range(1, episodes + 1):
        (season / f"{name} - S01E0{n} [1080p].mkv").write_bytes(b"\x00")
    return root


def _folder(path) -> int:
    from db.standalone import upsert_watched_folder

    return upsert_watched_folder(path=str(path))


def _count(table: str) -> int:
    from extensions import db

    return db.session.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar()


def _once_before(scanner, method: str, action):
    """Run ``action`` once, right before the scanner's first call of ``method``."""
    real = getattr(scanner, method)
    done = []

    def hook(*args, **kwargs):
        if not done:
            done.append(True)
            action()
        return real(*args, **kwargs)

    return patch.object(scanner, method, side_effect=hook)


def _delete_folder(api, fid):
    def delete():
        assert api.delete(f"/api/v1/standalone/folders/{fid}").status_code == 200

    return delete


# ---------------------------------------------------------------------------
# (a) the scanner does not write rows for a title deleted under it
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sweep", [True, False], ids=["with-sweep", "scanner-only"])
def test_a_title_deleted_before_its_wanted_rows_gets_none(api, scanner, tmp_path, sweep):
    fid = _folder(_show(tmp_path / "lib"))
    if not sweep:
        # The scanner's own re-check must hold without the safety net.
        patcher = patch("services.standalone_manager.sweep_orphan_standalone_rows", return_value={})
        patcher.start()
    try:
        with _once_before(scanner, "_get_target_languages", _delete_folder(api, fid)):
            scanner.scan_all_folders()
    finally:
        if not sweep:
            patcher.stop()

    assert _count("standalone_series") == 0
    assert _count("wanted_items") == 0
    assert _count("standalone_episodes") == 0


def test_a_title_deleted_before_its_episode_ids_gets_none(api, scanner, tmp_path):
    fid = _folder(_show(tmp_path / "lib"))

    with _once_before(scanner, "_record_episode_ids", _delete_folder(api, fid)):
        scanner.scan_all_folders()

    assert _count("standalone_series") == 0
    assert _count("standalone_episodes") == 0
    assert _count("wanted_items") == 0


def test_a_movie_deleted_before_its_wanted_rows_gets_none(api, scanner, tmp_path):
    lib = tmp_path / "lib"
    (lib / "Gamma (2001)").mkdir(parents=True)
    (lib / "Gamma (2001)" / "Gamma (2001).mkv").write_bytes(b"\x00")
    fid = _folder(lib)

    with _once_before(scanner, "_get_target_languages", _delete_folder(api, fid)):
        scanner.scan_all_folders()

    assert _count("standalone_movies") == 0
    assert _count("wanted_items") == 0


# ---------------------------------------------------------------------------
# (b) the orphan sweep
# ---------------------------------------------------------------------------


def _wanted(file_path: str | None = None, **ids) -> int:
    from db.models.core import WantedItem
    from extensions import db

    row = WantedItem(
        item_type="episode",
        file_path=file_path or f"/media/x/{len(ids)}-{sorted(ids.items())}.mkv",
        status="wanted",
        added_at=_NOW,
        updated_at=_NOW,
        instance_name="standalone" if ids else "sonarr",
        **ids,
    )
    db.session.add(row)
    db.session.commit()
    return row.id


def _series_row(title="Kept") -> int:
    from db.models.standalone import StandaloneSeries
    from extensions import db

    row = StandaloneSeries(
        title=title, folder_path=f"/media/{title}", created_at=_NOW, updated_at=_NOW
    )
    db.session.add(row)
    db.session.commit()
    return row.id


def _movie_row(title="Kept Film") -> int:
    from db.models.standalone import StandaloneMovie
    from extensions import db

    row = StandaloneMovie(
        title=title, file_path=f"/media/{title}.mkv", created_at=_NOW, updated_at=_NOW
    )
    db.session.add(row)
    db.session.commit()
    return row.id


def _episode_row(series_id: int, path: str) -> int:
    from db.models.standalone import StandaloneEpisode
    from extensions import db

    row = StandaloneEpisode(
        standalone_series_id=series_id, file_path=path, created_at=_NOW, updated_at=_NOW
    )
    db.session.add(row)
    db.session.commit()
    return row.id


def _finding(episode_id) -> int:
    from db.models.core import SubtitleHealthFinding
    from extensions import db

    row = SubtitleHealthFinding(
        episode_id=episode_id,
        target_kind="sidecar",
        target_path=f"/media/x/{episode_id}.srt",
        issue_type="encoding",
        severity="warning",
        detected_at=_NOW,
    )
    db.session.add(row)
    db.session.commit()
    return row.id


def _ids(table: str) -> set[int]:
    from extensions import db

    return {r[0] for r in db.session.execute(sa.text(f"SELECT id FROM {table}"))}


def test_the_sweep_removes_only_rows_of_titles_that_are_gone(app_ctx):
    from services.standalone_manager import sweep_orphan_standalone_rows

    sid = _series_row()
    mid = _movie_row()
    arr_row = _wanted(sonarr_series_id=7, sonarr_episode_id=70)
    plain_row = _wanted()  # no source id at all: never touched
    kept_series = _wanted(standalone_series_id=sid)
    kept_movie = _wanted(standalone_movie_id=mid)
    gone_series = _wanted(standalone_series_id=sid + 100)
    gone_movie = _wanted(standalone_movie_id=mid + 100)

    kept_ep = _episode_row(sid, "/media/Kept/e1.mkv")
    gone_ep = _episode_row(sid + 100, "/media/Gone/e1.mkv")
    kept_finding = _finding(-kept_ep)
    gone_ep_finding = _finding(-gone_ep)  # its episode is an orphan itself
    missing_ep_finding = _finding(-(gone_ep + 50))
    sonarr_finding = _finding(4242)
    null_finding = _finding(None)

    result = sweep_orphan_standalone_rows()

    assert _ids("wanted_items") == {arr_row, plain_row, kept_series, kept_movie}
    assert gone_series not in _ids("wanted_items") and gone_movie not in _ids("wanted_items")
    assert _ids("standalone_episodes") == {kept_ep}
    assert _ids("subtitle_health_findings") == {kept_finding, sonarr_finding, null_finding}
    assert gone_ep_finding not in _ids("subtitle_health_findings")
    assert missing_ep_finding not in _ids("subtitle_health_findings")
    assert result == {"wanted_items": 2, "standalone_episodes": 1, "subtitle_health_findings": 2}

    # Idempotent: nothing left to remove.
    assert sweep_orphan_standalone_rows() == {
        "wanted_items": 0,
        "standalone_episodes": 0,
        "subtitle_health_findings": 0,
    }


def test_every_scan_ends_with_the_sweep(scanner, tmp_path):
    lib = _show(tmp_path / "lib", episodes=1)
    _folder(lib)
    # On disk, so the missing-file cleanup does not take it first.
    on_disk = next(lib.rglob("*.mkv"))
    orphan = _wanted(file_path=str(on_disk) + ".orphan", standalone_series_id=9999)
    (lib / "Alpha" / "Season 1" / (on_disk.name + ".orphan")).write_bytes(b"\x00")

    scanner.scan_all_folders()

    assert orphan not in _ids("wanted_items")
    assert _count("standalone_series") == 1


def test_a_folder_delete_runs_the_sweep(api, tmp_path):
    fid = _folder(tmp_path)
    orphan = _wanted(standalone_movie_id=9999)

    assert api.delete(f"/api/v1/standalone/folders/{fid}").status_code == 200

    assert orphan not in _ids("wanted_items")


def test_a_folder_move_runs_the_sweep(api, tmp_path):
    old = tmp_path / "old"
    new = tmp_path / "new"
    old.mkdir()
    new.mkdir()
    fid = _folder(old)
    orphan = _wanted(standalone_series_id=9999)

    assert api.put(f"/api/v1/standalone/folders/{fid}", json={"path": str(new)}).status_code == 200

    assert orphan not in _ids("wanted_items")
