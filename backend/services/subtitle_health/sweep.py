"""Scheduled library-wide subtitle-health sweep (module-level, picklable)."""

from __future__ import annotations

import logging
import os

from services.scheduler.cancellation import abort_requested
from services.subtitle_health import store
from services.subtitle_health.apply import apply_fix
from services.subtitle_health.scan import scan_episode
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


def subtitle_health_sweep_tick() -> None:
    if not _sweep_enabled():
        return
    client = get_sonarr_client()
    if client is None:
        return
    auto = _auto_fix_enabled()
    scanned = 0
    for series in client.get_series() or []:
        if abort_requested():
            logger.info("subtitle_health sweep: stopping as asked after %d episode(s)", scanned)
            return
        sid = series.get("id")
        for ep in client.get_episodes(sid) or []:
            # One episode is the unit of work: the ffprobe and any extraction
            # inside scan_episode cannot be interrupted, so a stop takes effect
            # between episodes. This sweep is why cancellation exists — without
            # the check it ran sixteen hours past its ceiling, one stream index
            # at a time, and a container restart was the only way to end it.
            if abort_requested():
                logger.info("subtitle_health sweep: stopping as asked after %d episode(s)", scanned)
                return
            ep_id = ep.get("id")
            path = client.get_episode_file_path(ep_id) if ep_id else None
            if not path or not os.path.exists(path):
                continue
            try:
                scan_episode(episode_id=ep_id, video_path=path)
                scanned += 1
            except Exception:
                logger.exception("subtitle_health sweep: scan failed ep %s", ep_id)
                continue
            if not auto:
                continue
            for finding in store.get_findings_for_episode(ep_id):
                action = finding.get("suggested_fix")
                if action not in _AUTO_ACTIONS:
                    continue
                if finding.get("target_kind") != "sidecar":
                    continue  # auto-fix never touches embedded streams
                if not _is_stable(finding.get("target_path", "")):
                    continue
                try:
                    apply_fix(finding["id"], action)
                except Exception:
                    logger.exception("subtitle_health sweep: auto-fix failed")
