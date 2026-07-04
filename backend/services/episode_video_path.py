"""Resolve an episode id to its on-disk video path — in both Sonarr and
standalone modes.

Sonarr libraries key episodes by the Sonarr episode-file id and resolve the
path through the Sonarr client (then ``map_path`` for remote-path mapping).
Standalone libraries have no Sonarr: an "episode" is a ``wanted_items`` row
(``standalone_series_id`` set) and the row's ``id`` is what the UI/API passes
as ``ep_id`` — its ``file_path`` is the video itself.

Before this resolver, the episode combine/upload/track endpoints called
``get_sonarr_client()`` directly and returned 503 "Sonarr not configured" on a
standalone install (the movie variants already worked). This unifies both modes
behind one call so those endpoints work standalone too.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def resolve_episode_video_path(ep_id: int) -> str | None:
    """Return the on-disk video path for ``ep_id``, or ``None`` if unresolved.

    Sonarr mode: resolve via the Sonarr client + ``map_path``. Standalone mode
    (no Sonarr client): treat ``ep_id`` as a ``wanted_items`` row id and use its
    ``file_path`` directly (same as the standalone movie endpoints — no
    remote-path mapping applies to local standalone media).
    """
    from config import map_path
    from sonarr_client import get_sonarr_client

    client = get_sonarr_client()
    if client is not None:
        raw_path = client.get_episode_file_path(ep_id)
        if not raw_path:
            return None
        video_path = map_path(raw_path)
        return video_path if os.path.exists(video_path) else None

    # Standalone: ep_id is a wanted_items row id (an episode of a standalone
    # series). Its file_path is the video file.
    from sqlalchemy import text

    from extensions import db

    try:
        row = db.session.execute(
            text(
                "SELECT file_path FROM wanted_items "
                "WHERE id = :id AND standalone_series_id IS NOT NULL"
            ),
            {"id": ep_id},
        ).fetchone()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("standalone episode path lookup failed for %s: %s", ep_id, exc)
        return None

    if not row or not row[0]:
        return None
    video_path = row[0]
    return video_path if os.path.exists(video_path) else None
