"""Shared steps around a database restore.

A restore replaces the data every other part of the app is reading. The VM test
of 1.14.3-rc.4 showed three ways that went wrong, and each helper here closes one:

- ``release_db_connections``: the routes called ``db.close_db()``, a no-op since
  the move to SQLAlchemy, so SQLite's file was swapped under open pooled
  connections — "db_restored: true", then "disk I/O error".
- ``running_job_count``: replacing the data under a running job lets the job
  write its pre-restore view back. A restore is refused while jobs run.
- ``refresh_after_restore``: settings, API clients and the 60 s GET response
  cache kept serving the pre-restore state.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def release_db_connections() -> None:
    """Close this process's session and every pooled connection.

    Needed before a SQLite file is replaced (and harmless for PostgreSQL). The
    engine reconnects lazily on the next query.
    """
    try:
        from extensions import db

        db.session.remove()
        db.engine.dispose()
    except Exception as exc:  # noqa: BLE001 — no app context or engine: nothing is open
        logger.debug("release_db_connections: nothing to release (%s)", exc)


def running_job_count() -> int:
    """Number of translation jobs currently running."""
    from db.jobs import get_jobs

    return int(get_jobs(page=1, per_page=1, status="running").get("total", 0))


def refresh_after_restore() -> None:
    """Reload settings from the restored database and drop every derived cache."""
    from cache_response import invalidate_response_cache
    from config import reload_settings
    from db.config import get_all_config_entries

    reload_settings(get_all_config_entries())
    try:
        from mediaserver import invalidate_media_server_manager
        from providers import invalidate_manager
        from radarr_client import invalidate_client as invalidate_radarr
        from sonarr_client import invalidate_client as invalidate_sonarr

        invalidate_sonarr()
        invalidate_radarr()
        invalidate_media_server_manager()
        invalidate_manager()
    except Exception as exc:  # noqa: BLE001 — a stale client is not worth failing a restore
        logger.warning("Client cache invalidation failed after restore: %s", exc)
    invalidate_response_cache()
