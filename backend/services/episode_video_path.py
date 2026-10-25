"""Resolve an episode id to its on-disk video path — in both Sonarr and
standalone modes.

Sonarr libraries key episodes by the Sonarr episode-file id and resolve the
path through the Sonarr client (then ``map_path`` for remote-path mapping).
Standalone episodes are ``standalone_episodes`` rows; the UI/API passes their
negated id as ``ep_id`` (a positive id without Sonarr is the legacy
``wanted_items`` row id).

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

    * Negative id: a standalone episode (``-standalone_episodes.id``), with or
      without Sonarr configured — the sign keeps the two id spaces apart.
    * Positive id with Sonarr: the Sonarr episode, via the client +
      ``map_path`` (unchanged).
    * Positive id without Sonarr: the legacy standalone ``wanted_items`` row id.

    Standalone paths are only returned when they are a video file inside the
    owning series folder (``services.standalone_library``); no remote-path
    mapping applies to local standalone media.
    """
    from config import map_path
    from services.standalone_episode import resolve_standalone_episode_file

    if ep_id < 0:
        return resolve_standalone_episode_file(ep_id)

    from sonarr_client import get_sonarr_client

    client = get_sonarr_client()
    if client is not None:
        raw_path = client.get_episode_file_path(ep_id)
        if not raw_path:
            return None
        video_path = map_path(raw_path)
        return video_path if os.path.exists(video_path) else None

    try:
        return resolve_standalone_episode_file(ep_id)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("standalone episode path lookup failed for %s: %s", ep_id, exc)
        return None
