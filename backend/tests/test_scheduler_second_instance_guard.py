"""SUBLARR_SCHEDULER_ROLE env var guard."""

import logging

import pytest


def test_role_primary_starts_scheduler(monkeypatch, tmp_path, caplog):
    monkeypatch.setenv("SUBLARR_SCHEDULER_ROLE", "primary")
    monkeypatch.setenv("SUBLARR_DB_PATH", str(tmp_path / "app.db"))
    from config import reload_settings

    reload_settings()
    from app import create_app

    app = create_app(testing=True)
    from extensions import db as sa_db

    with app.app_context():
        sa_db.create_all()

    from services.scheduler import bootstrap_scheduler

    with caplog.at_level(logging.INFO, logger="services.scheduler"):
        s = bootstrap_scheduler(app)
    assert s is not None
    assert s.running is True
    s.shutdown(timeout_s=2)


def test_role_disabled_skips_scheduler(monkeypatch, tmp_path, caplog):
    monkeypatch.setenv("SUBLARR_SCHEDULER_ROLE", "disabled")
    monkeypatch.setenv("SUBLARR_DB_PATH", str(tmp_path / "app.db"))
    from config import reload_settings

    reload_settings()
    from app import create_app

    app = create_app(testing=True)
    from extensions import db as sa_db

    with app.app_context():
        sa_db.create_all()

    from services.scheduler import bootstrap_scheduler

    with caplog.at_level(logging.INFO, logger="services.scheduler"):
        s = bootstrap_scheduler(app)
    assert s is None
    assert any("skipping scheduler" in r.message.lower() for r in caplog.records)


def test_role_default_is_primary(monkeypatch, tmp_path):
    monkeypatch.delenv("SUBLARR_SCHEDULER_ROLE", raising=False)
    monkeypatch.setenv("SUBLARR_DB_PATH", str(tmp_path / "app.db"))
    from config import reload_settings

    reload_settings()
    from app import create_app

    app = create_app(testing=True)
    from extensions import db as sa_db

    with app.app_context():
        sa_db.create_all()

    from services.scheduler import bootstrap_scheduler

    s = bootstrap_scheduler(app)
    assert s is not None
    s.shutdown(timeout_s=2)


def test_role_invalid_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("SUBLARR_SCHEDULER_ROLE", "garbage")
    monkeypatch.setenv("SUBLARR_DB_PATH", str(tmp_path / "app.db"))
    from config import reload_settings

    reload_settings()
    from app import create_app

    app = create_app(testing=True)
    from extensions import db as sa_db

    with app.app_context():
        sa_db.create_all()

    from services.scheduler import bootstrap_scheduler

    with pytest.raises(ValueError, match="SUBLARR_SCHEDULER_ROLE"):
        bootstrap_scheduler(app)
