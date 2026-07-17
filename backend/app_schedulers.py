"""Background-scheduler startup for the Sublarr Flask app.

Phase 5 / P4: the four legacy threading.Timer schedulers (wanted_scanner,
cleanup, upgrade, anidb_sync) have been migrated into APScheduler JobSpecs
registered in services/scheduler.py. ``bootstrap_scheduler`` therefore
runs FIRST; then the per-site adapter functions push the user-configured
interval through to APScheduler via ``scheduler.modify_trigger``.
"""

import logging
import threading

from extensions import socketio

logger = logging.getLogger(__name__)


def _start_schedulers(settings, app=None):
    """Start background schedulers.

    Order matters: APScheduler bootstraps first so the per-site adapters
    can call ``modify_trigger`` on the live JobSpecs.
    """
    # 1. APScheduler bootstrap (registers JobSpecs + starts scheduler).
    if app is not None:
        from services.scheduler import bootstrap_scheduler

        try:
            bootstrap_scheduler(app)
        except Exception:
            logger.error("scheduler: bootstrap failed", exc_info=True)
            app.extensions["scheduler"] = None

    # 2. Per-site adapters — push current config intervals into APScheduler.
    from services.wanted_scanner import get_scanner

    scanner = get_scanner()
    scanner.start_scheduler(socketio=socketio, app=app, on_startup=True)

    from database_backup import start_backup_scheduler

    start_backup_scheduler(
        db_path=settings.db_path,
        backup_dir=settings.backup_dir,
        app=app,
    )

    from config import is_standalone_mode

    if is_standalone_mode():
        try:
            from standalone import get_standalone_manager

            standalone_mgr = get_standalone_manager()
            standalone_mgr.start(socketio=socketio, app=app)
        except Exception as e:
            logging.getLogger(__name__).warning("Standalone watcher start failed: %s", e)

    if app is not None:
        try:
            from cleanup_scheduler import start_cleanup_scheduler

            start_cleanup_scheduler(app, socketio)
        except Exception as e:
            logging.getLogger(__name__).warning("Cleanup scheduler start failed: %s", e)

    if app is not None:
        try:
            from upgrade_scheduler import start_upgrade_scheduler

            start_upgrade_scheduler(app)
        except Exception as e:
            logging.getLogger(__name__).warning("Upgrade scheduler start failed: %s", e)

    if app is not None:
        try:
            from anidb_sync import start_anidb_sync_scheduler

            start_anidb_sync_scheduler(app)
        except Exception as e:
            logging.getLogger(__name__).warning("AniDB sync scheduler start failed: %s", e)

    def _warm_anidb_index():
        try:
            from anidb_mapper import warm_title_index

            warm_title_index()
        except Exception:
            logging.getLogger(__name__).debug("startup anidb index warm failed", exc_info=True)

    threading.Thread(target=_warm_anidb_index, name="anidb-index-warm", daemon=True).start()
