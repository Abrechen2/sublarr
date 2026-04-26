"""Integration tests for the profiles-overrides API blueprint."""

from __future__ import annotations

import os

import pytest

from app import create_app
from extensions import db as sa_db


@pytest.fixture()
def app(tmp_path):
    """Flask app with isolated SQLite DB and all tables created."""
    db_path = str(tmp_path / "test.db")
    os.environ["SUBLARR_DB_PATH"] = db_path
    os.environ["SUBLARR_API_KEY"] = ""
    os.environ["SUBLARR_LOG_LEVEL"] = "ERROR"
    os.environ["SUBLARR_PLUGINS_DIR"] = str(tmp_path / "plugins")
    os.environ["SUBLARR_MEDIA_PATH"] = str(tmp_path)

    from config import reload_settings

    reload_settings()

    application = create_app(testing=True)
    application.config["TESTING"] = True

    with application.app_context():
        sa_db.create_all()
        yield application

    os.environ.pop("SUBLARR_DB_PATH", None)
    os.environ.pop("SUBLARR_API_KEY", None)
    os.environ.pop("SUBLARR_LOG_LEVEL", None)
    os.environ.pop("SUBLARR_PLUGINS_DIR", None)
    os.environ.pop("SUBLARR_MEDIA_PATH", None)

    from config import reload_settings as _rs

    _rs()


@pytest.fixture()
def client(app):
    """Test client bound to the SQLAlchemy-aware app fixture."""
    return app.test_client()


@pytest.fixture()
def sample_profiles_data(app):
    """Seed one LanguageProfile with one mapped series."""
    from datetime import UTC, datetime

    from db.models.core import LanguageProfile, SeriesLanguageProfile

    p = LanguageProfile(
        name="Anime DE",
        source_language="en",
        source_language_name="English",
        target_languages_json='["de"]',
        target_language_names_json='["German"]',
        is_default=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    sa_db.session.add(p)
    sa_db.session.flush()
    sa_db.session.add(SeriesLanguageProfile(sonarr_series_id=1, profile_id=p.id))
    sa_db.session.commit()


def test_get_scopes_returns_shape(client, sample_profiles_data):
    resp = client.get("/api/v1/profiles-overrides/scopes")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "profiles" in data
    assert "unassigned_series" in data
    assert "unassigned_movies" in data
    assert isinstance(data["profiles"], list)


def test_get_scopes_groups_series_under_profile(client, sample_profiles_data):
    resp = client.get("/api/v1/profiles-overrides/scopes")
    assert resp.status_code == 200
    data = resp.get_json()
    # sample_profiles_data fixture creates 1 profile with 1 mapped series
    assert len(data["profiles"]) >= 1
    profile = data["profiles"][0]
    assert "series" in profile


def test_get_resolved_global(client, sample_profiles_data):
    resp = client.get("/api/v1/profiles-overrides/resolved/global")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["scope"]["type"] == "global"
    assert "settings" in data
    # All 12 fields present
    assert len(data["settings"]) == 12


def test_get_resolved_profile(client, sample_profiles_data):
    resp = client.get("/api/v1/profiles-overrides/resolved/profile/1")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["scope"]["type"] == "profile"
    assert data["scope"]["id"] == 1


def test_get_resolved_series(client, sample_profiles_data):
    resp = client.get("/api/v1/profiles-overrides/resolved/series/1")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["scope"]["type"] == "series"
    assert "cleanup_foreign_tracks" in data["settings"]


def test_get_resolved_unknown_series_returns_404(client, sample_profiles_data):
    resp = client.get("/api/v1/profiles-overrides/resolved/series/99999")
    assert resp.status_code == 404


def test_patch_series_sets_override(client, sample_profiles_data):
    resp = client.patch(
        "/api/v1/profiles-overrides/series/1",
        json={"forced_preference": "prefer"},
    )
    assert resp.status_code == 200
    # follow-up GET reflects the change
    data = client.get("/api/v1/profiles-overrides/resolved/series/1").get_json()
    assert data["settings"]["forced_preference"]["effective"] == "prefer"
    assert data["settings"]["forced_preference"]["source"] == "series"


def test_patch_series_null_clears_override(client, sample_profiles_data):
    client.patch("/api/v1/profiles-overrides/series/1", json={"forced_preference": "prefer"})
    resp = client.patch("/api/v1/profiles-overrides/series/1", json={"forced_preference": None})
    assert resp.status_code == 200
    data = client.get("/api/v1/profiles-overrides/resolved/series/1").get_json()
    assert data["settings"]["forced_preference"]["source"] != "series"


def test_patch_series_invalid_field_returns_422(client, sample_profiles_data):
    resp = client.patch("/api/v1/profiles-overrides/series/1", json={"random_field": 1})
    assert resp.status_code == 422


def test_patch_series_invalid_enum_returns_422(client, sample_profiles_data):
    resp = client.patch("/api/v1/profiles-overrides/series/1", json={"hi_preference": "bad"})
    assert resp.status_code == 422


def test_post_reset_clears_all_series_overrides(client, sample_profiles_data):
    client.patch("/api/v1/profiles-overrides/series/1", json={"forced_preference": "prefer"})
    client.patch("/api/v1/profiles-overrides/series/1", json={"hi_preference": "exclude"})
    resp = client.post("/api/v1/profiles-overrides/series/1/reset")
    assert resp.status_code == 200
    data = client.get("/api/v1/profiles-overrides/resolved/series/1").get_json()
    assert data["settings"]["forced_preference"]["source"] != "series"
    assert data["settings"]["hi_preference"]["source"] != "series"


# ─── Phase A: scope filter + create/delete override endpoints ────────────────


def test_get_scopes_excludes_series_without_settings_or_mapping(client, sample_profiles_data):
    """A series that only exists in search_series (no settings, no mapping) must NOT appear in /scopes."""
    from sqlalchemy import text

    from extensions import db

    try:
        db.session.execute(
            text("CREATE TABLE IF NOT EXISTS search_series (id INTEGER PRIMARY KEY, title TEXT)")
        )
        db.session.execute(
            text("INSERT INTO search_series (id, title) VALUES (9999, 'Phantom Series')")
        )
        db.session.commit()
    except Exception:
        pytest.skip("search_series table cannot be created in test DB")
    resp = client.get("/api/v1/profiles-overrides/scopes")
    data = resp.get_json()
    all_series_ids = []
    for p in data["profiles"]:
        all_series_ids.extend(s["id"] for s in p["series"])
    all_series_ids.extend(s["id"] for s in data["unassigned_series"])
    assert 9999 not in all_series_ids


def test_post_create_override_series_inserts_empty_row(client, sample_profiles_data):
    from db.models.core import SeriesSettings

    assert SeriesSettings.query.get(7777) is None
    resp = client.post("/api/v1/profiles-overrides/series/7777/create-override")
    assert resp.status_code in (200, 201)
    assert SeriesSettings.query.get(7777) is not None


def test_post_create_override_series_is_idempotent(client, sample_profiles_data):
    client.post("/api/v1/profiles-overrides/series/7777/create-override")
    resp = client.post("/api/v1/profiles-overrides/series/7777/create-override")
    assert resp.status_code in (200, 201)


def test_delete_series_drops_settings_row(client, sample_profiles_data):
    client.post("/api/v1/profiles-overrides/series/8888/create-override")
    from db.models.core import SeriesSettings

    assert SeriesSettings.query.get(8888) is not None
    resp = client.delete("/api/v1/profiles-overrides/series/8888")
    assert resp.status_code == 200
    assert SeriesSettings.query.get(8888) is None


def test_delete_series_idempotent_on_missing(client, sample_profiles_data):
    resp = client.delete("/api/v1/profiles-overrides/series/12345")
    assert resp.status_code == 200


def test_post_create_override_movie_inserts_empty_row(client, sample_profiles_data):
    from db.models.core import MovieSettings

    assert MovieSettings.query.get(6666) is None
    resp = client.post("/api/v1/profiles-overrides/movie/6666/create-override")
    assert resp.status_code in (200, 201)
    assert MovieSettings.query.get(6666) is not None


def test_delete_movie_drops_settings_row(client, sample_profiles_data):
    client.post("/api/v1/profiles-overrides/movie/3333/create-override")
    resp = client.delete("/api/v1/profiles-overrides/movie/3333")
    assert resp.status_code == 200
    from db.models.core import MovieSettings

    assert MovieSettings.query.get(3333) is None
