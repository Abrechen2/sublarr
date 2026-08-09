"""Application factory for Sublarr Flask API server.

Uses the Flask Application Factory pattern: create_app() builds and
configures the application, initializes extensions, registers blueprints,
and starts background schedulers.

The low-level machinery (logging, routes, shutdown handlers, scheduler
bootstrap) lives in sibling modules app_logging / app_routes_core /
app_shutdown / app_schedulers so this file stays focused on the factory
itself.
"""

import hmac
import logging
import os

from flask import Flask, request

from app_logging import (  # re-exported for back-compat (tests import from app)
    LOG_FORMAT,
    SocketIOLogHandler,
    StructuredJSONFormatter,
    _has_app_context,
    _setup_logging,
    stamp_log_fingerprint,
)
from app_routes_core import _register_app_routes
from app_schedulers import _start_schedulers
from app_shutdown import _register_shutdown_handler
from extensions import limiter, socketio

__all__ = [
    "LOG_FORMAT",
    "SocketIOLogHandler",
    "StructuredJSONFormatter",
    "_has_app_context",
    "_setup_logging",
    "_register_app_routes",
    "_register_shutdown_handler",
    "_start_schedulers",
    "create_app",
    "limiter",
    "socketio",
]


def _patch_pre_alembic_columns(engine, inspect_fn) -> None:
    """Add columns missing from pre-Alembic databases.

    create_all() is a no-op on existing tables, so DBs created before Alembic
    was introduced may be missing columns added via later migrations.
    """
    import logging as _logging

    from sqlalchemy import text

    _log = _logging.getLogger(__name__)
    insp = inspect_fn(engine)
    patches = []

    if insp.has_table("subtitle_downloads"):
        existing = {c["name"] for c in insp.get_columns("subtitle_downloads")}
        if "source" not in existing:
            patches.append(
                "ALTER TABLE subtitle_downloads ADD COLUMN source TEXT DEFAULT 'provider'"
            )
        if "score_breakdown" not in existing:
            patches.append("ALTER TABLE subtitle_downloads ADD COLUMN score_breakdown TEXT")
        if "decision_log_json" not in existing:
            patches.append("ALTER TABLE subtitle_downloads ADD COLUMN decision_log_json TEXT")

    # Per-series ASS-only requirement (migration a4b5c6d7e8f9)
    if insp.has_table("series_settings"):
        existing = {c["name"] for c in insp.get_columns("series_settings")}
        if "subtitle_format_requirement" not in existing:
            patches.append(
                "ALTER TABLE series_settings ADD COLUMN subtitle_format_requirement TEXT"
            )

    # Per-profile provider selection + scoring preset (migration f8b2c3d4e5a6)
    if insp.has_table("language_profiles"):
        existing = {c["name"] for c in insp.get_columns("language_profiles")}
        if "enabled_providers_json" not in existing:
            patches.append("ALTER TABLE language_profiles ADD COLUMN enabled_providers_json TEXT")
        if "scoring_preset" not in existing:
            patches.append("ALTER TABLE language_profiles ADD COLUMN scoring_preset TEXT")

    # Split search/download success times (migration b7c8d9e0f1a2).
    # A column added by a migration MUST be repeated here: an install whose
    # alembic_version was stamped at head never replays the migration, and
    # create_all() adds missing tables but never missing columns — so the model
    # queries a column the database does not have and every worker dies at
    # boot. That is exactly how the beta instance went down on 2026-08-09.
    if insp.has_table("provider_stats"):
        existing = {c["name"] for c in insp.get_columns("provider_stats")}
        # The model declares DateTime(timezone=True). Spelling that as a bare
        # TIMESTAMP on Postgres would create a column the ORM then compares
        # against aware datetimes — the mixed-type trap that has produced 500s
        # in this codebase before.
        ts = "TIMESTAMP WITH TIME ZONE" if engine.dialect.name == "postgresql" else "TIMESTAMP"
        for column in ("last_search_at", "last_download_at"):
            if column not in existing:
                patches.append(f"ALTER TABLE provider_stats ADD COLUMN {column} {ts}")

    # Decision log snapshots (migration a7d3c9e1f5b2)
    if insp.has_table("wanted_items"):
        existing = {c["name"] for c in insp.get_columns("wanted_items")}
        if "last_decision_log_json" not in existing:
            patches.append("ALTER TABLE wanted_items ADD COLUMN last_decision_log_json TEXT")

    if not patches:
        return

    with engine.connect() as conn:
        for stmt in patches:
            conn.execute(text(stmt))
        conn.commit()

    _log.info("Pre-Alembic DB: patched %d missing column(s)", len(patches))


def create_app(testing=False):
    """Create and configure the Flask application.

    Args:
        testing: If True, skip scheduler startup (for tests and verification).

    Returns:
        Configured Flask application instance.
    """
    # static_folder=None disables Flask's built-in /<path:filename> route which
    # would intercept SPA routes (e.g. /wanted) and return 404 before our
    # catch-all serve_spa() can serve index.html. Static files are served by
    # serve_spa() itself via send_from_directory("static", ...).
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB — prevent request body DoS

    # Load config
    from config import get_settings, reload_settings, warn_on_ignored_env_vars

    settings = get_settings()

    # Set up logging. Everything below needs a logger, so this runs before the
    # config_entries overlay is read — which means `settings` here still holds
    # only ENV and defaults. The instance fingerprint is therefore NOT stamped
    # yet (stamp=False); it goes in once the overlay has been applied, further
    # down, or it would describe a half-loaded config.
    _setup_logging(settings, stamp=False)

    logger = logging.getLogger(__name__)

    # Warn (loudly, once per startup) about any SUBLARR_<ui_field> env vars
    # the operator has set. Since v0.88.0-beta the env-loadable surface is
    # the curated BootSettings allowlist; UI fields ignore env values
    # silently otherwise — this loop turns that silence into a logged
    # warning per ignored variable so the migration is visible.
    warn_on_ignored_env_vars()

    # Initialize SocketIO with the app — restrict origins to configured allowlist
    _cors_origins_raw = getattr(
        settings, "cors_origins", "http://localhost:5173,http://localhost:5765"
    )
    _cors_origins = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]
    socketio.init_app(app, cors_allowed_origins=_cors_origins, async_mode="threading")

    # Register structured error handlers (SublarrError -> JSON, generic 500)
    from error_handler import register_error_handlers

    register_error_handlers(app)

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Embedder-Policy", "credentialless")
        # CSP: allow self + inline styles + ws/wss for SocketIO.
        # script-src is strict (no 'unsafe-inline') for the SPA — its only inline
        # script (the pre-paint theme bootstrap) was moved to /theme-init.js so an
        # injected inline <script> can no longer execute. The Swagger UI bundle at
        # /api/docs* still ships inline bootstrap scripts, so that path keeps the
        # relaxed directive scoped to itself.
        # media-src needs blob: because the Waveform editor (WaveSurfer.js) fetches the
        # extracted audio from /api/v1/tools/waveform-audio/, wraps it in URL.createObjectURL(),
        # and feeds it into an internal <audio> element — which the browser charges against
        # media-src, not connect-src.
        if request.path.startswith("/api/docs"):
            script_src = "script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'; "
        else:
            script_src = "script-src 'self' 'wasm-unsafe-eval'; "
        response.headers.setdefault(
            "Content-Security-Policy",
            (
                "default-src 'self'; "
                + script_src
                + "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "img-src 'self' data: https:; "
                "media-src 'self' blob:; "
                "connect-src 'self' ws: wss:; "
                "font-src 'self' data: https://fonts.gstatic.com; "
                "frame-ancestors 'none'"
            ),
        )
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=()",
        )
        return response

    # Initialize rate limiter. In-memory counters are per-process, so under a
    # multi-worker Gunicorn deployment every worker keeps its own tally and the
    # effective limit becomes N×. When a Redis URL is configured, use it as the
    # shared storage backend so limits hold across workers (brute-force guard).
    _redis_url = getattr(settings, "redis_url", None)
    if _redis_url:
        app.config["RATELIMIT_STORAGE_URI"] = _redis_url
    limiter.init_app(app)

    # Initialize authentication
    from auth import init_auth
    from routes.auth_ui import auth_ui_bp
    from ui_auth import init_ui_auth

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

    from extensions import db as sa_db
    from extensions import migrate as sa_migrate

    sa_db.init_app(app)
    sa_migrate.init_app(app, sa_db, directory="db/migrations", render_as_batch=True)

    with app.app_context():
        # Import all models so they register with metadata
        # For new databases: create all tables (skip if Alembic already tracks schema)
        from sqlalchemy import inspect as _inspect

        import db.models  # noqa: F401

        if not _inspect(sa_db.engine).has_table("alembic_version"):
            sa_db.create_all()
            # NB: "untracked", not necessarily "new" — any DB that was first
            # created by create_all() never gets an alembic_version table, so
            # it takes this branch on every start for its whole lifetime and
            # relies on _patch_pre_alembic_columns() below for new columns.
            logger.info("Alembic-untracked DB: ran create_all()")
            # Pre-Alembic DB: patch any columns that were added via Alembic migrations
            # but are missing because create_all() is a no-op on existing tables.
            _patch_pre_alembic_columns(sa_db.engine, _inspect)
        else:
            # Run pending Alembic migrations automatically so new columns are always present
            try:
                from alembic import command as _alembic_cmd
                from alembic.config import Config as _AlembicConfig

                _alembic_cfg = _AlembicConfig()
                _alembic_cfg.set_main_option(
                    "script_location",
                    os.path.join(os.path.dirname(__file__), "db", "migrations"),
                )
                _alembic_cfg.set_main_option("sqlalchemy.url", str(sa_db.engine.url))
                _alembic_cmd.upgrade(_alembic_cfg, "head")
                logger.info("Alembic migrations applied (upgrade head)")
            except Exception as _e:
                # exc_info=True captures the full traceback so we can tell
                # *why* a migration failed. Without it this path logged an
                # empty reason for some exception types (e.g. AssertionError
                # from autocommit_block misuse), which hid a real bug for
                # weeks: the chain was pinned one revision behind head and
                # every subsequent migration silently skipped.
                logger.warning("Alembic auto-upgrade failed (non-fatal): %s", _e, exc_info=True)
        # ai_quality_results is created idempotently rather than via a migration.
        # This dates from the 2026-07-30 beta batch, when the chain still had
        # diverged heads; they were unified in eeb79287c3b6 and `upgrade head`
        # now succeeds, so the original reason no longer applies. The checkfirst
        # create is kept because it is also what gives Alembic-untracked DBs
        # (see the create_all branch above) this table at all.
        # TODO: fold into a real migration and drop this once untracked DBs are
        # stamped and migrated like every other install (ROADMAP).
        try:
            from db.models.quality import AIQualityResult

            AIQualityResult.__table__.create(bind=sa_db.engine, checkfirst=True)
        except Exception as _e:
            logger.warning("Could not ensure ai_quality_results table: %s", _e)
        # circuit_breaker_states is created by migration d5e6f7a8b9c0, but prod
        # and RC are stamped *downstream* of it and still lack the table — their
        # schema and alembic_version drifted apart at some point, so Alembic
        # considers a migration applied that never ran. Repair it idempotently
        # instead of hand-stamping revisions: checkfirst is a no-op wherever the
        # table is already present.
        try:
            from db.models.circuit_breaker import CircuitBreakerState

            CircuitBreakerState.__table__.create(bind=sa_db.engine, checkfirst=True)
        except Exception as _e:
            logger.warning("Could not ensure circuit_breaker_states table: %s", _e)
        # Enable SQLite WAL mode if using SQLite (match existing behavior)
        if not settings.database_url or settings.database_url.startswith("sqlite"):
            from sqlalchemy import text

            with sa_db.engine.connect() as conn:
                conn.execute(text("PRAGMA journal_mode=WAL"))
                conn.execute(text("PRAGMA busy_timeout=5000"))
                conn.commit()

            # Diagnostic: the #1 cause of "Sublarr is painfully slow" reports is
            # a SQLite DB on a microSD card or network share. Time a few commits
            # and warn if the /config volume is slow. Best-effort — never fatal.
            try:
                from db.storage_probe import warn_if_slow_storage

                warn_if_slow_storage(sa_db.engine)
            except Exception as _e:
                logger.debug("Storage probe skipped: %s", _e)

        # Initialize FTS5 search tables (virtual tables for global search)
        from db.search import init_search_tables, rebuild_search_index

        init_search_tables()
        try:
            rebuild_search_index()
            logger.info("FTS5 search index rebuilt on startup")
        except Exception as _e:
            logger.warning("FTS5 search index rebuild failed (non-fatal): %s", _e)

        # Initialize cache and queue backends
        from cache import create_cache_backend
        from job_queue import create_job_queue

        app.cache_backend = create_cache_backend(
            settings.redis_url if settings.redis_cache_enabled else ""
        )
        app.job_queue = create_job_queue(
            settings.redis_url if settings.redis_queue_enabled else "",
            max_workers=getattr(settings, "translation_max_workers", 4),
            app=app,
        )
        # Fail-loud on the silent-hang trap: an RQ backend with zero registered
        # workers accepts jobs and never runs them (no crash, no log). Surface
        # it at startup so a misconfigured deployment is obvious instead of
        # translation quietly doing nothing.
        try:
            _q_info = app.job_queue.get_backend_info()
            if _q_info.get("type") == "rq" and not _q_info.get("workers"):
                logger.error(
                    "Job queue is RQ but NO rq workers are registered — queued jobs "
                    "(translation, batch search) will hang forever. Start `python "
                    "worker.py` (see docker-compose.redis.yml) or set "
                    "redis_queue_enabled=false to use the in-process queue."
                )
        except Exception as _e:
            logger.debug("Could not inspect job queue backend info: %s", _e)

        # Initialize database (legacy -- no-op now that SQLAlchemy handles lifecycle)
        from db import init_db

        init_db()

        # Seed built-in cleanup rules that should exist on every fresh install.
        # Non-fatal: a failure here must never prevent the app from starting.
        try:
            from db.repositories.cleanup import CleanupRepository

            CleanupRepository().ensure_default_rules()
            logger.debug("Cleanup default rules seeded")
        except Exception as _e:
            logger.warning("Cleanup default rules seed failed (non-fatal): %s", _e)

        # Remove duplicate wanted_items rows that may exist in databases created
        # before the uq_wanted_file_lang_type UNIQUE constraint was added.
        # Keeps the row with the lowest rowid (earliest insert) for each
        # (file_path, target_language, subtitle_type) combination.
        try:
            from sqlalchemy import text as _text

            with sa_db.engine.connect() as _conn:
                _dedup_result = _conn.execute(
                    _text(
                        "DELETE FROM wanted_items WHERE id NOT IN ("
                        "  SELECT MIN(id) FROM wanted_items"
                        "  GROUP BY file_path,"
                        "    COALESCE(target_language, ''),"
                        "    COALESCE(subtitle_type, 'full')"
                        ")"
                    )
                )
                _conn.commit()
                if _dedup_result.rowcount:
                    logger.warning(
                        "wanted_items dedup: removed %d duplicate row(s) on startup",
                        _dedup_result.rowcount,
                    )
                else:
                    logger.debug("wanted_items dedup: no duplicates found")
        except Exception as _e:
            logger.warning("wanted_items dedup failed (non-fatal): %s", _e)

        # Mark any jobs stuck in "running" state as failed (zombie cleanup after crash/restart)
        if not testing:
            try:
                from db.jobs import get_jobs, update_job

                zombie_page = get_jobs(status="running", per_page=200)
                for zombie in zombie_page.get("data", []):
                    update_job(zombie["id"], "failed", error="Server restarted — job interrupted")
                    logger.info("Cleaned up zombie job %s", zombie["id"])
            except Exception as e:
                logger.warning("Zombie job cleanup failed: %s", e)

        # Initialize event system (SocketIO bridge + hook/webhook subscribers)
        from events import init_event_system
        from events.hooks import HookEngine, init_hook_subscribers
        from events.webhooks import WebhookDispatcher, init_webhook_subscribers

        init_event_system(app)

        hook_engine = HookEngine(max_workers=4, app=app)
        init_hook_subscribers(hook_engine)
        app.extensions["hook_engine"] = hook_engine

        webhook_dispatcher = WebhookDispatcher(max_workers=4, app=app)
        init_webhook_subscribers(webhook_dispatcher)
        app.extensions["webhook_dispatcher"] = webhook_dispatcher

        # Apply DB config overrides on startup (settings saved via UI take precedence)
        from db.config import get_all_config_entries, save_config_entry

        _db_overrides = get_all_config_entries()
        if _db_overrides:
            logger.info("Applying %d config overrides from database", len(_db_overrides))
            settings = reload_settings(_db_overrides)
            # Logging was set up above from ENV/defaults, before the DB was
            # read. Re-apply now so any UI-persisted logging setting takes
            # effect on startup (idempotent handler rebuild).
            from app_logging import LOGGING_CONFIG_KEYS

            if any(k in _db_overrides for k in LOGGING_CONFIG_KEYS):
                _setup_logging(settings)
        else:
            logger.info("No config overrides in database, using env/defaults")

        # Settings are complete now, so the log file can state which instance
        # wrote it. A no-op if the re-apply above already stamped this path.
        stamp_log_fingerprint()

        # Auto-generate API key on first start if not set via env or DB.
        # Skip when SUBLARR_API_KEY is explicitly set (even to "") — that means
        # the operator consciously chose to disable API-key auth (also covers tests).
        if not settings.api_key and "SUBLARR_API_KEY" not in os.environ:
            import secrets

            _generated_key = secrets.token_hex(32)
            save_config_entry("api_key", _generated_key)
            settings = reload_settings(get_all_config_entries())
            logger.info("API key auto-generated on first start (64 hex chars)")

        # Warn when both auth mechanisms are disabled — all API endpoints are public.
        # This is intentional for trusted-LAN / reverse-proxy deployments, but operators
        # should be aware of the exposure. See PENTEST_FINDINGS.md F-17.
        import ui_auth as _ui_auth

        _ui_auth_enabled = _ui_auth.is_ui_auth_enabled()
        if not settings.api_key and not _ui_auth_enabled:
            logger.warning(
                "SECURITY WARNING: No authentication is configured (api_key is empty and "
                "UI auth is disabled). All API endpoints are publicly accessible. "
                "Set SUBLARR_API_KEY or enable UI auth if this is not intentional."
            )

        # Initialize plugin system
        plugins_dir = getattr(settings, "plugins_dir", "")
        if plugins_dir:
            try:
                os.makedirs(plugins_dir, exist_ok=True)
            except PermissionError:
                import tempfile

                plugins_dir = tempfile.mkdtemp(prefix="sublarr_plugins_")
                logger.warning(
                    "Cannot create plugins_dir %s (permission denied), using temp: %s",
                    getattr(settings, "plugins_dir", ""),
                    plugins_dir,
                )
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

                    start_plugin_watcher(plugin_mgr, plugins_dir)
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
            from config import is_standalone_mode as _is_standalone_mode

            if _is_standalone_mode():
                from standalone import get_standalone_manager

                get_standalone_manager()
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
        def handle_connect(auth):
            from flask import session as _session

            from config import get_settings as _gs

            _api_key = getattr(_gs(), "api_key", None)
            if _api_key:
                # Same contract as the HTTP API gate: a logged-in UI session
                # counts. The Socket.IO handshake is an ordinary HTTP request
                # carrying the session cookie, so a browser that authenticated
                # via /auth/login but holds no key in localStorage (fresh
                # profile, or stale key after a server-side key change) must
                # not lose the WebSocket silently — that degraded log
                # streaming and live updates without any visible error.
                if _session.get("ui_authenticated"):
                    logger.debug("WebSocket client connected (UI session)")
                    return None
                provided = (auth or {}).get("apikey", "")
                if not hmac.compare_digest(provided, _api_key):
                    logger.warning("WebSocket connection rejected: invalid API key")
                    return False
            logger.debug("WebSocket client connected")

        @socketio.on("disconnect")
        def handle_disconnect():
            logger.debug("WebSocket client disconnected")

        # Accept (and ignore) any payload the client sends with the event.
        # flask-socketio forwards the emitted message data as a positional
        # argument, so a zero-arg handler raises "takes 0 positional arguments
        # but 1 was given" and the room join silently fails — dropping the Logs
        # page back to polling. `*_args` keeps the handler tolerant either way.
        @socketio.on("subscribe_logs")
        def _subscribe_logs(*_args):
            from flask_socketio import join_room

            join_room("logs")

        @socketio.on("unsubscribe_logs")
        def _unsubscribe_logs(*_args):
            from flask_socketio import leave_room

            leave_room("logs")

        # Register UI auth blueprint
        app.register_blueprint(auth_ui_bp)

        # Start schedulers (skip during testing)
        if not testing:
            _start_schedulers(settings, app)

        # Initialize UI auth (sets SECRET_KEY + before_request hook — must be LAST)
        init_ui_auth(app)

        # Register singletons in app.extensions for lifecycle visibility and test injection
        from providers import get_provider_manager as _gpm
        from services.wanted_scanner import get_scanner as _gs

        app.extensions["wanted_scanner"] = _gs()
        app.extensions["provider_manager"] = _gpm()

        # Register graceful shutdown handler (SIGTERM from Docker/Gunicorn)
        if not testing:
            _register_shutdown_handler(app)

    return app


if __name__ == "__main__":
    import os as _os

    from config import get_settings

    app = create_app()
    _debug = _os.environ.get("FLASK_DEBUG", "0") == "1"
    socketio.run(
        app, host="0.0.0.0", port=get_settings().port, debug=_debug, allow_unsafe_werkzeug=_debug
    )
