"""Tests for SearchRepository FTS5 search."""

import pytest

from app import create_app
from db.repositories.search import SearchRepository
from extensions import db as sa_db


@pytest.fixture()
def app(tmp_path):
    """Create a Flask app with in-memory SQLite for testing."""
    import os
    db_path = str(tmp_path / "test.db")
    os.environ["SUBLARR_DB_PATH"] = db_path
    os.environ["SUBLARR_API_KEY"] = ""
    os.environ["SUBLARR_LOG_LEVEL"] = "ERROR"

    from config import reload_settings
    reload_settings()

    application = create_app(testing=True)
    application.config["TESTING"] = True

    with application.app_context():
        sa_db.create_all()
        repo = SearchRepository()
        repo.init_search_tables()
        yield application

    os.environ.pop("SUBLARR_DB_PATH", None)
    os.environ.pop("SUBLARR_API_KEY", None)
    os.environ.pop("SUBLARR_LOG_LEVEL", None)


@pytest.fixture()
def search_repo(app):
    """Provide a SearchRepository within app context."""
    with app.app_context():
        yield SearchRepository()


def test_search_empty_query(app, search_repo):
    """Short query (single char) returns empty results without error."""
    with app.app_context():
        result = search_repo.search_all("a")
        assert result == {"series": [], "episodes": [], "subtitles": []}


def test_search_none_query(app, search_repo):
    """None query returns empty results."""
    with app.app_context():
        result = search_repo.search_all("")
        assert result == {"series": [], "episodes": [], "subtitles": []}


def test_search_no_results(app, search_repo):
    """Query with no matching data returns empty lists."""
    with app.app_context():
        result = search_repo.search_all("xyznonexistent")
        assert "series" in result
        assert "episodes" in result
        assert "subtitles" in result
        assert all(len(v) == 0 for v in result.values())


def test_search_result_structure(app, search_repo):
    """search_all always returns the three expected keys."""
    with app.app_context():
        result = search_repo.search_all("test")
        assert set(result.keys()) == {"series", "episodes", "subtitles"}


def test_search_limit_respected(app, search_repo):
    """Limit parameter bounds the result count."""
    with app.app_context():
        result = search_repo.search_all("ab", limit=5)
        assert len(result["series"]) <= 5
        assert len(result["episodes"]) <= 5
        assert len(result["subtitles"]) <= 5
