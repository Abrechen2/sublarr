"""Series-wide subtitle-health scan with SocketIO progress + aggregation.

Sonarr series are scanned through the Sonarr client (episode ids are Sonarr
episode ids). A standalone series — a negative id, or a positive id without
Sonarr (pre-1.18 form) — is scanned from its folder, each episode under its
stable negative id (docs/specs/standalone-ids.md), so findings never collide
with a Sonarr episode.
"""

from __future__ import annotations

import logging
import os

from events import emit_event
from services.subtitle_health.scan import scan_episode
from sonarr_client import get_sonarr_client

logger = logging.getLogger(__name__)


def _empty(series_id: int, error: str) -> dict:
    return {
        "series_id": series_id,
        "error": error,
        "episodes_scanned": 0,
        "total_issues": 0,
        "by_type": {},
        "affected_episodes": 0,
        "episodes": [],
    }


def _target_languages() -> list[str]:
    try:
        from config import get_settings

        primary = getattr(get_settings(), "target_language", None)
        return [primary] if primary else []
    except Exception:
        return []


def _episode_targets(series_id: int) -> list[tuple[int, str | None]] | dict:
    """``[(episode id, video path)]`` for the series, or an error summary dict."""
    # Same id rule as services.media_ids.resolve_series_ref, with this
    # module's client lookup.
    client = get_sonarr_client() if series_id > 0 else None
    if client is None:
        from services.standalone_library import episode_path_in_series, series_episode_files

        standalone_id = abs(series_id)
        files = series_episode_files(standalone_id) if standalone_id else None
        if files is None:
            return _empty(
                series_id, "Series not found" if series_id < 0 else "Sonarr not configured"
            )
        return [(ep.wire_id, episode_path_in_series(ep.file_path, standalone_id)) for ep in files]

    targets = []
    for ep in client.get_episodes(series_id) or []:
        ep_id = ep.get("id")
        targets.append((ep_id, client.get_episode_file_path(ep_id) if ep_id else None))
    return targets


def run_series_scan(series_id: int) -> dict:
    """Scan every episode of a series and return an aggregated summary."""
    targets = _episode_targets(series_id)
    if isinstance(targets, dict):
        return targets

    total = len(targets)
    by_type: dict[str, int] = {}
    episode_rows: list[dict] = []
    scanned = 0
    affected = 0
    target_languages = _target_languages()

    for idx, (ep_id, path) in enumerate(targets):
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
