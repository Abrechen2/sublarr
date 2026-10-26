"""What a subtitle-health scan reads for one episode, resolved the same way everywhere.

The single-episode route, the series scan and the nightly sweep must open the
same files; otherwise their findings for one episode disagree and overwrite
each other. Each input is resolved here once.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def episode_sidecars(video_path: str) -> list[dict]:
    """Sidecar subtitles next to ``video_path`` in ``scan_episode``'s shape.

    A failing sidecar scan yields ``[]`` (embedded tracks are still scanned).
    """
    # Looked up at call time so tests patching routes.subtitles keep working.
    from routes.subtitles import scan_subtitle_sidecars

    try:
        return [
            {"path": sc.get("path"), "lang": sc.get("language", "und")}
            for sc in scan_subtitle_sidecars(video_path)
        ]
    except Exception:
        logger.warning("subtitle_health: sidecar scan failed for %s", video_path)
        return []


def sonarr_episode_video_path(client, ep_id: int | None) -> str | None:
    """Local video path of a Sonarr episode, with remote-path mapping applied.

    Sonarr reports its own view of the library (e.g. ``/tv/...``); the file is
    opened through ``map_path`` like ``services.episode_video_path`` does.
    """
    if not ep_id:
        return None
    raw_path = client.get_episode_file_path(ep_id)
    if not raw_path:
        return None
    from config import map_path

    return map_path(raw_path)
