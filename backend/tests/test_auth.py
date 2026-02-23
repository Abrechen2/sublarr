"""Tests for auth.py — API key authentication."""

import os
import pytest
from flask import Flask
from config import reload_settings
from auth import require_api_key, init_auth


def test_no_auth_when_key_empty():
    """Test that auth is disabled when API key is empty."""
    if "SUBLARR_API_KEY" in os.environ:
        del os.environ["SUBLARR_API_KEY"]
    
    settings = reload_settings()
    assert settings.api_key == ""
    
    app = Flask(__name__)
    init_auth(app)
    # Should not raise any errors


def test_auth_required_when_key_set():
    """Test that auth is enabled when API key is set."""
    os.environ["SUBLARR_API_KEY"] = "test-key-123"
    settings = reload_settings()
    assert settings.api_key == "test-key-123"
    
    app = Flask(__name__)
    init_auth(app)
    
    # Cleanup
    del os.environ["SUBLARR_API_KEY"]
    reload_settings()


def test_require_api_key_decorator():
    """When API key is set, require it on protected endpoints."""
    app = Flask(__name__)

    @app.route("/test")
    @require_api_key
    def test_route():
        return {"status": "ok"}

    # Case 1: no API key configured — request should succeed
    os.environ.pop("SUBLARR_API_KEY", None)
    reload_settings()
    with app.test_client() as client:
        response = client.get("/test")
        assert response.status_code == 200

    # Case 2: API key configured — request without key should fail
    os.environ["SUBLARR_API_KEY"] = "test-key-123"
    reload_settings()
    try:
        with app.test_client() as client:
            response = client.get("/test")
            assert response.status_code == 401

            response_with_key = client.get("/test", headers={"X-Api-Key": "test-key-123"})
            assert response_with_key.status_code == 200
    finally:
        os.environ.pop("SUBLARR_API_KEY", None)
        reload_settings()
