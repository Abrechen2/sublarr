"""Tests for FilterPresetsRepository CRUD and validation."""

import pytest

from app import create_app
from db.repositories.presets import FilterPresetsRepository
from extensions import db as sa_db


@pytest.fixture()
def app(tmp_path):
    """Create a Flask app with SQLite for testing."""
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
        yield application

    os.environ.pop("SUBLARR_DB_PATH", None)
    os.environ.pop("SUBLARR_API_KEY", None)
    os.environ.pop("SUBLARR_LOG_LEVEL", None)


@pytest.fixture()
def repo(app):
    """Provide a FilterPresetsRepository within app context."""
    with app.app_context():
        yield FilterPresetsRepository()


def test_create_and_list_preset(app, repo):
    """Created preset appears in list for correct scope."""
    with app.app_context():
        conditions = {"logic": "AND", "conditions": [{"field": "status", "op": "eq", "value": "wanted"}]}
        preset = repo.create_preset("My Filter", "wanted", conditions)
        assert preset["name"] == "My Filter"
        assert preset["scope"] == "wanted"

        presets = repo.list_presets("wanted")
        assert len(presets) == 1
        assert presets[0]["id"] == preset["id"]


def test_list_presets_scope_isolation(app, repo):
    """Presets for 'wanted' scope don't appear in 'history' scope."""
    with app.app_context():
        conditions = {"logic": "AND", "conditions": []}
        repo.create_preset("Wanted filter", "wanted", conditions)
        history_presets = repo.list_presets("history")
        assert len(history_presets) == 0


def test_delete_preset(app, repo):
    """Deleted preset no longer appears in list."""
    with app.app_context():
        conditions = {"logic": "AND", "conditions": []}
        preset = repo.create_preset("To delete", "wanted", conditions)
        assert repo.delete_preset(preset["id"]) is True
        assert len(repo.list_presets("wanted")) == 0


def test_delete_nonexistent_preset(app, repo):
    """Deleting a non-existent preset returns False."""
    with app.app_context():
        assert repo.delete_preset(9999) is False


def test_invalid_field_raises(app, repo):
    """Conditions with invalid field name raise ValueError."""
    with app.app_context():
        bad_conditions = {"logic": "AND", "conditions": [
            {"field": "injected; DROP TABLE--", "op": "eq", "value": "x"}
        ]}
        with pytest.raises(ValueError, match="not allowed"):
            repo.create_preset("Bad", "wanted", bad_conditions)


def test_update_preset(app, repo):
    """Updated preset reflects new name."""
    with app.app_context():
        conditions = {"logic": "AND", "conditions": []}
        preset = repo.create_preset("Original", "wanted", conditions)
        updated = repo.update_preset(preset["id"], name="Updated")
        assert updated["name"] == "Updated"
