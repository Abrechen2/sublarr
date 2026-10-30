"""Fixes from the Codex review of the standalone-id change set.

1. A positive movie id with Radarr configured is Radarr's only — an id
   Radarr does not know never reaches the standalone movie of that number.
2. Downloads of standalone titles keep their owner: the post-download
   pipeline and the foreign-track cleanup see the standalone series' switch.
3. Exporting a standalone series uses its local folder, without the
   Sonarr remote-path mapping.
4. The overrides tree names standalone titles under their owner key.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from providers.base import SubtitleFormat

_NOW = datetime.now(UTC)
_SRT = b"1\n00:00:01,000 --> 00:00:02,000\nHallo Welt\n"


def _standalone_movie(tmp_path) -> int:
    from db.models.standalone import StandaloneMovie, WatchedFolder
    from extensions import db

    path = tmp_path / "Film (2020).mkv"
    path.write_bytes(b"\x00")
    db.session.add(WatchedFolder(path=str(tmp_path), created_at=_NOW, updated_at=_NOW))
    row = StandaloneMovie(title="Film", file_path=str(path), created_at=_NOW, updated_at=_NOW)
    db.session.add(row)
    db.session.commit()
    return row.id


def _standalone_series(folder) -> int:
    from db.models.standalone import StandaloneSeries
    from extensions import db

    row = StandaloneSeries(title="Show", folder_path=str(folder), created_at=_NOW, updated_at=_NOW)
    db.session.add(row)
    db.session.commit()
    return row.id


# --- 1 -----------------------------------------------------------------------


def test_unknown_radarr_id_does_not_reach_a_standalone_movie(app_ctx, tmp_path, monkeypatch):
    from services.movie_video_path import resolve_movie_video_path

    mid = _standalone_movie(tmp_path)
    radarr = MagicMock()
    radarr.get_movie_by_id.return_value = None
    monkeypatch.setattr("radarr_client.get_radarr_client", lambda *a, **kw: radarr)

    assert resolve_movie_video_path(mid) is None
    assert resolve_movie_video_path(-mid) == str(tmp_path / "Film (2020).mkv")


def test_movie_detail_of_an_unknown_radarr_id_is_404(client, tmp_path, monkeypatch):
    with client.application.app_context():
        mid = _standalone_movie(tmp_path)
    radarr = MagicMock()
    radarr.get_movie_by_id.return_value = None
    monkeypatch.setattr("radarr_client.get_radarr_client", lambda *a, **kw: radarr)

    assert client.get(f"/api/v1/standalone/movies/{mid}").status_code == 404
    assert client.get(f"/api/v1/standalone/movies/{-mid}").status_code == 200


# --- 2 -----------------------------------------------------------------------


def test_download_of_a_standalone_episode_honours_its_cleanup_switch(
    app_ctx, tmp_path, monkeypatch
):
    from config import get_settings, reload_settings
    from db.models.core import SeriesSettings, SubtitleAutomationQueueEntry
    from extensions import db
    from providers.download_manager import save_subtitle
    from services.media_ids import movie_key_for_item, series_key_for_item

    monkeypatch.setenv("SUBLARR_MEDIA_PATH", str(tmp_path))
    reload_settings()
    monkeypatch.setattr(get_settings(), "cleanup_foreign_tracks_default", True, raising=False)
    sid = _standalone_series(tmp_path)
    db.session.add(
        SeriesSettings(sonarr_series_id=-sid, cleanup_foreign_tracks=False, updated_at=_NOW)
    )
    db.session.commit()
    (tmp_path / "Show - S01E01.mkv").write_bytes(b"v")
    item = {"standalone_series_id": sid}
    result = SimpleNamespace(
        content=_SRT,
        format=SubtitleFormat.SRT,
        language="de",
        provider_name="opensubtitles",
        subtitle_id="s1",
        score=300,
    )

    with patch("services.processing_pipeline._run_pipeline_for_path") as pipeline:
        save_subtitle(
            result,
            str(tmp_path / "Show - S01E01.de.srt"),
            series_id=series_key_for_item(item),
            movie_id=movie_key_for_item(item),
        )

    assert pipeline.call_args.kwargs["series_id"] == -sid
    queued = db.session.query(SubtitleAutomationQueueEntry).filter_by(
        task_type=SubtitleAutomationQueueEntry.TASK_FOREIGN_TRACK_CLEANUP
    )
    assert queued.count() == 0, "the series switched cleanup off"


def test_wanted_downloads_pass_owner_keys():
    """Every save_subtitle call of the wanted pipeline passes the owner keys."""
    import inspect

    import wanted_search.post_processor as post
    import wanted_search.process as proc

    for module in (proc, post):
        source = inspect.getsource(module)
        assert 'series_id=item.get("sonarr_series_id")' not in source
        assert source.count("series_id=series_key_for_item(item)") >= 1


# --- 3 -----------------------------------------------------------------------


def test_standalone_export_path_is_not_remote_mapped(app_ctx, tmp_path, monkeypatch):
    from routes.subtitles.export import _get_series_path

    sid = _standalone_series(tmp_path)
    monkeypatch.setattr("routes.subtitles.export.map_path", lambda p: "/mapped" + p)
    sonarr = MagicMock()
    sonarr.get_series_by_id.return_value = None
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: sonarr)

    assert _get_series_path(-sid) == str(tmp_path)
    # A Sonarr id Sonarr does not know is not answered with the standalone series.
    assert _get_series_path(sid) is None


# --- 4 -----------------------------------------------------------------------


def test_override_tree_names_standalone_titles(client, tmp_path):
    from extensions import db

    with client.application.app_context():
        sid = _standalone_series(tmp_path)
        from db.models.core import SeriesSettings

        db.session.add(
            SeriesSettings(sonarr_series_id=-sid, cleanup_keep_sdh=True, updated_at=_NOW)
        )
        db.session.commit()

    data = client.get("/api/v1/profiles-overrides/scopes").get_json()
    text = str(data)
    assert "Show" in text
    assert f"#{-sid}" not in text
