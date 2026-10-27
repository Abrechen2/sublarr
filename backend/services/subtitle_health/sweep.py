"""Scheduled library-wide subtitle-health sweep (module-level, picklable)."""

from __future__ import annotations

import functools
import logging
import os
import time

from services.scheduler.cancellation import abort_requested
from services.subtitle_health import store
from services.subtitle_health.apply import apply_fix
from services.subtitle_health.episode_inputs import episode_sidecars, sonarr_episode_video_path
from services.subtitle_health.scan import scan_episode
from services.subtitle_health.sweep_cursor import (
    CURSOR_KEY,
    SOURCE_SONARR,
    SOURCE_STANDALONE,
    Cursor,
    load_cursor,
    save_cursor,
)
from services.suspect_sidecars import is_suspect_sidecar
from sonarr_client import get_sonarr_client

logger = logging.getLogger(__name__)

__all__ = [
    "CURSOR_KEY",
    "SOURCE_SONARR",
    "SOURCE_STANDALONE",
    "SWEEP_BUDGET_S",
    "SWEEP_TIMEOUT_S",
    "load_cursor",
    "save_cursor",
    "subtitle_health_sweep_tick",
]

# The scheduler's ceiling for the job (its JobSpec uses this constant). The
# sweep stops itself earlier, so a normal night ends with a saved resume point
# at INFO instead of a timeout ERROR. The reserve covers one slow episode: an
# embedded-track extraction may take up to 300 s, and an episode can have
# several.
SWEEP_TIMEOUT_S = 3600
SWEEP_BUDGET_S = SWEEP_TIMEOUT_S - 15 * 60

# Save the resume point every this many episodes as well, so a crash or
# container restart mid-run does not throw the night's progress away.
_CURSOR_SAVE_EVERY = 20

_clock = time.monotonic

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
        scan_episode(episode_id=ep_id, video_path=path, sidecars=episode_sidecars(path))
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


def _int_ids(rows) -> list[int]:
    """The integer ``id`` of every row, sorted — the walk order of the sweep."""
    return sorted({r.get("id") for r in rows or [] if isinstance(r.get("id"), int)})


class _SonarrUnavailableError(Exception):
    """Sonarr stopped answering during the walk."""


def _sonarr_episodes(client, series_ids: list[int], after: Cursor | None = None):
    """Yield ``(cursor key, path getter)`` for every Sonarr episode after ``after``.

    Series and episodes are walked by id. Series before the cursor's series are
    skipped without fetching their episodes, and the video path is only looked
    up for an episode that is actually swept. Raises ``_SonarrUnavailableError``
    when an episode list cannot be fetched, so that series is not skipped.
    """
    if after is not None and after[0] > SOURCE_SONARR:
        return
    after_series = after[1] if after is not None else None
    for sid in series_ids:
        if after_series is not None and sid < after_series:
            continue
        episodes = client.list_episodes(sid)
        if episodes is None:
            raise _SonarrUnavailableError(sid)
        for ep_id in _int_ids(episodes):
            key = (SOURCE_SONARR, sid, ep_id)
            if after is not None and key <= after:
                continue
            yield key, functools.partial(sonarr_episode_video_path, client, ep_id)


def _standalone_episodes(after: Cursor | None = None):
    """Yield ``(cursor key, path getter)`` for every standalone episode after ``after``.

    Standalone findings are keyed by the stable negative episode id
    (docs/specs/standalone-ids.md), so they never collide with Sonarr's.
    """
    from db.standalone import get_standalone_series
    from services.standalone_library import episode_path_in_series, series_episode_files

    try:
        series_ids = _int_ids(get_standalone_series())
    except Exception:  # noqa: BLE001 — the Sonarr part of the sweep must still count
        logger.warning("subtitle_health sweep: standalone series unavailable", exc_info=True)
        return
    after_series = after[1] if after is not None and after[0] == SOURCE_STANDALONE else None
    for sid in series_ids:
        if after_series is not None and sid < after_series:
            continue
        files = sorted(series_episode_files(sid) or [], key=lambda f: f.wire_id)
        for ep in files:
            key = (SOURCE_STANDALONE, sid, ep.wire_id)
            if after is not None and key <= after:
                continue
            yield key, functools.partial(episode_path_in_series, ep.file_path, sid)


def _library(client, series_ids: list[int], after: Cursor | None):
    """Every sweepable episode after ``after``, in cursor order."""
    if client is not None:
        yield from _sonarr_episodes(client, series_ids, after)
    # Standalone series are swept as well, with or without Sonarr.
    yield from _standalone_episodes(after)


class _SweepRun:
    """One night's walk: tracks the resume point and the time budget."""

    def __init__(self, auto: bool, deadline: float):
        self.auto = auto
        self.deadline = deadline
        self.scanned = 0
        self.visited = 0
        self.cursor: Cursor | None = None

    def walk(self, items, upto: Cursor | None = None) -> bool:
        """Sweep ``items`` (up to and including ``upto``); True when it had to stop."""
        for key, path_of in items:
            if upto is not None and key > upto:
                return False
            # One episode is the unit of work: the ffprobe and any extraction
            # inside scan_episode cannot be interrupted, so a stop takes effect
            # between episodes. This sweep is why cancellation exists — without
            # the check it ran sixteen hours past its ceiling, one stream index
            # at a time, and a container restart was the only way to end it.
            if abort_requested():
                save_cursor(self.cursor)
                logger.info(
                    "subtitle_health sweep: stopping as asked after %d episode(s), resumes after %s",
                    self.scanned,
                    self.cursor,
                )
                return True
            if _clock() >= self.deadline:
                # Stop before the scheduler's timeout does: a normal night ends
                # here, at INFO, with the resume point saved.
                save_cursor(self.cursor)
                logger.info(
                    "subtitle_health sweep: sweep paused after %d episode(s) (time budget %ds), "
                    "resumes after %s",
                    self.scanned,
                    SWEEP_BUDGET_S,
                    self.cursor,
                )
                return True
            if _sweep_episode(key[2], path_of(), self.auto):
                self.scanned += 1
            self.cursor = key
            self.visited += 1
            if self.visited % _CURSOR_SAVE_EVERY == 0:
                save_cursor(key)  # a crash or restart loses at most a few episodes
        return False


def _log_full_pass(run: _SweepRun) -> None:
    logger.info(
        "subtitle_health sweep: sweep completed a full pass (%d episode(s) scanned this run)",
        run.scanned,
    )


def subtitle_health_sweep_tick() -> None:
    if not _sweep_enabled():
        return
    run = _SweepRun(_auto_fix_enabled(), _clock() + SWEEP_BUDGET_S)
    client = get_sonarr_client()
    series_ids: list[int] = []
    if client is not None:
        series = client.list_series()
        if series is None:
            # Walking on would look like a finished Sonarr pass and move the
            # resume point past every series.
            logger.info("subtitle_health sweep: Sonarr unreachable, skipped; resume point kept")
            return
        series_ids = _int_ids(series)
    start = load_cursor()
    # A stop before the first episode keeps the old resume point.
    run.cursor = start
    try:
        if run.walk(_library(client, series_ids, start)):
            return
        if start is None:
            if run.visited:
                _log_full_pass(run)
            save_cursor(None)
            return
        # Wrap around: from the top up to where this run began.
        run.cursor = None
        stopped = run.walk(_library(client, series_ids, None), upto=start)
        if run.visited == 0:
            # Nothing to sweep at all (no Sonarr series, no standalone
            # episodes): keep the resume point for when there is again.
            logger.info("subtitle_health sweep: no episodes listed, resume point kept")
            return
        _log_full_pass(run)
        if not stopped:
            save_cursor(run.cursor)
    except _SonarrUnavailableError as exc:
        # Keep what was finished; the series that failed is swept next time.
        if run.cursor is not None:
            save_cursor(run.cursor)
        logger.info(
            "subtitle_health sweep: Sonarr stopped answering at series %s, resumes after %s",
            exc,
            run.cursor if run.cursor is not None else start,
        )
    except BaseException:
        if run.cursor is not None:
            save_cursor(run.cursor)
        raise
