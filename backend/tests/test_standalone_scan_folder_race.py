"""A watched folder removed or moved while a scan runs does not come back.

Found by the 1.18 end-to-end test: deleting /media/library 0.4 s after adding
it left 2 series, 2 movies and 11 wanted rows behind. The running scan
re-created them after the delete, and the follow-up scan was dropped with
"Standalone scan already running, skipping". The concurrent request is
simulated deterministically from inside the scan.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
import sqlalchemy as sa


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


def _library(root):
    for show in ("Alpha", "Beta"):
        season = root / show / "Season 1"
        season.mkdir(parents=True)
        for n in (1, 2):
            (season / f"{show} - S01E0{n} [1080p].mkv").write_bytes(b"\x00")
    for film in ("Gamma (2001)", "Delta (2002)"):
        (root / film).mkdir(parents=True)
        (root / film / f"{film}.mkv").write_bytes(b"\x00")
    return root


def _folder(path) -> int:
    from db.standalone import upsert_watched_folder

    return upsert_watched_folder(path=str(path))


def _count(table: str) -> int:
    from extensions import db

    return db.session.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar()


def _during_first_series(scanner, action):
    """Run ``action`` once, the first time the scan processes a series."""
    real = scanner._process_series_group
    done = []

    def hook(*args, **kwargs):
        if not done:
            done.append(True)
            action()
        return real(*args, **kwargs)

    return patch.object(scanner, "_process_series_group", side_effect=hook)


def test_a_folder_deleted_mid_scan_leaves_no_titles(api, scanner, tmp_path):
    library = _library(tmp_path / "library")
    fid = _folder(library)

    def delete():
        assert api.delete(f"/api/v1/standalone/folders/{fid}").status_code == 200
        # The follow-up scan the delete triggers finds the scan running.
        assert scanner.scan_all_folders() == {"error": "scan_already_running"}

    with _during_first_series(scanner, delete):
        scanner.scan_all_folders()

    assert _count("standalone_series") == 0
    assert _count("standalone_movies") == 0
    assert _count("wanted_items") == 0
    assert _count("standalone_episodes") == 0


def test_a_folder_moved_mid_scan_keeps_only_the_new_paths_titles(api, scanner, tmp_path):
    from db.standalone import get_standalone_movies, get_standalone_series

    old = _library(tmp_path / "old")
    new = tmp_path / "new"
    (new / "Omega" / "Season 1").mkdir(parents=True)
    (new / "Omega" / "Season 1" / "Omega - S01E01 [1080p].mkv").write_bytes(b"\x00")
    fid = _folder(old)

    def move():
        resp = api.put(f"/api/v1/standalone/folders/{fid}", json={"path": str(new)})
        assert resp.status_code == 200
        scanner.scan_all_folders()  # dropped today, run once the scan ends

    with _during_first_series(scanner, move):
        scanner.scan_all_folders()

    assert [s["folder_path"] for s in get_standalone_series()] == [str(new / "Omega")]
    assert get_standalone_movies() == []


def test_a_single_folder_scan_also_notices_the_delete(api, scanner, tmp_path, monkeypatch):
    from services.standalone_manager import launch_folder_scan

    library = _library(tmp_path / "library")
    fid = _folder(library)

    class InlineThread:
        def __init__(self, target, daemon=False):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr("services.standalone_manager.threading.Thread", InlineThread)
    monkeypatch.setattr("standalone.scanner.get_scanner", lambda: scanner)

    def delete():
        assert api.delete(f"/api/v1/standalone/folders/{fid}").status_code == 200

    with _during_first_series(scanner, delete):
        launch_folder_scan(api.application, fid, str(library))

    assert _count("standalone_series") == 0
    assert _count("standalone_movies") == 0
    assert _count("wanted_items") == 0


def test_scan_requests_during_a_scan_coalesce_into_one_rescan(scanner, tmp_path):
    first = _library(tmp_path / "first")
    _folder(first)
    second = tmp_path / "second"
    (second / "Omega" / "Season 1").mkdir(parents=True)
    (second / "Omega" / "Season 1" / "Omega - S01E01 [1080p].mkv").write_bytes(b"\x00")

    def request_twice():
        _folder(second)
        for _ in range(3):
            assert scanner.scan_all_folders() == {"error": "scan_already_running"}

    passes = []
    real_scan = scanner._scan_folder

    def counting(folder):
        passes.append(folder["path"])
        return real_scan(folder)

    with (
        _during_first_series(scanner, request_twice),
        patch.object(scanner, "_scan_folder", side_effect=counting),
    ):
        scanner.scan_all_folders()

    # First pass: only the first folder existed. One rescan covers both.
    assert passes == [str(first), str(first), str(second)]
    assert _count("standalone_series") == 3
    assert not scanner.is_scanning
    # The lock is free again.
    assert "error" not in scanner.scan_all_folders()
