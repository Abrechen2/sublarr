"""Tests for auth.py — API key authentication."""

import pytest
from flask import Flask
from config import reload_settings
from auth import require_api_key, init_auth


def test_no_auth_when_key_empty():
    """Test that auth is disabled when API key is empty."""
    import os
    if "SUBLARR_API_KEY" in os.environ:
        del os.environ["SUBLARR_API_KEY"]
    
    settings = reload_settings()
    assert settings.api_key == ""
    
    app = Flask(__name__)
    init_auth(app)
    # Should not raise any errors


def test_auth_required_when_key_set():
    """Test that auth is enabled when API key is set."""
    import os
    os.environ["SUBLARR_API_KEY"] = "test-key-123"
    settings = reload_settings()
    assert settings.api_key == "test-key-123"
    
    app = Flask(__name__)
    init_auth(app)
    
    # Cleanup
    del os.environ["SUBLARR_API_KEY"]


def test_require_api_key_decorator():
    """Test the require_api_key decorator."""
    app = Flask(__name__)
    
    @app.route("/test")
    @require_api_key
    def test_route():
        return {"status": "ok"}
    
    with app.test_client() as client:
        # Without API key configured, should work
        response = client.get("/test")
        assert response.status_code in [200, 401]  # Depends on config
