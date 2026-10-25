"""Standalone paths must resolve inside ``media_path`` as well as their series folder.

Codex review of 1.18.0, finding 2: the containment check compared a standalone
episode only against its series folder, and that folder can itself be a
symlink out of the media tree (``/media/Show -> /outside/Show``):
``is_safe_path`` resolves both sides to ``/outside/Show`` and the check passes,
so search, download, health scans and the sweep's auto-fix worked on files
outside every allowed root. Since 1.18 watched folders must sit inside
``media_path`` anyway, so every standalone path is now also checked against
``media_path``, resolved independently.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

_NOW = datetime(2026, 10, 1, tzinfo=UTC)


class _Result:
    def __init__(self, episode_id):
        self.episode_id = episode_id
        self.issues = []

    def to_dict(self):
        return {"episode_id": self.episode_id, "issues": []}


@pytest.fixture
def media(app_ctx, tmp_path, monkeypatch):
    from config import reload_settings

    root = tmp_path / "media"
    root.mkdir()
    (tmp_path / "outside").mkdir()
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", str(root))
    reload_settings()
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: None)
    monkeypatch.setattr("services.subtitle_health.series_scan.get_sonarr_client", lambda: None)
    monkeypatch.setattr("services.subtitle_health.sweep.get_sonarr_client", lambda: None)
    return root


def _episode_file(folder) -> str:
    season = folder / "Season 1"
    season.mkdir(parents=True)
    video = season / "Show - S01E01.mkv"
    video.write_bytes(b"\x00")
    return str(video)


def _series(folder_path: str) -> int:
    from db.models.standalone import StandaloneSeries
    from extensions import db

    row = StandaloneSeries(title="Show", folder_path=folder_path, created_at=_NOW, updated_at=_NOW)
    db.session.add(row)
    db.session.commit()
    return row.id


def _episode_row(series_id: int, path: str) -> int:
    from db.repositories.standalone_episodes import StandaloneEpisodeRepository

    return StandaloneEpisodeRepository().upsert_episode(series_id, path, 1, 1)["id"]


def _legacy_wanted_row(series_id: int, path: str) -> int:
    from db.wanted import upsert_wanted_item

    item_id, _ = upsert_wanted_item(
        item_type="episode",
        file_path=path,
        title="Show -- S01E01",
        season_episode="S01E01",
        missing_languages=["de"],
        target_language="de",
        instance_name="standalone",
        standalone_series_id=series_id,
    )
    return item_id


@pytest.fixture
def escaped(media, tmp_path):
    """``media/Show`` is a symlink to ``outside/Show``."""
    real = tmp_path / "outside" / "Show"
    _episode_file(real)
    link = media / "Show"
    os.symlink(real, link)
    video = str(link / "Season 1" / "Show - S01E01.mkv")
    sid = _series(str(link))
    return sid, _episode_row(sid, video), video


@pytest.fixture
def inside(media):
    """``media/Show`` is a symlink to ``media/library/Show``: stays inside."""
    real = media / "library" / "Show"
    _episode_file(real)
    link = media / "Show"
    os.symlink(real, link)
    video = str(link / "Season 1" / "Show - S01E01.mkv")
    sid = _series(str(link))
    return sid, _episode_row(sid, video), video


# --- path resolution: search / download / tracks -------------------------


def test_series_folder_symlinked_outside_media_is_refused(escaped):
    from services.standalone_episode import (
        StandaloneEpisodeNotFoundError,
        resolve_standalone_episode_file,
        resolve_standalone_episode_wanted_id,
    )
    from services.standalone_library import episode_path_in_series

    sid, eid, video = escaped
    assert episode_path_in_series(video, sid) is None
    assert resolve_standalone_episode_file(-eid) is None
    with pytest.raises(StandaloneEpisodeNotFoundError):
        resolve_standalone_episode_wanted_id(-eid)


def test_legacy_paths_outside_media_are_refused(escaped):
    from services.standalone_episode import resolve_standalone_episode_file

    sid, _eid, video = escaped
    legacy_id = _legacy_wanted_row(sid, video)
    assert resolve_standalone_episode_file(legacy_id) is None
    # 1.17.3 stand-in id with the file_path fallback.
    assert resolve_standalone_episode_file(-9999, file_path=video) is None


def test_symlink_staying_inside_media_still_works(inside):
    from services.standalone_episode import (
        resolve_standalone_episode_file,
        resolve_standalone_episode_wanted_id,
    )

    sid, eid, video = inside
    assert resolve_standalone_episode_file(-eid) == video
    assert resolve_standalone_episode_wanted_id(-eid) > 0
    legacy_id = _legacy_wanted_row(sid, video)
    assert resolve_standalone_episode_file(legacy_id) == video
    assert resolve_standalone_episode_file(-9999, file_path=video) == video


def test_without_media_path_the_series_folder_check_applies(escaped, monkeypatch):
    from config import reload_settings
    from services.standalone_episode import resolve_standalone_episode_file

    monkeypatch.setenv("SUBLARR_MEDIA_PATH", "")
    reload_settings()
    _sid, eid, video = escaped
    assert resolve_standalone_episode_file(-eid) == video


def test_movie_symlinked_outside_media_is_refused(media, tmp_path):
    from db.standalone import upsert_watched_folder
    from services.standalone_library import movie_path_in_watched_folder

    real = tmp_path / "outside" / "Film (2020).mkv"
    real.write_bytes(b"\x00")
    link = media / "Film (2020).mkv"
    os.symlink(real, link)
    upsert_watched_folder(str(media), media_type="movie")
    assert movie_path_in_watched_folder(str(link)) is None

    ok = media / "Other (2021).mkv"
    ok.write_bytes(b"\x00")
    assert movie_path_in_watched_folder(str(ok)) == str(ok)


# --- health: series scan, sweep, auto-fix --------------------------------


def test_health_series_scan_skips_episodes_outside_media(escaped):
    from services.subtitle_health.series_scan import run_series_scan

    sid, _eid, _video = escaped
    with patch(
        "services.subtitle_health.series_scan.scan_episode",
        side_effect=lambda **kw: _Result(kw["episode_id"]),
    ) as scan:
        summary = run_series_scan(-sid)
    scan.assert_not_called()
    assert summary["episodes_scanned"] == 0


def test_health_sweep_and_auto_fix_skip_episodes_outside_media(escaped, monkeypatch):
    from services.subtitle_health import sweep

    _sid, eid, video = escaped
    monkeypatch.setattr(sweep, "_sweep_enabled", lambda: True)
    monkeypatch.setattr(sweep, "_auto_fix_enabled", lambda: True)
    monkeypatch.setattr(sweep, "_is_stable", lambda p: True)
    finding = {
        "id": 1,
        "suggested_fix": "reencode",
        "target_kind": "sidecar",
        "target_path": video[:-4] + ".de.srt",
    }
    with (
        patch.object(
            sweep, "scan_episode", side_effect=lambda **kw: _Result(kw["episode_id"])
        ) as scan,
        patch.object(sweep.store, "get_findings_for_episode", return_value=[finding]),
        patch.object(sweep, "apply_fix") as fix,
    ):
        sweep.subtitle_health_sweep_tick()
    assert all(c.kwargs["episode_id"] != -eid for c in scan.call_args_list)
    fix.assert_not_called()


def test_sweep_auto_fix_skips_a_sidecar_symlinked_outside_media(inside, tmp_path, monkeypatch):
    """The episode is fine, but a sidecar next to it points out of the media tree."""
    from services.subtitle_health import sweep

    _sid, eid, video = inside
    outside_sub = tmp_path / "outside" / "x.srt"
    outside_sub.write_text("1\n00:00:01,000 --> 00:00:02,000\nx\n")
    sidecar = video[:-4] + ".de.srt"
    os.symlink(outside_sub, sidecar)
    good = video[:-4] + ".en.srt"
    with open(good, "w") as fh:
        fh.write("1\n00:00:01,000 --> 00:00:02,000\nx\n")

    monkeypatch.setattr(sweep, "_sweep_enabled", lambda: True)
    monkeypatch.setattr(sweep, "_auto_fix_enabled", lambda: True)
    monkeypatch.setattr(sweep, "_is_stable", lambda p: True)
    monkeypatch.setattr(sweep, "is_suspect_sidecar", lambda p: False)
    findings = [
        {"id": 1, "suggested_fix": "reencode", "target_kind": "sidecar", "target_path": sidecar},
        {"id": 2, "suggested_fix": "reencode", "target_kind": "sidecar", "target_path": good},
    ]
    with (
        patch.object(sweep, "scan_episode", side_effect=lambda **kw: _Result(kw["episode_id"])),
        patch.object(sweep.store, "get_findings_for_episode", return_value=findings),
        patch.object(sweep, "apply_fix", return_value={"changed": True}) as fix,
    ):
        sweep.subtitle_health_sweep_tick()
    assert [c.args[0] for c in fix.call_args_list] == [2]


# --- scanner -------------------------------------------------------------


class _Resolver:
    def resolve_series(self, title, year=None, is_anime=False):
        return {"title": title.title(), "metadata_source": "filename"}

    def resolve_movie(self, title, year=None):
        return {"title": title, "metadata_source": "filename"}


def test_scanner_skips_directory_symlinks_leaving_media(media, tmp_path, caplog):
    from db.models.standalone import StandaloneEpisode
    from extensions import db
    from standalone.scanner import StandaloneScanner

    real_inside = media / "tv" / "Kept"
    season = real_inside / "Season 1"
    season.mkdir(parents=True)
    kept = season / "Kept - S01E01.mkv"
    kept.write_bytes(b"\x00")

    outside = tmp_path / "outside" / "Gone" / "Season 1"
    outside.mkdir(parents=True)
    (outside / "Gone - S01E01.mkv").write_bytes(b"\x00")
    os.symlink(tmp_path / "outside" / "Gone", media / "tv" / "Gone")
    (tmp_path / "outside" / "Loose - S01E02.mkv").write_bytes(b"\x00")
    os.symlink(tmp_path / "outside" / "Loose - S01E02.mkv", season / "Kept - S01E02.mkv")

    scanner = StandaloneScanner(metadata_resolver=_Resolver())
    with (
        patch("standalone.scanner._probe_embedded_tracks", return_value=None),
        caplog.at_level("WARNING", logger="standalone.scanner"),
    ):
        scanner.scan_folder({"path": str(media / "tv"), "media_type": "tv"})

    paths = {r.file_path for r in db.session.query(StandaloneEpisode).all()}
    assert paths == {str(kept)}
    outside_logs = [r for r in caplog.records if "outside the media folder" in r.getMessage()]
    assert len(outside_logs) == 1


# --- bulk series actions and the sidecar map -----------------------------


def test_bulk_series_paths_leave_out_files_outside_media(escaped):
    from services.standalone_library import standalone_series_video_paths

    sid, _eid, _video = escaped
    assert standalone_series_video_paths(sid) == []


def test_bulk_series_paths_keep_symlinks_inside_media(inside):
    from services.standalone_library import standalone_series_video_paths

    sid, _eid, video = inside
    assert standalone_series_video_paths(sid) == [video]


def test_sidecar_map_skips_episodes_outside_media(app_ctx, escaped):
    sid, _eid, video = escaped
    with open(video[:-4] + ".de.srt", "w") as fh:
        fh.write("1\n00:00:01,000 --> 00:00:02,000\nx\n")
    resp = app_ctx.test_client().get(f"/api/v1/library/series/{-sid}/subtitles")
    assert resp.status_code == 200
    assert resp.get_json()["subtitles"] == {}
