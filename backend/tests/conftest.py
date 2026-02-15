"""Shared pytest fixtures for all tests."""

import pytest
import os
import tempfile
import shutil
from pathlib import Path

from config import reload_settings
from db import init_db, get_db
from app import create_app


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    # Create temporary database file
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    
    # Set environment variable
    os.environ["SUBLARR_DB_PATH"] = db_path
    os.environ["SUBLARR_API_KEY"] = ""  # Disable auth for tests
    os.environ["SUBLARR_LOG_LEVEL"] = "ERROR"  # Reduce log noise in tests
    
    # Reload settings and initialize database
    reload_settings()
    init_db()
    
    yield db_path
    
    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)
    if "SUBLARR_DB_PATH" in os.environ:
        del os.environ["SUBLARR_DB_PATH"]
    if "SUBLARR_API_KEY" in os.environ:
        del os.environ["SUBLARR_API_KEY"]
    if "SUBLARR_LOG_LEVEL" in os.environ:
        del os.environ["SUBLARR_LOG_LEVEL"]


@pytest.fixture
def client(temp_db):
    """Create a test client for Flask app."""
    app = create_app(testing=True)
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False

    with app.test_client() as client:
        yield client


@pytest.fixture
def temp_dir():
    """Create a temporary directory for file operations."""
    temp_path = tempfile.mkdtemp()
    yield temp_path
    shutil.rmtree(temp_path)


@pytest.fixture
def sample_subtitle_file(temp_dir):
    """Create a sample subtitle file for testing."""
    subtitle_path = Path(temp_dir) / "test.ass"
    subtitle_content = """[Script Info]
Title: Test Subtitle
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Test subtitle line
"""
    subtitle_path.write_text(subtitle_content, encoding="utf-8")
    return str(subtitle_path)


@pytest.fixture
def mock_ollama(monkeypatch):
    """Mock the Ollama client (translate_all returns identity translations)."""
    from unittest.mock import MagicMock

    mock_client = MagicMock()
    mock_client.return_value = ["translated line 1", "translated line 2"]

    monkeypatch.setattr("ollama_client.translate_all", mock_client)
    return mock_client


@pytest.fixture
def mock_provider_manager(monkeypatch):
    """Mock the ProviderManager singleton."""
    from unittest.mock import MagicMock
    from providers.base import SubtitleResult, SubtitleFormat

    manager = MagicMock()
    manager.search.return_value = []
    manager.search_and_download_best.return_value = None
    manager.download.return_value = None
    manager._circuit_breakers = {}

    monkeypatch.setattr("providers.get_provider_manager", lambda: manager)
    return manager


@pytest.fixture
def create_test_subtitle(temp_dir):
    """Factory fixture to create test subtitle files (ASS or SRT)."""
    def _create(fmt="ass", lang="en", lines=None):
        if lines is None:
            lines = ["Hello World", "How are you"]

        base_path = Path(temp_dir) / f"test.{lang}"

        if fmt == "ass":
            content = "[Script Info]\nTitle: Test\nScriptType: v4.00+\n\n"
            content += "[V4+ Styles]\n"
            content += "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            content += "Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1\n\n"
            content += "[Events]\n"
            content += "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            for i, line in enumerate(lines):
                start = f"0:00:{i*3+1:02d}.00"
                end = f"0:00:{i*3+3:02d}.00"
                content += f"Dialogue: 0,{start},{end},Default,,0,0,0,,{line}\n"
            path = str(base_path) + ".ass"
        else:
            content = ""
            for i, line in enumerate(lines, 1):
                content += f"{i}\n00:00:{(i-1)*3+1:02d},000 --> 00:00:{(i-1)*3+3:02d},000\n{line}\n\n"
            path = str(base_path) + ".srt"

        Path(path).write_text(content, encoding="utf-8")
        return path

    return _create


@pytest.fixture
def mock_requests(monkeypatch):
    """Mock requests library for HTTP calls."""
    import requests
    
    class MockResponse:
        def __init__(self, json_data, status_code=200):
            self.json_data = json_data
            self.status_code = status_code
            self.text = str(json_data)
        
        def json(self):
            return self.json_data
        
        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.exceptions.HTTPError(f"HTTP {self.status_code}")
    
    def mock_get(*args, **kwargs):
        return MockResponse({})
    
    def mock_post(*args, **kwargs):
        return MockResponse({})
    
    monkeypatch.setattr(requests, "get", mock_get)
    monkeypatch.setattr(requests, "post", mock_post)
    
    return {"get": mock_get, "post": mock_post}
