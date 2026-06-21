"""Series-wide subtitle-health scan with SocketIO progress + aggregation."""

from __future__ import annotations

import logging
import os

from events import emit_event
from services.subtitle_health.scan import scan_episode
from sonarr_client import get_sonarr_client

logger = logging.getLogger(__name__)


def run_series_scan(series_id: int) -> dict:
    """Scan every episode of a series and return an aggregated summary."""
    client = get_sonarr_client()
    if client is None:
        return {
            "series_id": series_id,
            "error": "Sonarr not configured",
            "episodes_scanned": 0,
            "total_issues": 0,
            "by_type": {},
            "affected_episodes": 0,
            "episodes": [],
        }

    episodes = client.get_episodes(series_id) or []
    total = len(episodes)
    by_type: dict[str, int] = {}
    episode_rows: list[dict] = []
    scanned = 0
    affected = 0

    try:
        from config import get_settings

        _primary = getattr(get_settings(), "target_language", None)
        target_languages = [_primary] if _primary else []
    except Exception:
        target_languages = []

    for idx, ep in enumerate(episodes):
        ep_id = ep.get("id")
        path = client.get_episode_file_path(ep_id) if ep_id else None
        if not path or not os.path.exists(path):
            continue
        try:
            result = scan_episode(
                episode_id=ep_id, video_path=path, target_languages=target_languages
            )
        except Exception:
            logger.exception("subtitle_health: episode scan failed for ep %s", ep_id)
            continue
        scanned += 1
        if result.issues:
            affected += 1
        for issue in result.issues:
            by_type[issue.type.value] = by_type.get(issue.type.value, 0) + 1
        episode_rows.append(result.to_dict())
        emit_event(
            "subtitle_health_progress",
            {
                "series_id": series_id,
                "done": idx + 1,
                "total": total,
                "episode_id": ep_id,
                "issue_count": len(result.issues),
            },
        )

    return {
        "series_id": series_id,
        "episodes_scanned": scanned,
        "total_issues": sum(by_type.values()),
        "by_type": by_type,
        "affected_episodes": affected,
        "episodes": episode_rows,
    }
