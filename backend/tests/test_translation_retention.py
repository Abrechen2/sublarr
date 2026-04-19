"""translation_events retention cron tests (Phase A1)."""

from datetime import UTC, datetime, timedelta

import pytest


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBLARR_DB_PATH", str(tmp_path / "app.db"))
    from config import reload_settings

    reload_settings()
    from app import create_app

    app = create_app(testing=True)
    from extensions import db as sa_db

    with app.app_context():
        sa_db.create_all()
    yield app


def test_delete_old_events(app):
    from db.models.translation import TranslationEvent
    from extensions import db
    from utils.scheduler_retention_translation import delete_old_translation_events

    with app.app_context():
        old = TranslationEvent(
            backend="ollama",
            source_lang="en",
            target_lang="de",
            lines_count=1,
            chars_in=1,
            status="ok",
            started_at=datetime.now(UTC) - timedelta(days=120),
        )
        fresh = TranslationEvent(
            backend="ollama",
            source_lang="en",
            target_lang="de",
            lines_count=1,
            chars_in=1,
            status="ok",
            started_at=datetime.now(UTC),
        )
        db.session.add_all([old, fresh])
        db.session.commit()

        deleted = delete_old_translation_events(retention_days=90)
        assert deleted == 1

        remaining = db.session.query(TranslationEvent).all()
        assert len(remaining) == 1


def test_defaults_to_setting(app, monkeypatch):
    from config import get_settings
    from utils.scheduler_retention_translation import delete_old_translation_events

    s = get_settings()
    monkeypatch.setattr(s, "translation_events_retention_days", 7)
    # No rows -> 0 deleted; just verifies it reads the setting without crashing
    with app.app_context():
        assert delete_old_translation_events() == 0
