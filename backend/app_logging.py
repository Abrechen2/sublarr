"""Logging setup for the Sublarr Flask app.

Extracted from app.py to keep the factory module lean. Provides the
structured JSON formatter, the Flask-context-aware WebSocket log handler,
and the idempotent _setup_logging() routine called by create_app().
"""

import logging
import os
from logging.handlers import RotatingFileHandler

from extensions import socketio

# `[%(request_id)s]` sits AFTER the level and BEFORE the logger name on purpose.
# Two consumers parse these lines with anchored regexes — support._extract_top_errors
# matches `^<ts>,\d+\s+\[(ERROR|WARNING)\]\s+[^:]+:` and the frontend Logs page
# tests `line.includes('[ERROR]')`. Placing the id before the level would break
# the first; placing it in this slot leaves both intact, because `[^:]+` happily
# spans `[<id>] <logger>` and the request id never contains a colon.
LOG_FORMAT = "%(asctime)s [%(levelname)s] [%(request_id)s] %(name)s: %(message)s"

# Rendered for any record logged outside a Flask request context — scheduler
# ticks, background threads, third-party libraries.
NO_REQUEST_ID = "-"


def _current_request_id() -> str:
    """The active request's id, or a placeholder outside a request context."""
    if not _has_app_context():
        return NO_REQUEST_ID
    try:
        from flask import g

        return str(getattr(g, "request_id", NO_REQUEST_ID) or NO_REQUEST_ID)
    except Exception:
        return NO_REQUEST_ID


class RequestIdFilter(logging.Filter):
    """Backstop that guarantees `record.request_id` exists before formatting.

    The record factory below covers everything logged through the normal
    `Logger.*` path. This filter covers what it cannot: records built by direct
    `logging.LogRecord(...)` construction, which bypasses the factory entirely.
    Without one of the two, `%(request_id)s` raises inside `Formatter.format`,
    the record is dropped, and the traceback goes to stderr — a logging change
    that loses logs.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = _current_request_id()
        return True


def _install_request_id_factory() -> None:
    """Make every record carry `request_id`, idempotently.

    Idempotence is not optional here: _setup_logging runs again on every config
    save and on the startup DB overlay, and a wrapper installed per call would
    nest N deep. The marker attribute makes re-installation a no-op.
    """
    existing = logging.getLogRecordFactory()
    if getattr(existing, "_sublarr_request_id", False):
        return

    def factory(*args, **kwargs):
        record = existing(*args, **kwargs)
        if not hasattr(record, "request_id"):
            record.request_id = _current_request_id()
        return record

    factory._sublarr_request_id = True  # type: ignore[attr-defined]
    logging.setLogRecordFactory(factory)


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


# Rotation bounds and defaults. Single source of truth: PUT/GET
# /api/v1/logs/rotation imports these to validate input and to report the
# current window. They lived in two places before, and drifted — the API
# advertised 10 MB / 5 backups while the handler was hardcoded to 5 MB / 3, so
# the setting had no effect at all.
LOG_MAX_SIZE_MB_DEFAULT = 10
LOG_MAX_SIZE_MB_MIN = 1
LOG_MAX_SIZE_MB_MAX = 100
LOG_BACKUP_COUNT_DEFAULT = 5
LOG_BACKUP_COUNT_MIN = 1
LOG_BACKUP_COUNT_MAX = 20

# Config keys whose change requires _setup_logging() to run again. Two callers
# gate on this: the startup DB-overlay in app.py (logging is first configured
# from ENV/defaults before the DB is read) and the live-apply on config save in
# routes/config/core.py. Both previously hardcoded the level/file/format triple,
# which is why adding a rotation setting was not enough to make it take effect.
# tests/test_app_logging.py asserts this covers every `log_*` settings field.
LOGGING_CONFIG_KEYS = frozenset(
    {
        "log_level",
        "log_file",
        "log_format",
        "log_max_size_mb",
        "log_backup_count",
    }
)


def _clamped_int_setting(settings, name: str, default: int, low: int, high: int) -> int:
    """Read an integer rotation setting, clamped to [low, high].

    The value arrives from ``config_entries``, which is writable outside the
    route's validation (a direct DB edit, or a row written by a different
    version). Two failure modes are handled deliberately: a non-numeric row
    falls back to the default instead of stopping logging altogether, and the
    lower bound is never 0 because ``RotatingFileHandler`` reads
    ``maxBytes=0`` as "never roll over" — which would turn a size cap into
    unbounded growth.
    """
    raw = getattr(settings, name, default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logging.getLogger(__name__).warning(
            "Invalid %s=%r in config; falling back to %d", name, raw, default
        )
        return default
    return max(low, min(value, high))


def _in_container() -> bool:
    """Best-effort container detection. Cheap, and wrong-answer-safe."""
    if os.path.exists("/.dockerenv"):
        return True
    try:
        with open("/proc/1/cgroup", encoding="utf-8") as fh:
            return any(marker in fh.read() for marker in ("docker", "kubepods", "containerd"))
    except OSError:
        return False


def _fingerprint_payload(settings) -> str:
    """One line identifying the instance that wrote this log file.

    Answers, without a round trip to the reporter, the questions every bug
    report needs: which version, on what, in which deployment mode, against
    which database, and how much history this file can hold. Two Discord
    reports were stalled for weeks on exactly these facts.
    """
    import platform

    from version import __version__

    if getattr(settings, "database_url", ""):
        backend = "postgres" if "postgres" in settings.database_url.lower() else "external"
    else:
        backend = "sqlite"

    if getattr(settings, "standalone_enabled", False):
        mode = "standalone"
    elif getattr(settings, "sonarr_url", "") or getattr(settings, "radarr_url", ""):
        mode = "arr"
    else:
        mode = "unconfigured"

    max_size_mb = _clamped_int_setting(
        settings,
        "log_max_size_mb",
        LOG_MAX_SIZE_MB_DEFAULT,
        LOG_MAX_SIZE_MB_MIN,
        LOG_MAX_SIZE_MB_MAX,
    )
    backup_count = _clamped_int_setting(
        settings,
        "log_backup_count",
        LOG_BACKUP_COUNT_DEFAULT,
        LOG_BACKUP_COUNT_MIN,
        LOG_BACKUP_COUNT_MAX,
    )

    fields = [
        f"version={__version__}",
        f"python={platform.python_version()}",
        f"os={platform.system()} {platform.release()} ({platform.machine()})",
        f"container={'yes' if _in_container() else 'no'}",
        f"db={backend}",
        f"mode={mode}",
        f"level={getattr(settings, 'log_level', '?')}",
        f"rotation={max_size_mb}MBx{backup_count}",
    ]
    return "sublarr-instance: " + " ".join(fields)


class FingerprintedRotatingFileHandler(RotatingFileHandler):
    """RotatingFileHandler that stamps its instance fingerprint into every file.

    Writing the fingerprint once at startup is not durable: rotation moves it
    to `sublarr.log.1` and eventually off the end of the backup chain, so the
    file a user uploads after a long uptime carries no identity. Re-stamping on
    every rollover makes each file self-describing on its own.

    The stamp is written through this handler's own formatter, so it obeys the
    text/JSON choice, and it is built with the live LogRecord factory so any
    attribute other filters or formats rely on is present.
    """

    def __init__(self, *args, fingerprint: str = "", **kwargs):
        self._fingerprint = fingerprint
        super().__init__(*args, **kwargs)

    def _write_fingerprint(self) -> None:
        if not self._fingerprint or self.stream is None:
            return
        try:
            record = logging.getLogRecordFactory()(
                "app_logging",
                logging.INFO,
                __file__,
                0,
                self._fingerprint,
                None,
                None,
            )
            self.stream.write(self.format(record) + self.terminator)
            self.flush()
        except Exception:
            # A diagnostic aid must never be able to break the log it annotates.
            pass

    def stamp_if_new(self) -> None:
        """Stamp an empty target file — called once after setup."""
        try:
            if self.stream is not None and self.stream.tell() == 0:
                self._write_fingerprint()
        except Exception:
            pass

    def doRollover(self) -> None:  # noqa: N802 — stdlib camelCase override
        super().doRollover()
        self._write_fingerprint()


def rotated_log_candidates(settings=None) -> list[str]:
    """The active log file plus one path per configured backup, newest first.

    Every consumer that reads log history — the support ZIP, the top-error
    parser, the redaction preview — must agree with the handler about how many
    rotated files exist. They each hardcoded a depth of 3, which was correct
    only while ``backupCount`` was itself hardcoded to 3; once rotation became
    user-configurable the bundle silently dropped everything from ``.4`` on.

    Paths are returned whether or not they exist: callers already skip missing
    files, and probing here would race with a rollover happening mid-read.
    """
    if settings is None:
        from config import get_settings

        settings = get_settings()
    log_file = getattr(settings, "log_file", "log/sublarr.log")
    backup_count = _clamped_int_setting(
        settings,
        "log_backup_count",
        LOG_BACKUP_COUNT_DEFAULT,
        LOG_BACKUP_COUNT_MIN,
        LOG_BACKUP_COUNT_MAX,
    )
    return [log_file] + [f"{log_file}.{i}" for i in range(1, backup_count + 1)]


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
            server = getattr(self.sio, "server", None)
            if server is None or not server.manager.rooms.get("/", {}).get("logs"):
                return  # nobody watching the Logs page — skip all work
            msg = self._sanitize(self.format(record))
            self.sio.emit("log_entry", {"message": msg}, to="logs")
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
    # Before basicConfig: LOG_FORMAT references %(request_id)s, and the handler
    # basicConfig installs would format records that do not have it yet.
    _install_request_id_factory()
    logging.basicConfig(level=log_level, format=LOG_FORMAT)

    root = logging.getLogger()
    # basicConfig() is a no-op once the root logger already has handlers, so on
    # a re-run (settings-save → live re-apply) it would NOT update the level.
    # Set it explicitly to keep _setup_logging idempotent for level changes.
    root.setLevel(log_level)

    for noisy_name, noisy_level in _THIRD_PARTY_LOG_LEVELS.items():
        logging.getLogger(noisy_name).setLevel(noisy_level)

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

        max_size_mb = _clamped_int_setting(
            settings,
            "log_max_size_mb",
            LOG_MAX_SIZE_MB_DEFAULT,
            LOG_MAX_SIZE_MB_MIN,
            LOG_MAX_SIZE_MB_MAX,
        )
        backup_count = _clamped_int_setting(
            settings,
            "log_backup_count",
            LOG_BACKUP_COUNT_DEFAULT,
            LOG_BACKUP_COUNT_MIN,
            LOG_BACKUP_COUNT_MAX,
        )
        # Built before the handler so a broken fingerprint cannot stop logging
        # from being set up at all.
        try:
            fingerprint = _fingerprint_payload(settings)
        except Exception as exc:
            logging.getLogger(__name__).debug("Could not build log fingerprint: %s", exc)
            fingerprint = ""

        fh = FingerprintedRotatingFileHandler(
            log_file,
            maxBytes=max_size_mb * 1024 * 1024,
            backupCount=backup_count,
            encoding="utf-8",
            fingerprint=fingerprint,
        )
        fh.setLevel(log_level)
        fh.setFormatter(formatter)
        root.addHandler(fh)
        fh.stamp_if_new()
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

    # Every handler on root, not just ours: basicConfig installs a console
    # StreamHandler using LOG_FORMAT too, and a record reaching it without
    # `request_id` would raise inside Formatter.format.
    for handler in root.handlers:
        if not any(isinstance(f, RequestIdFilter) for f in handler.filters):
            handler.addFilter(RequestIdFilter())
