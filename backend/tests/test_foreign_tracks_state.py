"""Tests for sweep state persistence and config-hash invalidation."""

import os

import pytest

from services.foreign_tracks.state import (
    PHASE_ENUMERATE,
    PHASE_IDLE,
    SweepState,
    config_hash,
    load_state,
    save_state,
)


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


def test_load_returns_a_fresh_state_when_nothing_is_stored(app):
    state = load_state()
    assert state.generation == 0
    assert state.phase == PHASE_IDLE
    assert state.enumeration_complete is False


def test_save_then_load_round_trips(app):
    save_state(
        SweepState(
            generation=3,
            phase=PHASE_ENUMERATE,
            enumeration_complete=False,
            config_hash="abc",
            started_at="2026-08-05T00:00:00+00:00",
            completed_at=None,
            paused_reason=None,
        )
    )
    state = load_state()
    assert state.generation == 3
    assert state.phase == PHASE_ENUMERATE
    assert state.config_hash == "abc"


def test_hash_is_stable_across_cosmetic_differences():
    a = config_hash(
        {"keep_languages": ["de", "en"], "keep_und": True, "include_paths": ["_Filme/"]},
        "/media",
    )
    b = config_hash(
        {"keep_languages": ["EN", "DE"], "keep_und": True, "include_paths": ["_Filme"]},
        "/media/",
    )
    assert a == b


def test_hash_changes_when_the_keep_list_narrows():
    a = config_hash({"keep_languages": ["de", "en"], "keep_und": True}, "/media")
    b = config_hash({"keep_languages": ["de"], "keep_und": True}, "/media")
    assert a != b


def test_hash_changes_with_keep_und():
    a = config_hash({"keep_languages": ["de"], "keep_und": True}, "/media")
    b = config_hash({"keep_languages": ["de"], "keep_und": False}, "/media")
    assert a != b


def test_hash_changes_with_the_media_root():
    a = config_hash({"keep_languages": ["de"]}, "/media")
    b = config_hash({"keep_languages": ["de"]}, "/other")
    assert a != b


def test_hash_changes_when_a_path_differs_only_by_case():
    # Sublarr runs on Linux/Docker, a case-sensitive filesystem: "_Filme" and
    # "_filme" are genuinely different scopes and must hash differently,
    # unlike language codes which are legitimately case-insensitive.
    a = config_hash({"keep_languages": ["de"], "include_paths": ["_Filme"]}, "/media")
    b = config_hash({"keep_languages": ["de"], "include_paths": ["_filme"]}, "/media")
    assert a != b

    c = config_hash({"keep_languages": ["de"]}, "/Media")
    d = config_hash({"keep_languages": ["de"]}, "/media")
    assert c != d


def test_load_returns_a_fresh_state_on_invalid_json(app):
    from db.repositories.config import ConfigRepository

    ConfigRepository().save_config_entry("foreign_track_sweep_state", "not json")

    state = load_state()

    assert state == SweepState()


def test_load_returns_a_fresh_state_on_non_object_json(app):
    from db.repositories.config import ConfigRepository

    ConfigRepository().save_config_entry("foreign_track_sweep_state", "[1, 2, 3]")

    state = load_state()

    assert state == SweepState()


def test_load_returns_a_fresh_state_on_unknown_field(app):
    from db.repositories.config import ConfigRepository

    # A legacy blob from an older SweepState shape must be discarded rather
    # than partially loaded — a fresh state is recoverable, a half-loaded one
    # is not.
    ConfigRepository().save_config_entry(
        "foreign_track_sweep_state", '{"generation": 1, "bogus_field": 1}'
    )

    state = load_state()

    assert state == SweepState()
