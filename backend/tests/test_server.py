"""Tests for Flask API endpoints (app.py / Blueprint routes)."""

import os
import tempfile

import pytest

from app import create_app
from config import reload_settings
from db import close_db


@pytest.fixture
def client():
    """Create a test client."""
    # Use temp DB for tests
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["SUBLARR_DB_PATH"] = db_path
    os.environ["SUBLARR_API_KEY"] = ""  # Disable auth for tests
    reload_settings()

    app = create_app(testing=True)
    app.config["TESTING"] = True

    with app.test_client() as client:
        yield client

    # Cleanup — close DB connection before deleting (Windows file locking)
    close_db()
    if os.path.exists(db_path):
        os.unlink(db_path)
    if "SUBLARR_DB_PATH" in os.environ:
        del os.environ["SUBLARR_DB_PATH"]


def test_health_endpoint(client):
    """Test health check endpoint."""
    response = client.get("/api/v1/health")
    assert response.status_code in [200, 503]  # 503 if Ollama not running
    data = response.get_json()
    assert "status" in data
    assert "services" in data


def test_config_endpoint(client):
    """Test config endpoint."""
    response = client.get("/api/v1/config")
    assert response.status_code == 200
    data = response.get_json()
    assert "port" in data
    assert "target_language" in data


def test_stats_endpoint(client):
    """Test stats endpoint."""
    response = client.get("/api/v1/stats")
    assert response.status_code == 200
    data = response.get_json()
    assert "total_translated" in data
    assert "total_failed" in data


def test_jobs_endpoint(client):
    """Test jobs listing endpoint."""
    response = client.get("/api/v1/jobs")
    assert response.status_code == 200
    data = response.get_json()
    assert "data" in data
    assert "page" in data
    assert "total" in data


def test_translate_endpoint_missing_file(client):
    """Test translate endpoint with missing file."""
    response = client.post(
        "/api/v1/translate",
        json={"file_path": "/nonexistent/file.mkv"}
    )
    assert response.status_code == 404


def test_batch_status_endpoint(client):
    """Test batch status endpoint."""
    response = client.get("/api/v1/batch/status")
    assert response.status_code == 200
    data = response.get_json()
    assert "running" in data
    assert "total" in data
