"""Best-effort media-server refresh after Sublarr modifies a media item.

A single chokepoint so every file-changing path (subtitle download,
foreign-track strip, translation, cleanup rule) can tell the configured
media servers (Jellyfin/Plex/Kodi) to re-scan the affected item without
duplicating the manager plumbing + error handling.

No-op when no media server is configured; never raises.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def notify_media_servers(file_path: str, item_type: str = "") -> None:
    """Trigger a refresh of ``file_path`` on all configured media servers.

    Args:
        file_path: Path of the changed media file. The video path is
            preferred (servers index the video); a sidecar path falls back
            to a library refresh inside the adapter when no item matches.
        item_type: Optional hint ("episode" / "movie") for logging.

    Best-effort: returns silently when no servers are configured and never
    propagates exceptions — a refresh failure must never break the caller's
    happy path.
    """
    if not file_path:
        return
    try:
        from mediaserver import get_media_server_manager

        manager = get_media_server_manager()
        results = manager.refresh_all(file_path, item_type)
        for r in results:
            if r.success:
                logger.info("Media server refresh: %s", r.message)
            else:
                logger.warning("Media server refresh failed: %s", r.message)
    except Exception as exc:  # noqa: BLE001 — refresh is best-effort
        logger.warning("Media server notification failed: %s", exc)


def notify_media_servers_batch(file_paths) -> None:
    """Refresh many changed media files at once, for batch writers.

    De-duplicates the paths and hands them to the manager's
    ``refresh_all_batch``: per-item refreshes without the per-file library
    fallback, and at most one library refresh per server. Same contract as
    :func:`notify_media_servers` otherwise — no-op without servers or paths,
    never raises.
    """
    paths = [p for p in dict.fromkeys(file_paths or ()) if p]
    if not paths:
        return
    try:
        from mediaserver import get_media_server_manager

        results = get_media_server_manager().refresh_all_batch(paths)
        failed = [r.message for r in results if not r.success and not r.needs_library_refresh]
        logger.info(
            "Media server batch refresh: %d file(s), %d call(s), %d failed",
            len(paths),
            len(results),
            len(failed),
        )
        for message in failed:
            logger.warning("Media server refresh failed: %s", message)
    except Exception as exc:  # noqa: BLE001 — refresh is best-effort
        logger.warning("Media server batch notification failed: %s", exc)
