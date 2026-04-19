"""TranslationEvent ORM model schema tests."""

from datetime import UTC, datetime

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


def test_tablename_and_columns():
    from db.models.translation import TranslationEvent

    assert TranslationEvent.__tablename__ == "translation_events"
    cols = {c.name for c in TranslationEvent.__table__.columns}
    assert cols == {
        "id",
        "backend",
        "source_lang",
        "target_lang",
        "lines_count",
        "chars_in",
        "chars_out",
        "tokens_in",
        "tokens_out",
        "cost_estimate_micro_usd",
        "cache_hit",
        "latency_ms",
        "status",
        "error_type",
        "error_msg",
        "job_id",
        "started_at",
        "finished_at",
    }


def test_indexes_exist():
    from db.models.translation import TranslationEvent

    index_names = {ix.name for ix in TranslationEvent.__table__.indexes}
    assert "ix_translation_events_backend_started_at" in index_names
    assert "ix_translation_events_started_at" in index_names
    assert "ix_translation_events_status" in index_names
    assert "ix_translation_events_job_id" in index_names


def test_default_cache_hit_false(app):
    from db.models.translation import TranslationEvent
    from extensions import db

    with app.app_context():
        row = TranslationEvent(
            backend="ollama",
            source_lang="en",
            target_lang="de",
            lines_count=10,
            chars_in=100,
            started_at=datetime.now(UTC),
            status="ok",
        )
        db.session.add(row)
        db.session.flush()
        assert row.cache_hit is False
        db.session.rollback()


def test_cost_is_bigint(app):
    from db.models.translation import TranslationEvent
    from extensions import db

    big_cost = 10**15  # bigger than 2**31 (signed 32-bit int)
    with app.app_context():
        row = TranslationEvent(
            backend="claude",
            source_lang="en",
            target_lang="de",
            lines_count=1,
            chars_in=1,
            cost_estimate_micro_usd=big_cost,
            started_at=datetime.now(UTC),
            status="ok",
        )
        db.session.add(row)
        db.session.flush()
        assert row.cost_estimate_micro_usd == big_cost
        db.session.rollback()
