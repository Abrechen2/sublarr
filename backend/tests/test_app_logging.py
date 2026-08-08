"""Tests for app_logging._setup_logging third-party noise capping.

Regression guard for the 20s page-open report on low-power hosts
(Discord/Elric, DS920+, 1.9.4-rc.2): with log_level=DEBUG the root logger
level applied to EVERY library. rebulk (guessit's engine) emits ~155 DEBUG
records per filename parse; during a wanted-search burst that produced
~8k records/minute, each formatted twice (file + WebSocket handler),
written to disk, and emitted to connected browsers — saturating weak CPUs
and starving concurrent API requests.

User-selected DEBUG must apply to Sublarr's own loggers only; noisy
third-party libraries stay capped.
"""

import logging
from types import SimpleNamespace

import pytest

from app_logging import (
    LOG_BACKUP_COUNT_DEFAULT,
    LOG_BACKUP_COUNT_MAX,
    SocketIOLogHandler,
    _setup_logging,
)


@pytest.fixture
def restore_root_logger(tmp_path):
    """Snapshot and restore root logger + third-party logger levels."""
    root = logging.getLogger()
    prev_level = root.level
    prev_handlers = list(root.handlers)
    third_party = ["rebulk", "guessit", "watchdog", "urllib3", "apscheduler"]
    prev_tp_levels = {name: logging.getLogger(name).level for name in third_party}
    yield
    for handler in list(root.handlers):
        if handler not in prev_handlers:
            root.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass
    root.setLevel(prev_level)
    for name, level in prev_tp_levels.items():
        logging.getLogger(name).setLevel(level)


def _settings(tmp_path, level="DEBUG"):
    return SimpleNamespace(
        log_level=level,
        log_file=str(tmp_path / "sublarr.log"),
        log_format="text",
    )


def test_debug_level_caps_noisy_third_party_loggers(restore_root_logger, tmp_path):
    """log_level=DEBUG must NOT turn on rebulk/guessit/watchdog/urllib3 debug spam."""
    _setup_logging(_settings(tmp_path, "DEBUG"))

    for name in ("rebulk", "guessit", "watchdog", "urllib3"):
        assert logging.getLogger(name).getEffectiveLevel() >= logging.WARNING, (
            f"{name} must stay capped at WARNING even when Sublarr runs at DEBUG"
        )


def test_debug_level_keeps_apscheduler_at_info(restore_root_logger, tmp_path):
    """APScheduler job-run INFO lines are useful — cap at INFO, not WARNING."""
    _setup_logging(_settings(tmp_path, "DEBUG"))

    assert logging.getLogger("apscheduler").getEffectiveLevel() == logging.INFO


def test_debug_level_still_applies_to_sublarr_loggers(restore_root_logger, tmp_path):
    """Sublarr's own loggers must still honour the user-selected DEBUG level."""
    _setup_logging(_settings(tmp_path, "DEBUG"))

    assert logging.getLogger().level == logging.DEBUG
    assert logging.getLogger("providers.search_coordinator").getEffectiveLevel() == logging.DEBUG
    assert logging.getLogger("wanted_search.process").getEffectiveLevel() == logging.DEBUG


def test_websocket_handler_never_forwards_below_info(restore_root_logger, tmp_path):
    """The WebSocket log handler must not stream DEBUG records to browsers.

    Every record emitted to the root logger passes through SocketIOLogHandler
    and out to ALL connected clients. At DEBUG volume this floods both the
    server (per-record serialize + emit) and every open browser tab.
    """
    _setup_logging(_settings(tmp_path, "DEBUG"))

    ws_handlers = [h for h in logging.getLogger().handlers if isinstance(h, SocketIOLogHandler)]
    assert ws_handlers, "SocketIOLogHandler must be installed"
    assert all(h.level >= logging.INFO for h in ws_handlers)


class TestRotatedLogPaths:
    """Consumers of the rotated log files must follow the configured backup count.

    `routes/system/support.py` hardcoded `range(1, 4)` in three places — the
    top-error parser, the support ZIP, and the redaction preview. That matched
    exactly while backupCount was itself hardcoded to 3. Once rotation became
    configurable (default 5, up to 20), all three silently skipped every file
    from `.4` on, so the support bundle a user sends would be missing log
    history that exists on disk.
    """

    def test_lists_the_active_file_plus_one_entry_per_backup(self, tmp_path):
        from app_logging import rotated_log_candidates

        settings = _settings(tmp_path)
        settings.log_backup_count = 5
        paths = rotated_log_candidates(settings)

        base = str(tmp_path / "sublarr.log")
        assert paths == [base] + [f"{base}.{i}" for i in range(1, 6)]

    def test_follows_a_raised_backup_count(self, tmp_path):
        from app_logging import rotated_log_candidates

        settings = _settings(tmp_path)
        settings.log_backup_count = 20
        assert len(rotated_log_candidates(settings)) == 21

    def test_applies_the_same_clamping_as_the_handler(self, tmp_path):
        # A junk value must not produce a zero-length or absurd candidate list.
        from app_logging import rotated_log_candidates

        settings = _settings(tmp_path)
        settings.log_backup_count = 999
        assert len(rotated_log_candidates(settings)) == 1 + LOG_BACKUP_COUNT_MAX

        settings.log_backup_count = "nonsense"
        assert len(rotated_log_candidates(settings)) == 1 + LOG_BACKUP_COUNT_DEFAULT

    def test_support_module_does_not_hardcode_a_rotation_depth(self):
        """Guard the actual defect: a literal range(1, 4) over the log path."""
        from pathlib import Path

        import routes.system.support as support_mod

        source = Path(support_mod.__file__).read_text(encoding="utf-8")
        assert "range(1, 4)" not in source, (
            "support.py must derive rotated log paths from the configured backup "
            "count, not a hardcoded depth"
        )


def test_logging_config_keys_cover_every_log_setting():
    """Every `log_*` setting must be in LOGGING_CONFIG_KEYS.

    Two call sites re-run _setup_logging only when a logging-relevant key was
    among the changed config entries: the startup DB-overlay in app.py and the
    live-apply on config save in routes/config/core.py. Both used a hardcoded
    ("log_level", "log_file", "log_format") triple, so log_max_size_mb and
    log_backup_count were declared, persisted, read by _setup_logging — and the
    re-apply still never fired for them. Unit tests that call _setup_logging
    directly cannot catch that gap; this one can.
    """
    from app_logging import LOGGING_CONFIG_KEYS
    from config_settings import BootSettings, UISettings

    declared = {
        name
        for model in (BootSettings, UISettings)
        for name in model.model_fields
        if name.startswith("log_")
    }
    missing = declared - LOGGING_CONFIG_KEYS
    assert not missing, (
        f"log settings not covered by LOGGING_CONFIG_KEYS: {sorted(missing)} — "
        "changing them via the UI would not re-apply the logging setup"
    )


def _rotating_handler():
    """The RotatingFileHandler installed by _setup_logging."""
    from logging.handlers import RotatingFileHandler

    handlers = [h for h in logging.getLogger().handlers if isinstance(h, RotatingFileHandler)]
    assert handlers, "RotatingFileHandler must be installed"
    return handlers[-1]


class TestLogRotationConfig:
    """PUT /api/v1/logs/rotation persisted log_max_size_mb / log_backup_count and
    promised "Changes take effect on next application restart", but nothing ever
    read them: _setup_logging hardcoded 5 MB / 3. The setting was a placebo, and
    the API even advertised defaults (10 MB / 5) that did not match the real
    behaviour. This matters for support: at DEBUG a wanted-search burst writes
    ~8k records/min (see module docstring), so the retention window is minutes
    and raising it is the user's only lever.
    """

    def test_configured_max_size_is_applied(self, restore_root_logger, tmp_path):
        settings = _settings(tmp_path)
        settings.log_max_size_mb = 20
        _setup_logging(settings)

        assert _rotating_handler().maxBytes == 20 * 1024 * 1024

    def test_configured_backup_count_is_applied(self, restore_root_logger, tmp_path):
        settings = _settings(tmp_path)
        settings.log_backup_count = 7
        _setup_logging(settings)

        assert _rotating_handler().backupCount == 7

    def test_defaults_match_what_the_api_advertises(self, restore_root_logger, tmp_path):
        # GET /logs/rotation falls back to 10 MB / 5 when unset; the installed
        # handler must agree, or the UI reports a window the app does not use.
        _setup_logging(_settings(tmp_path))

        handler = _rotating_handler()
        assert handler.maxBytes == 10 * 1024 * 1024
        assert handler.backupCount == 5

    def test_zero_max_size_does_not_disable_rotation(self, restore_root_logger, tmp_path):
        # RotatingFileHandler treats maxBytes=0 as "never roll over", so a 0 in
        # config_entries would silently grow the log without bound — the worst
        # possible outcome for a setting meant to bound disk use.
        settings = _settings(tmp_path)
        settings.log_max_size_mb = 0
        _setup_logging(settings)

        assert _rotating_handler().maxBytes >= 1024 * 1024

    def test_out_of_range_values_are_clamped_to_the_api_bounds(self, restore_root_logger, tmp_path):
        # config_entries is writable outside the route's 1..100 / 1..20 checks
        # (direct DB edit, or a value written by another version).
        settings = _settings(tmp_path)
        settings.log_max_size_mb = 5000
        settings.log_backup_count = -3
        _setup_logging(settings)

        handler = _rotating_handler()
        assert handler.maxBytes == 100 * 1024 * 1024
        assert handler.backupCount == 1

    def test_non_numeric_value_falls_back_to_the_default(self, restore_root_logger, tmp_path):
        # config_entries stores strings; a corrupt row must not stop logging.
        settings = _settings(tmp_path)
        settings.log_max_size_mb = "not-a-number"
        _setup_logging(settings)

        assert _rotating_handler().maxBytes == 10 * 1024 * 1024


def test_ws_handler_skips_format_when_no_clients():
    from unittest.mock import MagicMock

    from app_logging import SocketIOLogHandler

    sio = MagicMock()
    sio.server.manager.rooms = {}  # no namespace → no clients
    handler = SocketIOLogHandler(sio)
    handler.format = MagicMock(side_effect=AssertionError("format ran with zero clients"))

    record = logging.LogRecord("x", logging.INFO, __file__, 1, "hello", None, None)
    handler.emit(record)
    sio.emit.assert_not_called()


def test_ws_handler_emits_when_client_connected():
    from unittest.mock import MagicMock

    from app_logging import SocketIOLogHandler

    sio = MagicMock()
    sio.server.manager.rooms = {"/": {"logs": {"sid1": True}}}
    handler = SocketIOLogHandler(sio)
    handler.setFormatter(logging.Formatter("%(message)s"))

    record = logging.LogRecord("x", logging.INFO, __file__, 1, "hello", None, None)
    handler.emit(record)
    sio.emit.assert_called_once()


def test_ws_handler_emits_to_logs_room_only():
    from unittest.mock import MagicMock

    from app_logging import SocketIOLogHandler

    sio = MagicMock()
    sio.server.manager.rooms = {"/": {"logs": {"sid1": True}}}
    handler = SocketIOLogHandler(sio)
    handler.setFormatter(logging.Formatter("%(message)s"))

    record = logging.LogRecord("x", logging.INFO, __file__, 1, "hello", None, None)
    handler.emit(record)

    _, kwargs = sio.emit.call_args
    assert kwargs.get("to") == "logs", "log_entry must be scoped to the logs room"


def test_ws_handler_skips_when_logs_room_empty():
    from unittest.mock import MagicMock

    from app_logging import SocketIOLogHandler

    sio = MagicMock()
    sio.server.manager.rooms = {"/": {None: {"sid1": True}}}  # connected, not subscribed
    handler = SocketIOLogHandler(sio)
    handler.format = MagicMock(side_effect=AssertionError("formatted for empty room"))

    record = logging.LogRecord("x", logging.INFO, __file__, 1, "hello", None, None)
    handler.emit(record)
    sio.emit.assert_not_called()
