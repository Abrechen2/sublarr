"""Standalone series and movies use their own language profile (gap 2).

Profile assignments of standalone titles are stored under the negated id
(the owner key, docs/specs/standalone-ids.md), so standalone series 3 and
Sonarr series 3 have separate assignments. Every reader goes through
``db.profiles.get_profile_for_item``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest


class _Client:
    pass


@pytest.fixture
def no_arr(monkeypatch):
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: None)
    monkeypatch.setattr("radarr_client.get_radarr_client", lambda *a, **kw: None)


@pytest.fixture
def with_arr(monkeypatch):
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: _Client())
    monkeypatch.setattr("radarr_client.get_radarr_client", lambda *a, **kw: _Client())


def _profile(name: str, langs: list[str], **extra) -> int:
    from db.models.core import LanguageProfile
    from extensions import db

    now = datetime.now(UTC)
    row = LanguageProfile(
        name=name,
        target_languages_json=json.dumps(langs),
        target_language_names_json=json.dumps(langs),
        created_at=now,
        updated_at=now,
        **extra,
    )
    db.session.add(row)
    db.session.commit()
    return row.id


def _assign_series(key: int, profile_id: int) -> None:
    from db.profiles import assign_series_profile

    assign_series_profile(key, profile_id)


def _standalone_series(tmp_path, title="Show") -> tuple[int, str]:
    from db.models.standalone import StandaloneSeries
    from extensions import db

    folder = tmp_path / title
    (folder / "Season 1").mkdir(parents=True)
    ep = folder / "Season 1" / f"{title} - S01E01.mkv"
    ep.write_bytes(b"\x00")
    now = datetime.now(UTC)
    row = StandaloneSeries(title=title, folder_path=str(folder), created_at=now, updated_at=now)
    db.session.add(row)
    db.session.commit()
    return row.id, str(ep)


def _standalone_movie(tmp_path) -> int:
    from db.models.standalone import StandaloneMovie
    from extensions import db

    path = tmp_path / "Movie (2020).mkv"
    path.write_bytes(b"\x00")
    now = datetime.now(UTC)
    row = StandaloneMovie(title="Movie", file_path=str(path), created_at=now, updated_at=now)
    db.session.add(row)
    db.session.commit()
    return row.id


# --- resolver ----------------------------------------------------------------


def test_standalone_series_reads_its_own_assignment(app_ctx):
    from db.profiles import get_profile_for_item

    fr = _profile("French", ["fr"])
    ja = _profile("Japanese", ["ja"])
    _assign_series(-3, fr)  # standalone series 3
    _assign_series(3, ja)  # Sonarr series 3

    assert get_profile_for_item({"standalone_series_id": 3})["target_languages"] == ["fr"]
    assert get_profile_for_item({"sonarr_series_id": 3})["target_languages"] == ["ja"]


def test_standalone_movie_reads_its_own_assignment(app_ctx):
    from db.profiles import assign_movie_profile, get_profile_for_item

    fr = _profile("French", ["fr"])
    ja = _profile("Japanese", ["ja"])
    assign_movie_profile(-4, fr)
    assign_movie_profile(4, ja)
    assert get_profile_for_item({"standalone_movie_id": 4})["target_languages"] == ["fr"]
    assert get_profile_for_item({"radarr_movie_id": 4})["target_languages"] == ["ja"]


def test_unassigned_and_ownerless_items_use_the_default(app_ctx):
    from db.profiles import get_default_profile, get_profile_for_item

    default_id = get_default_profile()["id"]
    assert get_profile_for_item({"standalone_series_id": 99})["id"] == default_id
    assert get_profile_for_item({})["id"] == default_id


def test_readers_follow_the_standalone_profile(app_ctx):
    """MT keep-seeking, embedded extraction and the provider filters."""
    from config import get_settings
    from services.embedded_extractor import resolve_profile_for_item
    from services.mt_provisional import resolve_keep_seeking
    from wanted_search.process import _load_profile_filters

    p = _profile(
        "Keep",
        ["fr"],
        mt_keep_seeking_original=1,
        enabled_providers_json=json.dumps(["animetosho"]),
        scoring_preset="anime",
    )
    _assign_series(-3, p)
    item = {"id": 1, "standalone_series_id": 3}

    assert resolve_keep_seeking(item) is True
    assert resolve_profile_for_item(item, get_settings())["target_languages"] == ["fr"]
    filters = _load_profile_filters(item, 1)
    assert filters["enabled_providers"] == ["animetosho"]
    assert filters["scoring_preset"] == "anime"


def test_translation_backend_and_glossary_follow_standalone(app_ctx):
    from translator._helpers import _extract_series_id, _resolve_backend_for_context
    from wanted_search.process import _build_arr_context

    p = _profile("DeepL", ["fr"], translation_backend="deepl")
    _assign_series(-3, p)
    ctx = _build_arr_context({"standalone_series_id": 3, "id": 1})

    assert ctx == {"standalone_series_id": 3}
    assert _resolve_backend_for_context(ctx, "fr")[0] == "deepl"
    assert _extract_series_id(ctx) == -3
    assert _extract_series_id({"sonarr_series_id": 3}) == 3


def test_scanner_uses_the_series_profile(app_ctx):
    from standalone.scanner import StandaloneScanner

    p = _profile("French", ["fr", "it"])
    _assign_series(-5, p)
    scanner = StandaloneScanner()
    assert scanner._get_target_languages({"standalone_series_id": 5}) == ["fr", "it"]


# --- API ---------------------------------------------------------------------


def test_series_detail_shows_the_assigned_profile(client, no_arr, tmp_path):
    with client.application.app_context():
        sid, _ep = _standalone_series(tmp_path)
        p = _profile("French", ["fr"])
        _assign_series(-sid, p)

    detail = client.get(f"/api/v1/library/series/{-sid}").get_json()
    assert detail["profile_id"] == p
    assert detail["target_languages"] == ["fr"]
    assert set(detail["episodes"][0]["subtitles"]) == {"fr"}


def test_library_list_shows_standalone_ids_and_profiles(client, no_arr, tmp_path, monkeypatch):
    monkeypatch.setattr("config.is_standalone_mode", lambda: True)
    with client.application.app_context():
        sid, _ep = _standalone_series(tmp_path)
        mid = _standalone_movie(tmp_path)
        p = _profile("French", ["fr"])
        _assign_series(-sid, p)

    data = client.get("/api/v1/library").get_json()
    series = {s["standalone_id"]: s for s in data["series"]}
    movies = {m["standalone_id"]: m for m in data["movies"]}
    assert series[sid]["id"] == -sid
    assert series[sid]["profile_id"] == p
    assert movies[mid]["id"] == -mid


@pytest.mark.parametrize(
    ("arr_id_sign", "arr_fixture", "stored_key_sign"),
    [(-1, "no_arr", -1), (1, "no_arr", -1), (-1, "with_arr", -1), (1, "with_arr", 1)],
)
def test_assign_stores_the_owner_key(
    client, tmp_path, request, arr_id_sign, arr_fixture, stored_key_sign
):
    request.getfixturevalue(arr_fixture)
    from db.models.core import SeriesLanguageProfile
    from extensions import db

    with client.application.app_context():
        sid, _ep = _standalone_series(tmp_path)
        p = _profile("French", ["fr"])

    resp = client.put(
        "/api/v1/language-profiles/assign",
        json={"type": "series", "arr_id": arr_id_sign * sid, "profile_id": p},
    )
    assert resp.status_code == 200, resp.get_json()
    with client.application.app_context():
        keys = [r.sonarr_series_id for r in db.session.query(SeriesLanguageProfile).all()]
    assert keys == [stored_key_sign * sid]


def test_assign_rejects_unknown_negative_ids(client, no_arr):
    with client.application.app_context():
        p = _profile("French", ["fr"])
    resp = client.put(
        "/api/v1/language-profiles/assign",
        json={"type": "series", "arr_id": -999, "profile_id": p},
    )
    assert resp.status_code == 404


def test_standalone_movie_detail_reads_its_profile(client, no_arr, tmp_path):
    from db.profiles import assign_movie_profile

    with client.application.app_context():
        mid = _standalone_movie(tmp_path)
        p = _profile("French", ["fr"])
        assign_movie_profile(-mid, p)

    for movie_id in (-mid, mid):
        data = client.get(f"/api/v1/standalone/movies/{movie_id}").get_json()
        assert data["profile_id"] == p
        assert data["standalone_id"] == mid
        assert data["id"] == -mid
