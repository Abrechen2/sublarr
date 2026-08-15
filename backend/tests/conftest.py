"""Shared pytest fixtures for all tests."""

import os
import shutil
import tempfile
from pathlib import Path

# Resolve once — avoids 8.3 short-name vs long-name mismatch on Windows
_TEMP_DIR = os.path.realpath(tempfile.gettempdir())

# config_crypto writes the Fernet master key to ``{config_dir}/.encryption_key``
# (config_dir = SUBLARR_CONFIG_DIR, default ``/config``). Since 1.6.0 feature #6,
# create_app() encrypts the auto-generated api_key, so ANY test that builds its
# own app (not just the temp_db fixture) triggers that write. ``/config`` is not
# writable on the CI runner → PermissionError. Pin it to a session-local tmp dir
# at import time (before any create_app) so encryption always lands on a writable,
# isolated path. setdefault so an explicit override still wins.
# Only mint a dir when we actually own it — calling mkdtemp() unconditionally
# leaked one per session even when an explicit override won (1888 of them here).
if "SUBLARR_CONFIG_DIR" in os.environ:
    _SESSION_CONFIG_DIR = None
else:
    _SESSION_CONFIG_DIR = tempfile.mkdtemp(prefix="sublarr-cfg-")
    os.environ["SUBLARR_CONFIG_DIR"] = _SESSION_CONFIG_DIR

import pytest

from app import create_app
from config import reload_settings
from db import close_db, get_db, init_db


def pytest_sessionfinish(session, exitstatus):
    """Force-stop every leaked APScheduler daemon thread before pytest exits.

    Some scheduler-fixture teardowns use an aggressive 2-second
    ``shutdown(timeout_s=2)`` which can time out under CI load. APScheduler's
    ``BackgroundScheduler`` then keeps polling the SQLAlchemyJobStore even
    after pytest's ``tmp_path`` cleanup deletes the SQLite file — the daemon
    thread retries forever, hammering stderr with
    ``no such table: apscheduler_jobs`` and stretching a 2-minute pytest
    process to 48+ minutes (the actual GitHub Actions failure on PR #135 /
    Backend job 75162360308). This hook bypasses the per-instance
    ``_shutting_down`` guard and force-shuts every live SublarrScheduler so
    pytest exits cleanly.
    """
    try:
        from services.scheduler import SublarrScheduler

        SublarrScheduler._force_stop_all_for_test_cleanup()
    except Exception:  # noqa: BLE001 — best-effort cleanup, never block exit
        pass
    try:
        from services.background_tasks import shutdown_background

        shutdown_background(wait=False)
    except Exception:  # noqa: BLE001 -- best-effort cleanup, never block exit
        pass
    if _SESSION_CONFIG_DIR:
        shutil.rmtree(_SESSION_CONFIG_DIR, ignore_errors=True)


def _shutdown_event_dispatchers_for_test(app):
    try:
        from app_shutdown import shutdown_event_dispatchers

        shutdown_event_dispatchers(app)
    except Exception:  # noqa: BLE001 -- best-effort cleanup, never hide test failures
        pass


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database for testing.

    Everything lives under pytest's ``tmp_path`` so cleanup is *self-healing*.
    The previous ``NamedTemporaryFile(delete=False)`` + best-effort ``unlink``
    lost the file permanently whenever SQLite still held the WAL lock at
    teardown — and it never even tried to remove the ``-wal``/``-shm``
    siblings. On Windows nothing else ever collects ``%TEMP%``, so that leaked
    ~0.7 MB per test: 106k files / 71 GB in six weeks, still growing at ~3 GB
    per day. Under ``tmp_path`` a failed removal is merely deferred — pytest
    garbage-collects the whole session tree on a later run, by which time this
    process has exited and the lock is gone.
    """
    # Beside tmp_path, not inside it. Many tests hand `tmp_path` to the app as
    # a *media folder* and then assert on what it contains; `test.db` and its
    # `-wal`/`-shm` siblings are files, so anywhere under that root they show
    # up. A subdirectory is not enough — the standalone scanner walks
    # recursively and counted them as media. Together that broke 19 tests in
    # test_format_upgrade_alias and test_standalone_scanner.
    #
    # tmp_path.parent is pytest's numbered session directory, which pytest
    # garbage-collects wholesale on a later run — so the self-healing cleanup
    # this fixture is built around still holds. tmp_path.name is unique per
    # test, so two tests cannot collide here.
    db_dir = tmp_path.parent / f"{tmp_path.name}_db"
    db_dir.mkdir(exist_ok=True)
    db_path = str(db_dir / "test.db")
    # Pre-create the empty file so init_db() sees exactly what
    # NamedTemporaryFile used to hand it.
    Path(db_path).touch()

    # Set environment variable
    os.environ["SUBLARR_DB_PATH"] = db_path
    os.environ["SUBLARR_API_KEY"] = ""  # Disable auth for tests
    os.environ["SUBLARR_LOG_LEVEL"] = "ERROR"  # Reduce log noise in tests
    plugins_dir = tmp_path / "plugins"  # CI: /config not writable
    plugins_dir.mkdir()
    os.environ["SUBLARR_PLUGINS_DIR"] = str(plugins_dir)
    # Allow video-sync path-security check to pass for tmp_path fixtures
    os.environ["SUBLARR_MEDIA_PATH"] = _TEMP_DIR

    # Reload settings and initialize database
    reload_settings()
    init_db()

    yield db_path

    # Cleanup — close the DB so pytest's own tmp_path removal can succeed.
    # We deliberately do NOT unlink here: if this fails, pytest's retention
    # sweep reclaims the tree later. Nothing is left behind permanently.
    close_db()
    if "SUBLARR_DB_PATH" in os.environ:
        del os.environ["SUBLARR_DB_PATH"]
    if "SUBLARR_API_KEY" in os.environ:
        del os.environ["SUBLARR_API_KEY"]
    if "SUBLARR_LOG_LEVEL" in os.environ:
        del os.environ["SUBLARR_LOG_LEVEL"]
    if "SUBLARR_PLUGINS_DIR" in os.environ:
        del os.environ["SUBLARR_PLUGINS_DIR"]
    if "SUBLARR_MEDIA_PATH" in os.environ:
        del os.environ["SUBLARR_MEDIA_PATH"]
    reload_settings()  # clear singleton cached DB path


@pytest.fixture(autouse=True)
def _isolate_settings_env():
    """Snapshot + restore os.environ and the settings singleton around every test.

    Several route tests call reload_settings() which reads SUBLARR_* env vars and
    caches a process-global Settings singleton. Under xdist a test that mutates an
    env var (or leaves a reloaded singleton) could leak into later tests on the
    same worker, causing order-dependent flakes (e.g. subtitle_processor media-path
    checks). Restoring both makes each test start from a clean baseline.
    """
    import config_singleton

    snapshot = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(snapshot)
    config_singleton._settings = None


@pytest.fixture(autouse=True)
def _reset_budget_singleton():
    """Ensure every test sees a fresh ProviderBudgetManager singleton.

    Prevents order-dependent failures where a test that patches get_budget_manager
    leaves state visible to later tests in the same process.
    """
    from services.provider_budget import reset_singleton_for_tests

    reset_singleton_for_tests()
    yield
    reset_singleton_for_tests()


@pytest.fixture
def app_ctx(temp_db):
    """Provide Flask application context for DB-layer unit tests."""
    app = create_app(testing=True)
    with app.app_context():
        try:
            yield app
        finally:
            _shutdown_event_dispatchers_for_test(app)


@pytest.fixture
def client(temp_db):
    """Create a test client for Flask app."""
    app = create_app(testing=True)
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False

    with app.test_client() as client:
        try:
            yield client
        finally:
            _shutdown_event_dispatchers_for_test(app)


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

    from providers.base import SubtitleFormat, SubtitleResult

    manager = MagicMock()
    manager.search.return_value = []
    manager.search_and_download_best.return_value = None
    manager.download.return_value = None
    manager._circuit_breakers = {}

    monkeypatch.setattr("providers.get_provider_manager", lambda: manager)
    return manager


@pytest.fixture(autouse=True)
def reset_provider_manager():
    """Ensure each test ends with a clean provider manager singleton.

    Post-test teardown via invalidate_manager() is sufficient: it clears
    both the module-level _manager global (in providers.manager_singleton
    after the B1P T3 refactor) and any Flask app.extensions entry.
    Does NOT conflict with mock_provider_manager — that patches the getter function,
    while this resets the underlying singleton reference.
    """
    # Clear from extensions if an app context is already active (prevents stale mock bleed)
    try:
        from flask import current_app, has_app_context

        if has_app_context():
            current_app.extensions.pop("provider_manager", None)
    except RuntimeError:
        pass
    yield
    import providers as _prov_module

    _prov_module.invalidate_manager()  # post-test: shutdown cleanly, then null


@pytest.fixture(autouse=True)
def reset_wanted_scanner():
    """Reset WantedScanner singleton before each test.

    Symmetric fixture to reset_provider_manager — prevents stale scanner
    state from leaking between tests.
    Post-test uses invalidate_scanner() to stop the scheduler thread cleanly.
    """
    import services.wanted_scanner as _ws_module

    _ws_module._scanner = None
    # Clear from extensions if an app context is already active
    try:
        from flask import current_app, has_app_context

        if has_app_context():
            current_app.extensions.pop("wanted_scanner", None)
    except RuntimeError:
        pass
    yield
    _ws_module.invalidate_scanner()


@pytest.fixture
def mock_sonarr(monkeypatch):
    """Mock SonarrClient — patch at source module so all callers see the mock.

    NOTE: wanted_search.py imports get_sonarr_client lazily inside function bodies,
    so we must patch at sonarr_client.get_sonarr_client, NOT wanted_search.get_sonarr_client.
    Do not combine with mock_provider_manager in the same test if the code path calls both
    get_sonarr_client and get_provider_manager — fixture teardown order is not guaranteed.
    """

    class MockSonarrClient:
        def get_episode(self, episode_id):
            return {
                "id": episode_id,
                "title": "Test Episode",
                "seasonNumber": 1,
                "episodeNumber": 1,
                "series": {
                    "title": "Test Series",
                    "year": 2023,
                    "tvdbId": 12345,
                    "imdbId": "tt1234567",
                    "genres": ["Animation"],
                },
            }

        def get_series(self, series_id):
            return {
                "id": series_id,
                "title": "Test Series",
                "year": 2023,
                "tvdbId": 12345,
            }

    mock_instance = MockSonarrClient()
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: mock_instance)
    return mock_instance


@pytest.fixture
def mock_radarr(monkeypatch):
    """Mock RadarrClient — patch at source module.

    NOTE: Same lazy-import pattern as sonarr — patch at radarr_client.get_radarr_client.
    Do not combine with mock_provider_manager in the same test if the code path calls both
    get_radarr_client and get_provider_manager — fixture teardown order is not guaranteed.
    """

    class MockRadarrClient:
        def get_movie(self, movie_id):
            return {
                "id": movie_id,
                "title": "Test Movie",
                "year": 2023,
                "tmdbId": 99999,
                "imdbId": "tt9999999",
                "genres": ["Action"],
            }

    mock_instance = MockRadarrClient()
    monkeypatch.setattr("radarr_client.get_radarr_client", lambda *a, **kw: mock_instance)
    return mock_instance


@pytest.fixture
def provider_error_factory():
    """Factory for mock providers that raise specific errors on search/download."""

    def _make(error_class=Exception, message="provider error", name="failing_provider"):
        class FailingProvider:
            pass

        FailingProvider.name = name

        def search(self, query):
            raise error_class(message)

        def download(self, result):
            raise error_class(message)

        FailingProvider.search = search
        FailingProvider.download = download

        return FailingProvider()

    return _make


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
            content += (
                "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            )
            for i, line in enumerate(lines):
                start = f"0:00:{i * 3 + 1:02d}.00"
                end = f"0:00:{i * 3 + 3:02d}.00"
                content += f"Dialogue: 0,{start},{end},Default,,0,0,0,,{line}\n"
            path = str(base_path) + ".ass"
        else:
            content = ""
            for i, line in enumerate(lines, 1):
                content += f"{i}\n00:00:{(i - 1) * 3 + 1:02d},000 --> 00:00:{(i - 1) * 3 + 3:02d},000\n{line}\n\n"
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
