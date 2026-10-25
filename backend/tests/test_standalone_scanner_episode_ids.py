"""The standalone scanner records an episode id for every episode file and
drops ids whose file is gone (behind the same reachability guard as the
wanted cleanup)."""

from __future__ import annotations

from unittest.mock import patch


class _Resolver:
    def resolve_series(self, title, year=None, is_anime=False):
        return {"title": title.title(), "metadata_source": "filename"}

    def resolve_movie(self, title, year=None):
        return {"title": title, "metadata_source": "filename"}


def _make_show(root):
    season = root / "Show" / "Season 1"
    season.mkdir(parents=True)
    paths = []
    for n in (1, 2):
        p = season / f"Show - S01E0{n} [1080p].mkv"
        p.write_bytes(b"\x00")
        paths.append(str(p))
    return paths


def _rows():
    from db.models.standalone import StandaloneEpisode
    from extensions import db

    return {
        r.file_path: (r.id, r.season, r.episode) for r in db.session.query(StandaloneEpisode).all()
    }


def test_scan_records_episode_ids(app_ctx, tmp_path):
    from standalone.scanner import StandaloneScanner

    paths = _make_show(tmp_path)
    scanner = StandaloneScanner(metadata_resolver=_Resolver())
    with patch("standalone.scanner._probe_embedded_tracks", return_value=None):
        scanner.scan_folder({"path": str(tmp_path), "media_type": "tv"})
        first = _rows()
        scanner.scan_folder({"path": str(tmp_path), "media_type": "tv"})
        again = _rows()

    assert set(first) == set(paths)
    assert first[paths[0]][1:] == (1, 1)
    assert again == first


def test_cleanup_drops_ids_of_missing_files(app_ctx, tmp_path):
    import os

    from db.standalone import upsert_watched_folder
    from standalone.scanner import StandaloneScanner

    paths = _make_show(tmp_path)
    upsert_watched_folder(str(tmp_path), media_type="tv")
    scanner = StandaloneScanner(metadata_resolver=_Resolver())
    with patch("standalone.scanner._probe_embedded_tracks", return_value=None):
        scanner.scan_all_folders()
        assert set(_rows()) == set(paths)
        os.remove(paths[1])
        scanner.scan_all_folders()

    assert set(_rows()) == {paths[0]}


def test_cleanup_keeps_ids_while_a_root_is_unreachable(app_ctx, tmp_path):
    import os

    from db.standalone import upsert_watched_folder
    from standalone.scanner import StandaloneScanner

    paths = _make_show(tmp_path)
    upsert_watched_folder(str(tmp_path), media_type="tv")
    scanner = StandaloneScanner(metadata_resolver=_Resolver())
    with patch("standalone.scanner._probe_embedded_tracks", return_value=None):
        scanner.scan_all_folders()
    os.remove(paths[1])
    with patch.object(StandaloneScanner, "_watched_roots_reachable", return_value=False):
        scanner._cleanup_stale_episodes()

    assert set(_rows()) == set(paths)
