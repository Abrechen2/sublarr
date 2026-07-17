"""Logging setup for the Sublarr Flask app.

Extracted from app.py to keep the factory module lean. Provides the
structured JSON formatter, the Flask-context-aware WebSocket log handler,
and the idempotent _setup_logging() routine called by create_app().
"""

import logging
import os

from extensions import socketio

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

# Noisy third-party loggers stay capped regardless of the user-selected level.
# rebulk (guessit's rule engine) emits ~155 DEBUG records per filename parse;
# at DEBUG root level a single wanted-search burst produced ~8k records/min,
# each formatted twice (file + WebSocket handler), written to disk, and
# emitted to every connected browser — enough to starve concurrent API
# requests on low-power hosts (20s page opens on a Synology DS920+).
# The user-selected level still applies to all of Sublarr's own loggers.
_THIRD_PARTY_LOG_LEVELS = {
    "rebulk": logging.WARNING,
    "guessit": logging.WARNING,
    "watchdog": logging.WARNING,
    "urllib3": logging.WARNING,
    "chardet": logging.WARNING,
    "charset_normalizer": logging.WARNING,
    "engineio": logging.WARNING,
    "socketio": logging.WARNING,
    "apscheduler": logging.INFO,  # job-run lines are useful — keep INFO
}


class StructuredJSONFormatter(logging.Formatter):
    """JSON log formatter for structured logging (ELK, Loki, etc.)."""

    def format(self, record: logging.LogRecord) -> str:
        import json as _json

        from flask import g as _g

        entry = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        request_id = getattr(_g, "request_id", None) if _has_app_context() else None
        if request_id:
            entry["request_id"] = request_id

        if record.exc_info and record.exc_info[1]:
            entry["exception"] = {
                "type": type(record.exc_info[1]).__name__,
                "message": str(record.exc_info[1]),
            }

        return _json.dumps(entry, default=str)


def _has_app_context() -> bool:
    """Check if Flask application context is active (avoids import cycle)."""
    try:
        from flask import has_app_context

        return has_app_context()
    except Exception:
        return False


class SocketIOLogHandler(logging.Handler):
    """Emits log entries to connected WebSocket clients."""

    _DB_ERROR_PATTERNS = ("psycopg2.errors.", "psycopg2.exc.", "sqlalchemy.exc.")

    def __init__(self, sio):
        super().__init__()
        self.sio = sio

    @staticmethod
    def _sanitize(message: str) -> str:
        """Strip DB-internal error details before emitting to WebSocket clients.

        Replaces the portion of the message starting at the DB exception class name
        with a generic placeholder so that table names, column names, and query
        fragments never reach browser clients.
        """
        for pattern in SocketIOLogHandler._DB_ERROR_PATTERNS:
            idx = message.find(pattern)
            if idx != -1:
                return message[:idx] + "Database error (details hidden)"
        return message

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self._sanitize(self.format(record))
            self.sio.emit("log_entry", {"message": msg})
        except Exception:
            pass  # Never break the app because of log emission


def _setup_logging(settings) -> None:
    """Set up file handler and WebSocket handler on the root logger.

    Idempotent: removes any previously-installed Sublarr handlers before
    re-adding them. create_app() can be called more than once in the same
    process (tests, WSGI reloaders) — without this guard each invocation
    leaks another RotatingFileHandler + SocketIOLogHandler, producing N-fold
    duplicated log lines.
    """
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(level=log_level, format=LOG_FORMAT)

    root = logging.getLogger()
    # basicConfig() is a no-op once the root logger already has handlers, so on
    # a re-run (settings-save → live re-apply) it would NOT update the level.
    # Set it explicitly to keep _setup_logging idempotent for level changes.
    root.setLevel(log_level)

    for noisy_name, noisy_level in _THIRD_PARTY_LOG_LEVELS.items():
        logging.getLogger(noisy_name).setLevel(noisy_level)

    from logging.handlers import RotatingFileHandler

    for existing in list(root.handlers):
        if isinstance(existing, (RotatingFileHandler, SocketIOLogHandler)):
            root.removeHandler(existing)
            try:
                existing.close()
            except Exception:
                pass

    use_json = getattr(settings, "log_format", "text").lower() == "json"
    if use_json:
        formatter: logging.Formatter = StructuredJSONFormatter()
    else:
        formatter = logging.Formatter(LOG_FORMAT)

    log_file = settings.log_file
    try:
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        fh = RotatingFileHandler(
            log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        fh.setLevel(log_level)
        fh.setFormatter(formatter)
        root.addHandler(fh)
    except Exception as e:
        logging.getLogger(__name__).warning("Could not set up log file %s: %s", log_file, e)

    ws_handler = SocketIOLogHandler(socketio)
    # Never stream DEBUG records to browsers: every record goes to ALL
    # connected clients, and DEBUG volume floods both the server (per-record
    # serialize + emit) and every open tab. The Logs page still shows DEBUG
    # lines via its 10s file-backed API poll.
    ws_handler.setLevel(max(log_level, logging.INFO))
    ws_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(ws_handler)
