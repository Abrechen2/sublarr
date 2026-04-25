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
    from datetime import datetime, timezone

    from db.models.core import LanguageProfile, SeriesLanguageProfile

    p = LanguageProfile(
        name="Anime DE",
        source_language="en",
        source_language_name="English",
        target_languages_json='["de"]',
        target_language_names_json='["German"]',
        is_default=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
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
