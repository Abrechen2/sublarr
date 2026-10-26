"""What a subtitle-health scan reads for one episode, resolved the same way everywhere.

The single-episode route, the series scan and the nightly sweep must open the
same files; otherwise their findings for one episode disagree and overwrite
each other. Each input is resolved here once.
"""

from __future__ import annotations


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
