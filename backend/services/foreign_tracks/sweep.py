"""The batched, resumable foreign-track sweep.

One tick runs one bounded slice of work and returns. Every state transition is
committed as it happens, so an abrupt kill — the gunicorn SIGKILL that
discarded 11 minutes of work on 2026-08-04 — costs at most the file in flight.
"""

import logging
import os
import threading
import time
from datetime import UTC, datetime

from db.models.foreign_tracks import ERROR_PROBE, ERROR_REMUX, ERROR_VERIFY
from services.foreign_tracks.enumerate import iter_video_files, sweep_stale_temp_files
from services.foreign_tracks.probe import expand_keep_languages, foreign_languages
from services.foreign_tracks.state import (
    PHASE_ENUMERATE,
    PHASE_IDLE,
    PHASE_PROBE,
    PHASE_STRIP,
    config_hash,
    load_state,
    save_state,
)

logger = logging.getLogger(__name__)

# Serialises the scheduler tick against a manual "Run now". One process, one
# scheduler (gunicorn runs --workers 1), so a thread lock is the right scope.
_sweep_lock = threading.Lock()

# How long a remux temp file must be untouched before it counts as abandoned.
_TEMP_MAX_AGE_S = 86_400

_PROBE_BATCH = 50


class SweepBusyError(RuntimeError):
    """Raised when a sweep slice is already running."""


def _probe_file(path: str) -> dict:
    """ffprobe one file. Split out so tests can substitute it."""
    from remux import get_media_streams

    return get_media_streams(path)


def _strip_file(path: str, keep_languages: set[str], keep_und: bool) -> tuple[str | None, int]:
    """Rewrite one file. Returns ``(backup_path, bytes_freed)``.

    ``remove_foreign_subtitle_streams`` re-probes the file itself and returns
    None when nothing foreign remains, which is what makes a retry after a
    crash-between-replace-and-commit a harmless no-op.
    """
    from remux import remove_foreign_subtitle_streams

    try:
        size_before = os.path.getsize(path)
    except OSError:
        size_before = 0
    backup = remove_foreign_subtitle_streams(
        video_path=path, target_languages=keep_languages, keep_und=keep_und
    )
    try:
        freed = max(0, size_before - os.path.getsize(path))
    except OSError:
        freed = 0
    return backup, freed


def _free_bytes(root: str) -> int:
    import shutil

    try:
        return shutil.disk_usage(root).free
    except OSError:
        return 0


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def run_slice(
    media_root: str,
    config: dict,
    budget_s: int,
    *,
    now_fn=time.monotonic,
    repo=None,
) -> dict:
    """Run one bounded slice of the sweep and return what it did."""
    from db.repositories.foreign_track_scan import ForeignTrackScanRepository

    repo = repo or ForeignTrackScanRepository()
    deadline = now_fn() + budget_s

    result = {
        "phase": PHASE_IDLE,
        "probed": 0,
        "stripped_files": 0,
        "tracks_removed": 0,
        "bytes_freed": 0,
        "pending": 0,
        "affected": 0,
        "paused_reason": None,
    }

    keep_languages = expand_keep_languages(config.get("keep_languages") or [])
    if not keep_languages:
        # Mirrors the executor's guard: an empty keep set would strip every
        # embedded subtitle track in the library.
        result["paused_reason"] = "empty keep_languages — refusing to sweep"
        logger.warning("foreign_track_sweep: %s", result["paused_reason"])
        return result

    keep_und = bool(config.get("keep_und"))
    state = load_state()

    current_hash = config_hash(config, media_root)
    if state.config_hash and state.config_hash != current_hash:
        reset = repo.reset_all_to_pending()
        logger.info("foreign_track_sweep: config changed — reset %d cached verdicts", reset)
        state.phase = PHASE_PROBE
        state.enumeration_complete = False
    state.config_hash = current_hash
    state.paused_reason = None

    # A row left in `stripping` is work a previous slice abandoned.
    released = repo.release_stripping()
    if released:
        logger.info("foreign_track_sweep: released %d abandoned in-flight file(s)", released)

    if state.phase == PHASE_IDLE and _rescan_due(state, config):
        state.phase = PHASE_ENUMERATE

    if state.phase == PHASE_ENUMERATE:
        _enumerate(media_root, config, state, repo)
        save_state(state)

    if state.phase == PHASE_PROBE:
        _probe_phase(state, repo, keep_languages, keep_und, deadline, now_fn, result)
        save_state(state)

    if state.phase == PHASE_STRIP:
        _strip_phase(
            media_root, config, state, repo, keep_languages, keep_und, deadline, now_fn, result
        )
        save_state(state)

    counts = repo.counts_by_state()
    result["pending"] = counts.get("pending", 0)
    result["affected"] = counts.get("affected", 0)
    result["phase"] = state.phase
    result["paused_reason"] = state.paused_reason
    return result


def _rescan_due(state, config) -> bool:
    """Whether an idle sweep should start a new generation."""
    from config import get_settings

    if not state.completed_at:
        return True
    days = int(getattr(get_settings(), "foreign_track_sweep_rescan_days", 7))
    try:
        completed = datetime.fromisoformat(state.completed_at)
    except ValueError:
        return True
    return (datetime.now(UTC) - completed).total_seconds() >= days * 86_400


def _enumerate(media_root: str, config: dict, state, repo) -> None:
    """Walk once, upserting as we go.

    Stale rows are pruned ONLY after the walk finished. An interrupted walk
    leaves every unvisited file looking deleted, which would throw away its
    cached verdict — the worst failure this design has to avoid.
    """
    from config import get_settings

    settings = get_settings()
    min_age = int(getattr(settings, "foreign_track_min_file_age_s", 600))

    state.generation += 1
    state.enumeration_complete = False
    state.started_at = _now_iso()
    state.completed_at = None
    save_state(state)

    sweep_stale_temp_files(media_root, _TEMP_MAX_AGE_S, time.time())

    try:
        for path, size, mtime in iter_video_files(
            media_root,
            config.get("include_paths") or [],
            config.get("exclude_paths") or [],
            min_age_s=min_age,
            now=time.time(),
        ):
            repo.upsert_seen(path, size, mtime, state.generation)
    except OSError as exc:
        logger.warning("foreign_track_sweep: enumeration interrupted (%s) — will restart", exc)
        state.paused_reason = f"enumeration interrupted: {exc}"
        return

    state.enumeration_complete = True
    pruned = repo.prune_stale(state.generation)
    if pruned:
        logger.info("foreign_track_sweep: %d file(s) disappeared since the last pass", pruned)
    state.phase = PHASE_PROBE


def _probe_phase(state, repo, keep_languages, keep_und, deadline, now_fn, result) -> None:
    while now_fn() < deadline:
        rows = repo.next_pending(limit=_PROBE_BATCH)
        if not rows:
            state.phase = PHASE_STRIP
            return
        for row in rows:
            if now_fn() >= deadline:
                return
            try:
                probe = _probe_file(row.path)
            except Exception as exc:  # noqa: BLE001 — one bad probe must not stop the sweep
                repo.mark_failed(row.path, str(exc), ERROR_PROBE)
                continue
            repo.mark_probed(row.path, foreign_languages(probe, keep_languages, keep_und))
            result["probed"] += 1


def _strip_phase(
    media_root, config, state, repo, keep_languages, keep_und, deadline, now_fn, result
) -> None:
    min_free_gb = _min_free_gb(config)

    while now_fn() < deadline:
        if min_free_gb and _free_bytes(media_root) < min_free_gb * 1024**3:
            state.paused_reason = (
                f"disk floor reached (min_free_gb={min_free_gb}) — paused before the next file"
            )
            logger.warning("foreign_track_sweep: %s", state.paused_reason)
            return

        row = repo.claim_next_affected()
        if row is None:
            state.phase = PHASE_IDLE
            state.completed_at = _now_iso()
            return

        try:
            backup, freed = _strip_file(row.path, keep_languages, keep_und)
        except Exception as exc:  # noqa: BLE001 — record and move on
            error_class = ERROR_VERIFY if "verif" in str(exc).lower() else ERROR_REMUX
            repo.mark_failed(row.path, str(exc), error_class)
            continue

        repo.mark_stripped(row.path)
        if backup:
            result["stripped_files"] += 1
            result["tracks_removed"] += row.track_count
            result["bytes_freed"] += freed


def _min_free_gb(config: dict) -> int:
    from services.cleanup_executors import DEFAULT_SWEEP_MIN_FREE_GB

    try:
        return max(0, int(config.get("min_free_gb", DEFAULT_SWEEP_MIN_FREE_GB)))
    except (TypeError, ValueError):
        return DEFAULT_SWEEP_MIN_FREE_GB


def foreign_track_sweep_tick() -> None:
    """APScheduler entry point. Module-level and closure-free so it pickles."""
    from config import get_settings
    from db.repositories.cleanup import CleanupRepository

    settings = get_settings()
    if not getattr(settings, "foreign_track_sweep_enabled", False):
        return

    if not _sweep_lock.acquire(blocking=False):
        logger.info("foreign_track_sweep: another slice is running, skipping this tick")
        return
    try:
        rule = _find_rule(CleanupRepository())
        if rule is None:
            logger.debug("foreign_track_sweep: no foreign_tracks rule configured")
            return
        budget = int(getattr(settings, "foreign_track_sweep_budget_s", 1800))
        result = run_slice(settings.media_path, rule.get("config_json") or {}, budget)
        logger.info(
            "foreign_track_sweep: phase=%s probed=%d stripped=%d pending=%d affected=%d",
            result["phase"],
            result["probed"],
            result["stripped_files"],
            result["pending"],
            result["affected"],
        )
    finally:
        _sweep_lock.release()


def _find_rule(repo) -> dict | None:
    for rule in repo.get_rules() or []:
        if rule.get("rule_type") == "foreign_tracks" and rule.get("enabled"):
            return rule
    return None
