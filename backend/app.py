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

    # ---- Flask-SQLAlchemy + Alembic initialization ----
    app.config["SQLALCHEMY_DATABASE_URI"] = settings.get_database_url()
    # Only set pool options for non-SQLite (SQLite uses StaticPool)
    if settings.database_url and not settings.database_url.startswith("sqlite"):
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "pool_size": settings.db_pool_size,
            "max_overflow": settings.db_pool_max_overflow,
            "pool_recycle": settings.db_pool_recycle,
            "pool_pre_ping": True,
        }
    else:
        # SQLite: use check_same_thread=False for thread safety
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "connect_args": {"check_same_thread": False},
        }

    from extensions import db as sa_db, migrate as sa_migrate
    sa_db.init_app(app)
    sa_migrate.init_app(app, sa_db, directory="db/migrations", render_as_batch=True)

    with app.app_context():
        # Import all models so they register with metadata
        import db.models  # noqa: F401
        # For new databases: create all tables
        sa_db.create_all()
        # Enable SQLite WAL mode if using SQLite (match existing behavior)
        if not settings.database_url or settings.database_url.startswith("sqlite"):
            from sqlalchemy import text
            with sa_db.engine.connect() as conn:
                conn.execute(text("PRAGMA journal_mode=WAL"))
                conn.execute(text("PRAGMA busy_timeout=5000"))
                conn.commit()

        # Initialize FTS5 search tables (virtual tables for global search)
        from db.search import init_search_tables
        init_search_tables()

        # Initialize cache and queue backends
        from cache import create_cache_backend
        from job_queue import create_job_queue
        app.cache_backend = create_cache_backend(
            settings.redis_url if settings.redis_cache_enabled else ""
        )
        app.job_queue = create_job_queue(
            settings.redis_url if settings.redis_queue_enabled else ""
        )

        # Initialize database (legacy -- no-op now that SQLAlchemy handles lifecycle)
        from db import init_db
        init_db()

        # Initialize event system (SocketIO bridge + hook/webhook subscribers)
        from events import init_event_system
        from events.hooks import HookEngine, init_hook_subscribers
        from events.webhooks import WebhookDispatcher, init_webhook_subscribers

        init_event_system(app)

        hook_engine = HookEngine(max_workers=4)
        init_hook_subscribers(hook_engine)

        webhook_dispatcher = WebhookDispatcher(max_workers=4)
        init_webhook_subscribers(webhook_dispatcher)

        # Apply DB config overrides on startup (settings saved via UI take precedence)
        from db.config import get_all_config_entries
        _db_overrides = get_all_config_entries()
        if _db_overrides:
            logger.info("Applying %d config overrides from database", len(_db_overrides))
            settings = reload_settings(_db_overrides)
        else:
            logger.info("No config overrides in database, using env/defaults")

        # Initialize plugin system
        plugins_dir = getattr(settings, "plugins_dir", "")
        if plugins_dir:
            os.makedirs(plugins_dir, exist_ok=True)
            from providers.plugins import init_plugin_manager
            plugin_mgr = init_plugin_manager(plugins_dir)
            loaded, plugin_errors = plugin_mgr.discover()
            if loaded:
                logger.info("Loaded %d plugins: %s", len(loaded), loaded)
            if plugin_errors:
                for err in plugin_errors:
                    logger.warning("Plugin load error: %s -- %s", err["file"], err["error"])

            # Start hot-reload watcher if enabled (optional -- watchdog must be installed)
            if not testing and getattr(settings, "plugin_hot_reload", False):
                try:
                    from providers.plugins.watcher import start_plugin_watcher
                    watcher = start_plugin_watcher(plugin_mgr, plugins_dir)
                    logger.info("Plugin hot-reload watcher started on %s", plugins_dir)
                except ImportError:
                    logger.warning("watchdog not installed, plugin hot-reload disabled")

        # Initialize media server manager (loads configured instances)
        try:
            from mediaserver import get_media_server_manager
            ms_manager = get_media_server_manager()
            ms_manager.load_instances()
            types = ms_manager.get_all_server_types()
            logger.info("Media server manager initialized: %d types registered", len(types))
        except Exception as e:
            logger.warning("Media server manager initialization failed: %s", e)

        # Initialize standalone manager (folder watching + scanning)
        try:
            from config import get_settings as _get_standalone_settings
            if getattr(_get_standalone_settings(), 'standalone_enabled', False):
                from standalone import get_standalone_manager
                standalone_mgr = get_standalone_manager()
                logger.info("Standalone manager initialized")
        except Exception as e:
            logger.warning("Standalone manager initialization failed: %s", e)

        # Bazarr deprecation warning
        if os.environ.get("SUBLARR_BAZARR_URL") or os.environ.get("SUBLARR_BAZARR_API_KEY"):
            logger.warning(
                "DEPRECATION: SUBLARR_BAZARR_URL/SUBLARR_BAZARR_API_KEY are set but Bazarr "
                "integration has been removed. Sublarr now has its own provider system."
            )

        # Register blueprints
        from routes import register_blueprints
        register_blueprints(app)

        # Register OpenAPI spec (must be after register_blueprints)
        from openapi import register_all_paths
        register_all_paths(app)

        # Register Swagger UI blueprint
        from flask_swagger_ui import get_swaggerui_blueprint
        swagger_bp = get_swaggerui_blueprint(
            "/api/docs",
            "/api/v1/openapi.json",
            config={"app_name": "Sublarr API", "layout": "BaseLayout"},
        )
        app.register_blueprint(swagger_bp)

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
            _start_schedulers(settings, app)

    return app


def _register_app_routes(app):
    """Register app-level routes: /metrics and SPA fallback."""
    from flask import jsonify, send_from_directory

    @app.route("/api/v1/metrics", methods=["GET"])
    def prometheus_metrics():
        """Prometheus metrics endpoint (protected by auth hook)."""
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
        from version import __version__
        return jsonify({
            "name": "Sublarr",
            "version": __version__,
            "api": "/api/v1/health",
            "message": "Frontend not built. Run 'npm run build' in frontend/ first.",
        })


def _start_schedulers(settings, app=None):
    """Start background schedulers (wanted scanner, database backup, standalone watcher, cleanup)."""
    from wanted_scanner import get_scanner
    scanner = get_scanner()
    scanner.start_scheduler(socketio=socketio, app=app)

    from database_backup import start_backup_scheduler
    start_backup_scheduler(
        db_path=settings.db_path,
        backup_dir=settings.backup_dir,
    )

    # Start standalone watcher if enabled
    if getattr(settings, 'standalone_enabled', False):
        try:
            from standalone import get_standalone_manager
            standalone_mgr = get_standalone_manager()
            standalone_mgr.start(socketio=socketio)
        except Exception as e:
            logging.getLogger(__name__).warning("Standalone watcher start failed: %s", e)

    # Start cleanup scheduler
    if app is not None:
        try:
            from cleanup_scheduler import start_cleanup_scheduler
            start_cleanup_scheduler(app, socketio)
        except Exception as e:
            logging.getLogger(__name__).warning("Cleanup scheduler start failed: %s", e)


if __name__ == "__main__":
    from config import get_settings
    app = create_app()
    socketio.run(app, host="0.0.0.0", port=get_settings().port, debug=True, allow_unsafe_werkzeug=True)
