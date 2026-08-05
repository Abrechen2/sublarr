"""Tests for the foreign-track scan repository."""

import os

import pytest

from db.models import foreign_tracks as ft


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


@pytest.fixture
def repo(app):
    from db.repositories.foreign_track_scan import ForeignTrackScanRepository

    return ForeignTrackScanRepository()


def test_upsert_inserts_a_new_path_as_pending(repo):
    repo.upsert_seen("/media/a.mkv", 100, 1.0, generation=1)
    rows = repo.next_pending(limit=10)
    assert [r.path for r in rows] == ["/media/a.mkv"]
    assert rows[0].state == ft.STATE_PENDING


def test_upsert_keeps_the_verdict_when_size_and_mtime_are_unchanged(repo):
    repo.upsert_seen("/media/a.mkv", 100, 1.0, generation=1)
    repo.mark_probed("/media/a.mkv", [])
    repo.upsert_seen("/media/a.mkv", 100, 1.0, generation=2)
    assert repo.next_pending(limit=10) == []
    assert repo.counts_by_state()[ft.STATE_CLEAN] == 1


def test_upsert_resets_the_verdict_when_the_file_changed(repo):
    repo.upsert_seen("/media/a.mkv", 100, 1.0, generation=1)
    repo.mark_probed("/media/a.mkv", [])
    repo.upsert_seen("/media/a.mkv", 200, 2.0, generation=2)
    assert [r.path for r in repo.next_pending(limit=10)] == ["/media/a.mkv"]


def test_upsert_resets_attempts_when_the_file_changed(repo):
    repo.upsert_seen("/media/a.mkv", 100, 1.0, generation=1)
    repo.mark_failed("/media/a.mkv", "boom", ft.ERROR_PROBE)
    repo.upsert_seen("/media/a.mkv", 200, 2.0, generation=2)
    rows = repo.next_pending(limit=10)
    assert rows[0].attempts == 0


def test_prune_stale_removes_rows_from_older_generations(repo):
    repo.upsert_seen("/media/gone.mkv", 1, 1.0, generation=1)
    repo.upsert_seen("/media/here.mkv", 1, 1.0, generation=2)
    assert repo.prune_stale(generation=2) == 1
    assert [r.path for r in repo.next_pending(limit=10)] == ["/media/here.mkv"]


def test_mark_probed_with_languages_becomes_affected(repo):
    repo.upsert_seen("/media/a.mkv", 1, 1.0, generation=1)
    repo.mark_probed("/media/a.mkv", ["spa", "ita"])
    row = repo.claim_next_affected()
    assert row.path == "/media/a.mkv"
    assert row.track_count == 2
    assert row.state == ft.STATE_STRIPPING


def test_claim_returns_none_when_nothing_is_affected(repo):
    assert repo.claim_next_affected() is None


def test_release_stripping_returns_abandoned_rows_to_affected(repo):
    repo.upsert_seen("/media/a.mkv", 1, 1.0, generation=1)
    repo.mark_probed("/media/a.mkv", ["spa"])
    repo.claim_next_affected()
    assert repo.release_stripping() == 1
    assert repo.claim_next_affected().path == "/media/a.mkv"


def test_mark_failed_parks_the_row_after_the_attempt_cap(repo):
    repo.upsert_seen("/media/a.mkv", 1, 1.0, generation=1)
    for _ in range(ft.MAX_ATTEMPTS):
        repo.mark_failed("/media/a.mkv", "boom", ft.ERROR_PROBE)
    assert repo.counts_by_state()[ft.STATE_FAILED] == 1
    assert repo.next_pending(limit=10) == []


def test_verify_failures_park_immediately(repo):
    repo.upsert_seen("/media/a.mkv", 1, 1.0, generation=1)
    repo.mark_failed("/media/a.mkv", "bad", ft.ERROR_VERIFY)
    assert repo.counts_by_state()[ft.STATE_FAILED] == 1


def test_reset_all_to_pending_includes_stripped_rows(repo):
    repo.upsert_seen("/media/a.mkv", 1, 1.0, generation=1)
    repo.mark_probed("/media/a.mkv", ["spa"])
    repo.claim_next_affected()
    repo.mark_stripped("/media/a.mkv")
    assert repo.reset_all_to_pending() == 1
    assert [r.path for r in repo.next_pending(limit=10)] == ["/media/a.mkv"]


def test_sample_affected_reports_paths_and_languages(repo):
    repo.upsert_seen("/media/a.mkv", 1, 1.0, generation=1)
    repo.mark_probed("/media/a.mkv", ["spa", "ita"])
    sample = repo.sample_affected(limit=5)
    assert sample == [{"path": "/media/a.mkv", "tracks": 2, "langs": ["ita", "spa"]}]
