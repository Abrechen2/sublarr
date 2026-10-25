"""Foreign-track cleanup switches and policies of standalone titles.

The standalone series page and movie page save ``cleanup_foreign_tracks`` and
track-policy overrides under the standalone id. Without Sonarr/Radarr:

* the sweep's ``override_paths`` raised "Sonarr is not configured" for such a
  row, marked the whole set incomplete and paused stripping everywhere;
* the per-download hook ignored the switch (standalone items carry no
  ``sonarr_series_id``) and fell back to the global default — a series
  switched off could still be stripped.

An unconfigured arr with an id that is no standalone title still fails closed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest


@pytest.fixture
def no_arr(monkeypatch):
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: None)
    monkeypatch.setattr("radarr_client.get_radarr_client", lambda *a, **kw: None)


def _now():
    return datetime.now(UTC)


def _standalone_series(folder: str) -> int:
    from db.models.standalone import StandaloneSeries
    from extensions import db

    row = StandaloneSeries(title="Show", folder_path=folder, created_at=_now(), updated_at=_now())
    db.session.add(row)
    db.session.commit()
    return row.id


def _standalone_movie(file_path: str) -> int:
    from db.models.standalone import StandaloneMovie
    from extensions import db

    row = StandaloneMovie(title="Film", file_path=file_path, created_at=_now(), updated_at=_now())
    db.session.add(row)
    db.session.commit()
    return row.id


def _series_settings(series_id: int, **fields):
    from db.models.core import SeriesSettings
    from extensions import db

    db.session.add(SeriesSettings(sonarr_series_id=series_id, updated_at=_now(), **fields))
    db.session.commit()


def _movie_settings(movie_id: int, **fields):
    from db.models.core import MovieSettings
    from extensions import db

    db.session.add(MovieSettings(radarr_movie_id=movie_id, updated_at=_now(), **fields))
    db.session.commit()


# --- sweep: override_paths ---------------------------------------------------


def test_switched_off_standalone_series_is_excluded_and_set_complete(app_ctx, no_arr):
    from services.foreign_tracks.policy import override_paths

    sid = _standalone_series("/media/standalone/Show")
    _series_settings(sid, cleanup_foreign_tracks=False)

    result = override_paths()
    assert result.complete is True
    assert result.excluded == ["/media/standalone/Show"]


def test_standalone_movie_override_is_keyed_by_its_file(app_ctx, no_arr):
    """Standalone movies may share a folder, so the movie's own file is the
    scope — the folder would also catch its neighbours."""
    from services.foreign_tracks.policy import is_excluded, override_paths

    mid = _standalone_movie("/media/movies/Film.mkv")
    _movie_settings(mid, cleanup_foreign_tracks=False)

    result = override_paths()
    assert result.complete is True
    assert result.excluded == ["/media/movies/Film.mkv"]
    assert is_excluded("/media/movies/Film.mkv", result.excluded)
    assert not is_excluded("/media/movies/Other.mkv", result.excluded)


def test_standalone_series_policy_override_becomes_a_pair(app_ctx, no_arr):
    from services.foreign_tracks.policy import override_paths

    sid = _standalone_series("/media/standalone/Show")
    _series_settings(sid, cleanup_keep_sdh=True)

    result = override_paths()
    assert result.complete is True
    assert [p for p, _ in result.pairs] == ["/media/standalone/Show"]


def test_unknown_id_without_arr_still_pauses_the_strip(app_ctx, no_arr):
    from services.foreign_tracks.policy import override_paths

    _series_settings(999, cleanup_foreign_tracks=False)

    result = override_paths()
    assert result.complete is False
    assert result.failed == ("series 999",)


def test_standalone_paths_are_not_remote_mapped(app_ctx, no_arr):
    from services.foreign_tracks.policy import override_paths

    sid = _standalone_series("/media/standalone/Show")
    _series_settings(sid, cleanup_foreign_tracks=False)

    with patch("config_utils.map_path", side_effect=lambda p: "/mapped" + p):
        result = override_paths()
    assert result.excluded == ["/media/standalone/Show"]


# --- per-download hook: the item's own switch ---------------------------------


def _global_on(monkeypatch):
    class _S:
        cleanup_foreign_tracks_default = True

    monkeypatch.setattr("config.get_settings", lambda: _S())


def test_hook_honours_a_switched_off_standalone_series(app_ctx, no_arr, monkeypatch):
    from services.foreign_track_cleanup import foreign_track_cleanup_decision

    _global_on(monkeypatch)
    sid = _standalone_series("/media/standalone/Show")
    _series_settings(sid, cleanup_foreign_tracks=False)

    assert foreign_track_cleanup_decision({"standalone_series_id": sid}) is False


def test_hook_honours_a_switched_off_standalone_movie(app_ctx, no_arr, monkeypatch):
    from services.foreign_track_cleanup import foreign_track_cleanup_decision

    _global_on(monkeypatch)
    mid = _standalone_movie("/media/movies/Film.mkv")
    _movie_settings(mid, cleanup_foreign_tracks=False)

    assert foreign_track_cleanup_decision({"standalone_movie_id": mid}) is False


def test_hook_ignores_standalone_ids_while_sonarr_is_configured(app_ctx, monkeypatch):
    """With Sonarr configured, SeriesSettings ids are Sonarr ids — a standalone
    id must not pick up an unrelated Sonarr series' switch."""
    from services.foreign_track_cleanup import foreign_track_cleanup_decision, settings_ids

    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: object())
    monkeypatch.setattr("radarr_client.get_radarr_client", lambda *a, **kw: None)
    _global_on(monkeypatch)
    _series_settings(5, cleanup_foreign_tracks=False)

    assert settings_ids({"standalone_series_id": 5}) == (None, None)
    assert foreign_track_cleanup_decision({"standalone_series_id": 5}) is True


def test_settings_ids_prefers_arr_ids(no_arr):
    from services.foreign_track_cleanup import settings_ids

    assert settings_ids({"sonarr_series_id": 3, "standalone_series_id": 9}) == (3, None)
    assert settings_ids({"standalone_series_id": 9}) == (9, None)
    assert settings_ids({"standalone_movie_id": 4}) == (None, 4)
    assert settings_ids({}) == (None, None)


# --- series detail shows the saved switch -------------------------------------


def test_standalone_series_detail_shows_the_saved_cleanup_switch(client, no_arr, tmp_path):
    with client.application.app_context():
        sid = _standalone_series(str(tmp_path))
        _series_settings(sid, cleanup_foreign_tracks=False)

    resp = client.get(f"/api/v1/library/series/{sid}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["source"] == "standalone"
    assert data["cleanup_foreign_tracks_override"] is False
    assert data["cleanup_foreign_tracks_effective"] is False
