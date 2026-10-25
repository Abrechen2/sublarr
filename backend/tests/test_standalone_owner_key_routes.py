"""Per-series/per-movie settings routes store standalone titles under the
owner key (the negated id) and Sonarr/Radarr titles under their own id
(docs/specs/standalone-ids.md, gap 7: mixed mode)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest


class _Client:
    def get_series_by_id(self, series_id):
        return None


@pytest.fixture
def no_arr(monkeypatch):
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: None)
    monkeypatch.setattr("radarr_client.get_radarr_client", lambda *a, **kw: None)


@pytest.fixture
def with_arr(monkeypatch):
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: _Client())
    monkeypatch.setattr("radarr_client.get_radarr_client", lambda *a, **kw: _Client())


def _series(client, tmp_path) -> int:
    from db.models.standalone import StandaloneSeries
    from extensions import db

    now = datetime.now(UTC)
    with client.application.app_context():
        row = StandaloneSeries(
            title="Show", folder_path=str(tmp_path), created_at=now, updated_at=now
        )
        db.session.add(row)
        db.session.commit()
        return row.id


def _movie(client, tmp_path) -> int:
    from db.models.standalone import StandaloneMovie
    from extensions import db

    now = datetime.now(UTC)
    with client.application.app_context():
        row = StandaloneMovie(
            title="Film", file_path=str(tmp_path / "Film.mkv"), created_at=now, updated_at=now
        )
        db.session.add(row)
        db.session.commit()
        return row.id


def _series_settings_keys(client) -> list[int]:
    from db.models.core import SeriesSettings
    from extensions import db

    with client.application.app_context():
        return sorted(r.sonarr_series_id for r in db.session.query(SeriesSettings).all())


@pytest.mark.parametrize(
    ("arr_fixture", "sign", "stored_sign"),
    [("no_arr", -1, -1), ("no_arr", 1, -1), ("with_arr", -1, -1), ("with_arr", 1, 1)],
)
def test_series_settings_patch_uses_the_owner_key(
    client, tmp_path, request, arr_fixture, sign, stored_sign
):
    request.getfixturevalue(arr_fixture)
    sid = _series(client, tmp_path)
    resp = client.patch(
        f"/api/v1/series/{sign * sid}/settings", json={"cleanup_foreign_tracks": False}
    )
    assert resp.status_code == 200, resp.get_json()
    assert _series_settings_keys(client) == [stored_sign * sid]


def test_series_settings_keep_an_unknown_positive_id_without_sonarr(client, no_arr):
    """A positive id that is no standalone series is stored as sent (pre-1.18)."""
    resp = client.patch("/api/v1/series/77/settings", json={"min_attempts_per_day": 2})
    assert resp.status_code == 200
    assert _series_settings_keys(client) == [77]


def test_profiles_overrides_series_roundtrip(client, with_arr, tmp_path):
    sid = _series(client, tmp_path)
    resp = client.patch(
        f"/api/v1/profiles-overrides/series/{-sid}", json={"cleanup_keep_sdh": True}
    )
    assert resp.status_code == 200, resp.get_json()
    assert _series_settings_keys(client) == [-sid]

    resolved = client.get(f"/api/v1/profiles-overrides/resolved/series/{-sid}")
    assert resolved.status_code == 200, resolved.get_json()
    body = resolved.get_json()
    assert body["scope"] == {"type": "series", "id": -sid, "name": "Show"}


def test_profiles_overrides_movie_roundtrip(client, with_arr, tmp_path):
    from db.models.core import MovieSettings
    from extensions import db

    mid = _movie(client, tmp_path)
    resp = client.patch(f"/api/v1/profiles-overrides/movie/{-mid}", json={"cleanup_keep_sdh": True})
    assert resp.status_code == 200, resp.get_json()
    with client.application.app_context():
        assert [r.radarr_movie_id for r in db.session.query(MovieSettings).all()] == [-mid]
    resolved = client.get(f"/api/v1/profiles-overrides/resolved/movie/{-mid}")
    assert resolved.status_code == 200
    assert resolved.get_json()["scope"]["name"] == "Film"


# Resolved scope labels: a positive id is Sonarr's/Radarr's when configured
# (1.18.0-rc.2 end-to-end test, F5).


def _arr_settings(client, series_key: int, movie_key: int) -> None:
    from db.models.core import MovieSettings, SeriesSettings
    from extensions import db

    now = datetime.now(UTC)
    with client.application.app_context():
        db.session.add(SeriesSettings(sonarr_series_id=series_key, updated_at=now))
        db.session.add(MovieSettings(radarr_movie_id=movie_key, updated_at=now))
        db.session.commit()


def _arr_titles(monkeypatch, series: dict, movies: dict) -> None:
    monkeypatch.setattr("routes.profiles_overrides.get_sonarr_series_titles", lambda: series)
    monkeypatch.setattr("routes.profiles_overrides.get_radarr_movie_titles", lambda: movies)


def test_resolved_positive_ids_are_not_labelled_with_standalone_titles(
    client, tmp_path, with_arr, monkeypatch
):
    _arr_titles(monkeypatch, {}, {})
    sid = _series(client, tmp_path)
    mid = _movie(client, tmp_path)
    _arr_settings(client, sid, mid)

    series = client.get(f"/api/v1/profiles-overrides/resolved/series/{sid}").get_json()
    movie = client.get(f"/api/v1/profiles-overrides/resolved/movie/{mid}").get_json()

    assert series["scope"]["name"] == f"#{sid}"
    assert movie["scope"]["name"] == f"#{mid}"


def test_resolved_positive_ids_use_the_arr_titles(client, tmp_path, with_arr, monkeypatch):
    sid = _series(client, tmp_path)
    mid = _movie(client, tmp_path)
    _arr_settings(client, sid, mid)
    _arr_titles(monkeypatch, {sid: "Sonarr Show"}, {mid: "Radarr Film"})

    series = client.get(f"/api/v1/profiles-overrides/resolved/series/{sid}").get_json()
    movie = client.get(f"/api/v1/profiles-overrides/resolved/movie/{mid}").get_json()

    assert series["scope"]["name"] == "Sonarr Show"
    assert movie["scope"]["name"] == "Radarr Film"


def test_resolved_positive_id_known_only_as_standalone_is_unknown_with_arr(
    client, tmp_path, with_arr
):
    sid = _series(client, tmp_path)
    mid = _movie(client, tmp_path)

    assert client.get(f"/api/v1/profiles-overrides/resolved/series/{sid}").status_code == 404
    assert client.get(f"/api/v1/profiles-overrides/resolved/movie/{mid}").status_code == 404


def test_resolved_legacy_positive_ids_keep_standalone_titles_without_arr(client, tmp_path, no_arr):
    sid = _series(client, tmp_path)
    mid = _movie(client, tmp_path)

    series = client.get(f"/api/v1/profiles-overrides/resolved/series/{sid}")
    movie = client.get(f"/api/v1/profiles-overrides/resolved/movie/{mid}")

    assert series.status_code == 200
    assert series.get_json()["scope"]["name"] == "Show"
    assert movie.status_code == 200
    assert movie.get_json()["scope"]["name"] == "Film"


def test_fansub_prefs_and_audio_pref_use_the_owner_key(client, no_arr, tmp_path):
    from db.models.core import FansubPreference
    from extensions import db

    sid = _series(client, tmp_path)
    resp = client.put(
        f"/api/v1/series/{sid}/fansub-prefs",
        json={"preferred_groups": ["SubsPlease"], "excluded_groups": [], "bonus": 10},
    )
    assert resp.status_code == 200
    resp = client.put(
        f"/api/v1/series/{-sid}/audio-track-pref", json={"preferred_audio_track_index": 1}
    )
    assert resp.status_code == 200, resp.get_json()
    with client.application.app_context():
        assert [r.sonarr_series_id for r in db.session.query(FansubPreference).all()] == [-sid]
    assert _series_settings_keys(client) == [-sid]
    assert client.get(f"/api/v1/series/{-sid}/fansub-prefs").get_json()["bonus"] == 10


def test_absolute_order_flag_uses_the_owner_key(client, no_arr, tmp_path):
    from db.repositories.anidb import AnidbRepository

    sid = _series(client, tmp_path)
    resp = client.put(f"/api/v1/library/series/{-sid}/settings", json={"absolute_order": True})
    assert resp.status_code == 200, resp.get_json()
    with client.application.app_context():
        assert AnidbRepository().get_absolute_order(-sid) is True
    resp = client.get(f"/api/v1/anidb-mapping/settings/{-sid}")
    assert resp.status_code == 200
    assert resp.get_json()["data"]["absolute_order"] is True


def test_search_readers_use_the_owner_key(app_ctx):
    """Format requirement and fansub scoring of a standalone wanted item."""
    from db.models.core import SeriesSettings
    from db.repositories.fansub_prefs import FansubPreferenceRepository
    from extensions import db
    from services.media_ids import series_key_for_item
    from services.series_format import REQUIRE_ASS, get_series_format_requirement

    db.session.add(
        SeriesSettings(
            sonarr_series_id=-3,
            subtitle_format_requirement=REQUIRE_ASS,
            updated_at=datetime.now(UTC),
        )
    )
    db.session.commit()
    FansubPreferenceRepository().set_fansub_prefs(
        series_id=-3, preferred=["X"], excluded=[], bonus=5
    )
    item = {"standalone_series_id": 3}
    assert get_series_format_requirement(series_key_for_item(item)) == REQUIRE_ASS
    assert FansubPreferenceRepository().get_fansub_prefs(series_key_for_item(item))["bonus"] == 5
