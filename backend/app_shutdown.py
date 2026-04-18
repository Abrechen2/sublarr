"""Graceful shutdown handler for the Sublarr Flask app.

Extracted from app.py. Called by create_app() to install SIGTERM + atexit
hooks that cleanly stop background schedulers and watchers before process exit.
"""

import atexit
import logging
import signal


def _register_shutdown_handler(app):
    """Register handlers for graceful shutdown on SIGTERM/SIGINT.

    Docker sends SIGTERM when stopping a container. Gunicorn forwards it
    to workers. Without this handler, background threads (scanner, search,
    standalone watcher) keep running and prevent clean process exit,
    causing Docker to escalate to SIGKILL which fails in unprivileged LXC.
    """
    logger = logging.getLogger(__name__)

    def _graceful_shutdown(signum=None, frame=None):
        sig_name = signal.Signals(signum).name if signum else "atexit"
        logger.info("Graceful shutdown initiated (%s)", sig_name)

        try:
            scanner = app.extensions.get("wanted_scanner")
            if scanner:
                scanner.cancel_search()
                scanner.stop_scheduler()
                logger.info("Wanted scanner stopped")
        except Exception as e:
            logger.debug("Scanner shutdown error: %s", e)

        try:
            from standalone import get_standalone_manager

            get_standalone_manager().stop()
            logger.info("Standalone watcher stopped")
        except Exception:
            pass

        try:
            from cleanup_scheduler import stop_cleanup_scheduler

            stop_cleanup_scheduler()
        except Exception:
            pass
        try:
            from upgrade_scheduler import stop_upgrade_scheduler

            stop_upgrade_scheduler()
        except Exception:
            pass

        logger.info("Graceful shutdown complete")

    signal.signal(signal.SIGTERM, _graceful_shutdown)
    atexit.register(_graceful_shutdown)
