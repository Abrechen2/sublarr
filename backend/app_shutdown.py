"""Graceful shutdown handler for the Sublarr Flask app.

Extracted from app.py. Called by create_app() to install SIGTERM + atexit
hooks that cleanly stop background schedulers and watchers before process exit.
"""

import atexit
import logging
import signal


def shutdown_event_dispatchers(app, logger=None):
    """Stop HookEngine/WebhookDispatcher instances registered on the app."""
    logger = logger or logging.getLogger(__name__)
    for key, label in (
        ("hook_engine", "Hook engine"),
        ("webhook_dispatcher", "Webhook dispatcher"),
    ):
        try:
            dispatcher = app.extensions.pop(key, None)
            if dispatcher is not None:
                dispatcher.shutdown()
                logger.info("%s shutdown complete", label)
        except Exception:
            logger.debug("%s shutdown error", key, exc_info=True)


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
            scheduler = app.extensions.get("scheduler")
            if scheduler is not None:
                scheduler.shutdown(timeout_s=25)
                logger.info("Scheduler shutdown complete")
        except Exception:
            logger.error("scheduler: shutdown raised", exc_info=True)

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
            logger.debug("standalone watcher shutdown error", exc_info=True)

        try:
            from cleanup_scheduler import stop_cleanup_scheduler

            stop_cleanup_scheduler()
        except Exception:
            logger.debug("cleanup scheduler shutdown error", exc_info=True)
        try:
            from upgrade_scheduler import stop_upgrade_scheduler

            stop_upgrade_scheduler()
        except Exception:
            logger.debug("upgrade scheduler shutdown error", exc_info=True)

        shutdown_event_dispatchers(app, logger)

        # Stop accepting new fire-and-forget background tasks and cancel any
        # still queued so the process can exit promptly (Docker SIGTERM grace).
        try:
            from services.background_tasks import shutdown_background

            shutdown_background(wait=False)
        except Exception:
            logger.debug("background task executor shutdown error", exc_info=True)

        # Plan B6 follow-up — drain the post-processing executor so in-flight
        # ops (webhooks, plex_refresh, etc.) finish cleanly before process exit.
        try:
            from post_processing.pipeline import shutdown_executor

            shutdown_executor(wait=True)
            logger.info("Post-processing executor shutdown complete")
        except Exception:
            logger.debug("post_processing shutdown error", exc_info=True)

        logger.info("Graceful shutdown complete")

    signal.signal(signal.SIGTERM, _graceful_shutdown)
    atexit.register(_graceful_shutdown)
