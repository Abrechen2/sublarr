"""Application factory for Sublarr Flask API server.

Uses the Flask Application Factory pattern: create_app() builds and
configures the application, initializes extensions, registers blueprints,
and starts background schedulers.
"""

import os
import logging

from flask import Flask

from extensions import socketio

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


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

    def __init__(self, sio):
        super().__init__()
        self.sio = sio

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.sio.emit("log_entry", {"message": msg})
        except Exception:
            pass  # Never break the app because of log emission


def _setup_logging(settings) -> None:
    """Set up file handler and WebSocket handler on the root logger."""
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(level=log_level, format=LOG_FORMAT)

    root = logging.getLogger()

    # Determine formatter
    use_json = getattr(settings, "log_format", "text").lower() == "json"
    if use_json:
        formatter: logging.Formatter = StructuredJSONFormatter()
    else:
        formatter = logging.Formatter(LOG_FORMAT)

    # File handler
    log_file = settings.log_file
    try:
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        from logging.handlers import RotatingFileHandler
        fh = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
        fh.setLevel(log_level)
        fh.setFormatter(formatter)
        root.addHandler(fh)
    except Exception as e:
        logging.getLogger(__name__).warning("Could not set up log file %s: %s", log_file, e)

    # WebSocket handler (emits log_entry events to frontend)
    ws_handler = SocketIOLogHandler(socketio)
    ws_handler.setLevel(log_level)
    ws_handler.setFormatter(logging.Formatter(LOG_FORMAT))  # Always text for WebSocket
    root.addHandler(ws_handler)


def create_app(testing=False):
    """Create and configure the Flask application.

    Args:
        testing: If True, skip scheduler startup (for tests and verification).

    Returns:
        Configured Flask application instance.
    """
    app = Flask(__name__, static_folder="static", static_url_path="")

    # Load config
    from config import get_settings, reload_settings
    settings = get_settings()

    # Set up logging
    _setup_logging(settings)

    logger = logging.getLogger(__name__)

    # Initialize SocketIO with the app
    socketio.init_app(app, cors_allowed_origins="*", async_mode="threading")

    # Register structured error handlers (SublarrError -> JSON, generic 500)
    from error_handler import register_error_handlers
    register_error_handlers(app)

    # Initialize authentication
    from auth import init_auth
    init_auth(app)

    # Initialize database
    from db import init_db
    init_db()

    # Apply DB config overrides on startup (settings saved via UI take precedence)
    from db.config import get_all_config_entries
    _db_overrides = get_all_config_entries()
    if _db_overrides:
        logger.info("Applying %d config overrides from database", len(_db_overrides))
        settings = reload_settings(_db_overrides)
    else:
        logger.info("No config overrides in database, using env/defaults")

    # Bazarr deprecation warning
    if os.environ.get("SUBLARR_BAZARR_URL") or os.environ.get("SUBLARR_BAZARR_API_KEY"):
        logger.warning(
            "DEPRECATION: SUBLARR_BAZARR_URL/SUBLARR_BAZARR_API_KEY are set but Bazarr "
            "integration has been removed. Sublarr now has its own provider system."
        )

    # Register blueprints
    from routes import register_blueprints
    register_blueprints(app)

    # Register app-level routes (metrics, SPA fallback)
    _register_app_routes(app)

    # Register SocketIO events
    @socketio.on("connect")
    def handle_connect():
        logger.debug("WebSocket client connected")

    @socketio.on("disconnect")
    def handle_disconnect():
        logger.debug("WebSocket client disconnected")

    # Start schedulers (skip during testing)
    if not testing:
        _start_schedulers(settings)

    return app


def _register_app_routes(app):
    """Register app-level routes: /metrics and SPA fallback."""
    from flask import jsonify, send_from_directory

    @app.route("/metrics", methods=["GET"])
    def prometheus_metrics():
        """Prometheus metrics endpoint (unauthenticated)."""
        from metrics import generate_metrics
        from config import get_settings
        from flask import Response
        body, content_type = generate_metrics(get_settings().db_path)
        return Response(body, mimetype=content_type)

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_spa(path):
        """Serve the React SPA frontend."""
        import os
        static_dir = app.static_folder or "static"

        # Try to serve the exact file first
        if path and os.path.exists(os.path.join(static_dir, path)):
            return send_from_directory(static_dir, path)

        # Fallback to index.html for SPA routing
        index_path = os.path.join(static_dir, "index.html")
        if os.path.exists(index_path):
            return send_from_directory(static_dir, "index.html")

        # No frontend built yet — return API info
        return jsonify({
            "name": "Sublarr",
            "version": "0.1.0",
            "api": "/api/v1/health",
            "message": "Frontend not built. Run 'npm run build' in frontend/ first.",
        })


def _start_schedulers(settings):
    """Start background schedulers (wanted scanner, database backup)."""
    from wanted_scanner import get_scanner
    scanner = get_scanner()
    scanner.start_scheduler(socketio=socketio)

    from database_backup import start_backup_scheduler
    start_backup_scheduler(
        db_path=settings.db_path,
        backup_dir=settings.backup_dir,
    )


if __name__ == "__main__":
    from config import get_settings
    app = create_app()
    socketio.run(app, host="0.0.0.0", port=get_settings().port, debug=True, allow_unsafe_werkzeug=True)
