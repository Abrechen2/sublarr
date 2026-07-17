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

from app_logging import SocketIOLogHandler, _setup_logging


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
