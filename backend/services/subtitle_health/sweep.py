"""Scheduled library-wide subtitle-health sweep (module-level, picklable)."""

from __future__ import annotations

import logging
import os

from services.scheduler.cancellation import abort_requested
from services.subtitle_health import store
from services.subtitle_health.apply import apply_fix
from services.subtitle_health.scan import scan_episode
from services.suspect_sidecars import is_suspect_sidecar
from sonarr_client import get_sonarr_client

logger = logging.getLogger(__name__)

# Only these two are ever auto-applied (spec auto-fix policy).
_AUTO_ACTIONS = frozenset({"repair_escapes", "reencode"})


def _auto_fix_enabled() -> bool:
    from config import get_settings

    return bool(getattr(get_settings(), "subtitle_health_auto_fix", False))


def _is_stable(path: str) -> bool:
    """True if the file is old enough and not currently changing."""
    import time

    try:
        st = os.stat(path)
    except OSError:
        return False
    age = time.time() - st.st_mtime
    return age > 300  # at least 5 minutes since last write


def _sweep_enabled() -> bool:
    """Honour the feature toggle AND the sweep toggle.

    Both settings existed in config but were never read — a user who
    disabled the sweep still had sidecars rewritten nightly whenever
    auto-fix was on.
    """
    from config import get_settings

    try:
        settings = get_settings()
    except Exception:
        return False
    return bool(getattr(settings, "subtitle_health_enabled", True)) and bool(
        getattr(settings, "subtitle_health_sweep_enabled", True)
    )


def _standalone_target_allowed(target: str, video_path: str) -> bool:
    """A standalone finding's target must resolve next to its video and inside media_path."""
    from services.standalone_library import standalone_path_allowed

    return standalone_path_allowed(target, os.path.dirname(video_path))


def _sweep_episode(ep_id: int, path: str | None, auto: bool) -> bool:
    """Scan one episode and auto-fix its findings; True when it was scanned."""
    if not path or not os.path.exists(path):
        return False
    try:
        scan_episode(episode_id=ep_id, video_path=path)
    except Exception:
        logger.exception("subtitle_health sweep: scan failed ep %s", ep_id)
        return False
    if not auto:
        return True
    for finding in store.get_findings_for_episode(ep_id):
        action = finding.get("suggested_fix")
        if action not in _AUTO_ACTIONS:
            continue
        if finding.get("target_kind") != "sidecar":
            continue  # auto-fix never touches embedded streams
        if not _is_stable(finding.get("target_path", "")):
            continue
        if is_suspect_sidecar(finding.get("target_path", "")):
            # Quarantined as another episode's subtitle: a rewrite
            # would move its bytes off the flag (see suspect_sidecars).
            continue
        if (
            ep_id is not None
            and ep_id < 0
            and not _standalone_target_allowed(finding.get("target_path", ""), path)
        ):
            # A standalone sidecar that resolves out of the episode's folder
            # or the media tree (symlink) is never rewritten unattended.
            logger.warning(
                "subtitle_health sweep: auto-fix skipped for %s (outside the media folder)",
                finding.get("target_path", ""),
            )
            continue
        try:
            apply_fix(finding["id"], action)
        except Exception:
            logger.exception("subtitle_health sweep: auto-fix failed")
    return True


def _sonarr_episodes(client):
    """Yield ``(episode id, video path)`` for every Sonarr episode, lazily."""
    for series in client.get_series() or []:
        sid = series.get("id")
        for ep in client.get_episodes(sid) or []:
            ep_id = ep.get("id")
            yield ep_id, (client.get_episode_file_path(ep_id) if ep_id else None)


def _standalone_episodes():
    """Yield ``(negative episode id, video path)`` for every standalone episode.

    Standalone findings are keyed by the stable negative episode id
    (docs/specs/standalone-ids.md), so they never collide with Sonarr's.
    """
    from db.standalone import get_standalone_series
    from services.standalone_library import episode_path_in_series, series_episode_files

    try:
        all_series = get_standalone_series() or []
    except Exception:  # noqa: BLE001 — the Sonarr part of the sweep must still count
        logger.warning("subtitle_health sweep: standalone series unavailable", exc_info=True)
        return
    for series in all_series:
        for ep in series_episode_files(series["id"]) or []:
            yield ep.wire_id, episode_path_in_series(ep.file_path, series["id"])


def subtitle_health_sweep_tick() -> None:
    if not _sweep_enabled():
        return
    auto = _auto_fix_enabled()
    client = get_sonarr_client()
    sources = [_sonarr_episodes(client)] if client is not None else []
    # Standalone series are swept as well, with or without Sonarr.
    sources.append(_standalone_episodes())
    scanned = 0
    for episodes in sources:
        for ep_id, path in episodes:
            # One episode is the unit of work: the ffprobe and any extraction
            # inside scan_episode cannot be interrupted, so a stop takes effect
            # between episodes. This sweep is why cancellation exists — without
            # the check it ran sixteen hours past its ceiling, one stream index
            # at a time, and a container restart was the only way to end it.
            if abort_requested():
                logger.info("subtitle_health sweep: stopping as asked after %d episode(s)", scanned)
                return
            if _sweep_episode(ep_id, path, auto):
                scanned += 1
