"""Background-scheduler startup for the Sublarr Flask app.

Extracted from app.py. Called by create_app() (when not testing) to start
the wanted-scanner loop, DB backup job, standalone watcher, cleanup scheduler,
upgrade-candidate scheduler and AniDB absolute-episode sync.
"""

import logging

from extensions import socketio


def _start_schedulers(settings, app=None):
    """Start background schedulers (wanted scanner, database backup, standalone watcher, cleanup)."""  # noqa: D200
    from services.wanted_scanner import get_scanner

    scanner = get_scanner()
    scanner.start_scheduler(socketio=socketio, app=app)

    from database_backup import start_backup_scheduler

    start_backup_scheduler(
        db_path=settings.db_path,
        backup_dir=settings.backup_dir,
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
