"""write_translation_event tests."""

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


def test_write_event_persists(app):
    from db.models.translation import TranslationEvent
    from extensions import db
    from translator.events import write_translation_event

    with app.app_context():
        write_translation_event(
            backend="ollama",
            source_lang="en",
            target_lang="de",
            lines_count=10,
            chars_in=100,
            chars_out=120,
            tokens_in=150,
            tokens_out=170,
            cost_micro_usd=0,
            cache_hit=False,
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            status="ok",
        )
        row = db.session.query(TranslationEvent).filter_by(backend="ollama").one()
        assert row.lines_count == 10
        assert row.tokens_in == 150
        assert row.status == "ok"


def test_error_msg_truncated_to_4kb(app):
    from db.models.translation import TranslationEvent
    from extensions import db
    from translator.events import write_translation_event

    with app.app_context():
        huge = "x" * 10_000
        write_translation_event(
            backend="claude",
            source_lang="en",
            target_lang="de",
            lines_count=1,
            chars_in=1,
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            status="error",
            error_type="RuntimeError",
            error_msg=huge,
        )
        row = db.session.query(TranslationEvent).filter_by(backend="claude").one()
        assert len(row.error_msg) <= 4096


def test_cache_hit_records_zero_cost(app):
    from db.models.translation import TranslationEvent
    from extensions import db
    from translator.events import write_translation_event

    with app.app_context():
        write_translation_event(
            backend="claude",
            source_lang="en",
            target_lang="de",
            lines_count=10,
            chars_in=100,
            started_at=datetime.now(UTC),
            status="ok",
            cache_hit=True,
            cost_micro_usd=0,
        )
        row = db.session.query(TranslationEvent).filter_by(backend="claude").one()
        assert row.cache_hit is True
        assert row.cost_estimate_micro_usd == 0


def test_latency_ms_computed_from_times(app):
    from db.models.translation import TranslationEvent
    from extensions import db
    from translator.events import write_translation_event

    with app.app_context():
        started = datetime.now(UTC)
        finished = started + timedelta(milliseconds=1234)
        write_translation_event(
            backend="claude",
            source_lang="en",
            target_lang="de",
            lines_count=1,
            chars_in=1,
            started_at=started,
            finished_at=finished,
            status="ok",
        )
        row = db.session.query(TranslationEvent).filter_by(backend="claude").one()
        assert row.latency_ms == 1234


def test_db_failure_logged_not_raised(app, caplog):
    """Event write failure must never break the translation flow."""
    import logging
    from unittest.mock import patch

    from translator.events import write_translation_event

    with (
        app.app_context(),
        patch("translator.events._commit", side_effect=RuntimeError("db down")),
        caplog.at_level(logging.ERROR, logger="translator.events"),
    ):
        write_translation_event(
            backend="claude",
            source_lang="en",
            target_lang="de",
            lines_count=1,
            chars_in=1,
            started_at=datetime.now(UTC),
            status="ok",
        )
    assert any("failed" in r.message.lower() for r in caplog.records)
