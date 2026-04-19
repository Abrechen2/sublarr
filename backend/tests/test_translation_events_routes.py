"""API tests for /api/v1/translation/* (cost + memory + concurrency)."""

from datetime import UTC, datetime, timedelta

import pytest


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBLARR_DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("SUBLARR_API_KEY", "")
    monkeypatch.setenv("SUBLARR_SCHEDULER_ROLE", "disabled")
    from config import reload_settings

    reload_settings()
    from app import create_app

    app = create_app(testing=True)
    from extensions import db as sa_db

    with app.app_context():
        sa_db.create_all()
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def seed_events(app):
    """Seed 5 events: 3 ollama (zero cost) + 2 claude ($0.005 each)."""
    from db.models.translation import TranslationEvent
    from extensions import db

    now = datetime.now(UTC)
    with app.app_context():
        for i in range(3):
            db.session.add(
                TranslationEvent(
                    backend="ollama",
                    source_lang="en",
                    target_lang="de",
                    lines_count=10,
                    chars_in=100,
                    status="ok",
                    cost_estimate_micro_usd=0,
                    cache_hit=False,
                    started_at=now - timedelta(hours=i),
                )
            )
        for i in range(2):
            db.session.add(
                TranslationEvent(
                    backend="claude",
                    source_lang="en",
                    target_lang="de",
                    lines_count=10,
                    chars_in=100,
                    status="ok",
                    cost_estimate_micro_usd=5000,  # $0.005
                    cache_hit=False,
                    started_at=now - timedelta(hours=i),
                )
            )
        db.session.commit()


def test_get_cost_summary(app, client, seed_events):
    resp = client.get("/api/v1/translation/cost")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "today" in data and "last_7d" in data and "last_30d" in data
    # 2 claude events * $0.005 = $0.01
    assert abs(data["today"]["cost_usd"] - 0.01) < 0.0001
    assert data["today"]["events"] == 5


def test_get_cost_by_backend(app, client, seed_events):
    resp = client.get("/api/v1/translation/cost/by-backend?window=7d")
    assert resp.status_code == 200
    data = resp.get_json()
    backends = {b["backend"]: b for b in data["backends"]}
    assert "ollama" in backends and "claude" in backends
    assert abs(backends["claude"]["cost_usd"] - 0.01) < 0.0001
    assert backends["ollama"]["cost_usd"] == 0.0


def test_get_memory_stats(app, client):
    resp = client.get("/api/v1/translation/memory/stats")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "rows" in data
    assert "hit_rate_7d" in data
    assert "size_bytes" in data


def test_post_memory_purge(app, client):
    """Purge endpoint accepts + returns deletion count."""
    resp = client.post(
        "/api/v1/translation/memory/purge",
        json={"older_than_days": 30},
    )
    assert resp.status_code == 202
    data = resp.get_json()
    assert "deleted" in data


def test_get_cost_requires_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBLARR_DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("SUBLARR_API_KEY", "secret123")
    monkeypatch.setenv("SUBLARR_SCHEDULER_ROLE", "disabled")
    from config import reload_settings

    reload_settings()
    from app import create_app

    app = create_app(testing=True)
    from extensions import db as sa_db

    with app.app_context():
        sa_db.create_all()
    resp = app.test_client().get("/api/v1/translation/cost")
    assert resp.status_code == 401


def test_get_concurrency(app, client):
    from translation.concurrency import get_concurrency, reset_for_tests

    reset_for_tests()
    get_concurrency().register("ollama", 3)

    resp = client.get("/api/v1/translation/concurrency")
    assert resp.status_code == 200
    data = resp.get_json()
    assert any(b["backend"] == "ollama" and b["limit"] == 3 for b in data["backends"])


def test_patch_concurrency_limit(app, client):
    from translation.concurrency import get_concurrency, reset_for_tests

    reset_for_tests()
    get_concurrency().register("ollama", 3)

    resp = client.patch(
        "/api/v1/translation/concurrency/ollama",
        json={"limit": 5},
    )
    assert resp.status_code == 200
    assert get_concurrency().get_limit("ollama") == 5


def test_patch_concurrency_invalid_limit(app, client):
    from translation.concurrency import get_concurrency, reset_for_tests

    reset_for_tests()
    get_concurrency().register("ollama", 3)

    resp = client.patch(
        "/api/v1/translation/concurrency/ollama",
        json={"limit": 0},
    )
    assert resp.status_code == 400
