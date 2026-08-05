"""Tests for the foreign_track_scan ORM model."""

import os

import pytest


@pytest.fixture()
def app(tmp_path):
    """Create a Flask app with an isolated SQLite DB for testing."""
    from app import create_app
    from config import reload_settings

    db_path = str(tmp_path / "test.db")
    os.environ["SUBLARR_DB_PATH"] = db_path
    os.environ["SUBLARR_API_KEY"] = ""
    os.environ["SUBLARR_LOG_LEVEL"] = "ERROR"

    reload_settings()

    application = create_app(testing=True)
    application.config["TESTING"] = True

    with application.app_context():
        yield application

    os.environ.pop("SUBLARR_DB_PATH", None)
    os.environ.pop("SUBLARR_API_KEY", None)
    os.environ.pop("SUBLARR_LOG_LEVEL", None)


def test_model_defines_the_expected_columns(app):
    from db.models.foreign_tracks import ForeignTrackScan

    cols = set(ForeignTrackScan.__table__.columns.keys())
    assert cols == {
        "id",
        "path",
        "size_bytes",
        "mtime",
        "state",
        "foreign_langs",
        "track_count",
        "probed_at",
        "processed_at",
        "error",
        "error_class",
        "attempts",
        "generation",
    }


def test_path_is_unique(app):
    from db.models.foreign_tracks import ForeignTrackScan

    assert ForeignTrackScan.__table__.columns["path"].unique is True


def test_state_constants_cover_the_graph(app):
    from db.models import foreign_tracks as ft

    assert ft.STATE_PENDING == "pending"
    assert ft.STATE_CLEAN == "clean"
    assert ft.STATE_AFFECTED == "affected"
    assert ft.STATE_STRIPPING == "stripping"
    assert ft.STATE_STRIPPED == "stripped"
    assert ft.STATE_FAILED == "failed"
