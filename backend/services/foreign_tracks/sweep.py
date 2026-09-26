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
from services.foreign_tracks.policy import (
    OverrideSet,
    is_excluded,
    override_paths,
    policy_for_path,
    policy_from_settings,
)
from services.foreign_tracks.probe import expand_keep_languages
from services.foreign_tracks.state import (
    PHASE_ENUMERATE,
    PHASE_IDLE,
    PHASE_PROBE,
    PHASE_STRIP,
    config_hash,
    load_state,
    save_state,
)
from services.scheduler.cancellation import abort_requested

logger = logging.getLogger(__name__)

# Serialises the scheduler tick against a manual "Run now". One process, one
# scheduler (gunicorn runs --workers 1), so a thread lock is the right scope.
_sweep_lock = threading.Lock()

# How long a remux temp file must be untouched before it counts as abandoned.
_TEMP_MAX_AGE_S = 86_400

# Enumeration progress cadence: whichever comes first. The walk took 754 s on
# the production library and logged nothing, so a slow share and a hung one
# looked the same from the outside.
_ENUM_PROGRESS_FILES = 5000
_ENUM_PROGRESS_S = 60.0
# Indirection so tests can drive elapsed time without patching `time` globally.
_monotonic = time.monotonic

_PROBE_BATCH = 50

# An NFS blip makes every ffprobe fail fast, and `next_pending` has no
# backoff predicate (that needs a column this task does not own) — so
# without a circuit breaker, one bad mount would park the entire backlog
# `failed` inside a single tick. A single bad file must not trip this: the
# counter resets on any success within the same slice.
_MAX_CONSECUTIVE_PROBE_FAILURES = 10


class SweepBusyError(RuntimeError):
    """Raised when a sweep slice is already running."""


def _probe_file(path: str) -> dict:
    """ffprobe one file. Split out so tests can substitute it."""
    from remux import get_media_streams

    return get_media_streams(path)


def _strip_file(
    path: str,
    keep_languages: set[str],
    keep_und: bool,
    policy=None,
    real_sidecar_langs: set[str] | None = None,
) -> tuple[str | None, int]:
    """Rewrite one file. Returns ``(backup_path, bytes_freed)``.

    ``remove_foreign_subtitle_streams`` re-probes the file itself and returns
    None when nothing foreign remains, which is what makes a retry after a
    crash-between-replace-and-commit a harmless no-op — and also what makes
    it safe to pass the per-file ``policy``/``real_sidecar_langs`` here even
    though the probe phase decided under a possibly-stale policy: strip
    re-decides from the current file contents, it never trusts the cached
    verdict.
    """
    from remux import remove_foreign_subtitle_streams

    try:
        size_before = os.path.getsize(path)
    except OSError:
        size_before = 0
    backup = remove_foreign_subtitle_streams(
        video_path=path,
        target_languages=keep_languages,
        keep_und=keep_und,
        policy=policy,
        real_sidecar_langs=real_sidecar_langs,
    )
    try:
        freed = max(0, size_before - os.path.getsize(path))
    except OSError:
        freed = 0
    return backup, freed


def _real_sidecars_for_policy(path: str, keep_languages, policy) -> set[str]:
    """Real sidecar languages for ``path``, or empty when policy B is not in play.

    ``select_tracks`` (and ``remove_foreign_subtitle_streams``) ignore
    ``real_sidecar_langs`` unless the policy is BOTH ``SIDECAR_DROP`` AND
    ``one_per_language`` — policy B only ever applies in that mode (see
    ``select_tracks``: "Policy B ... only ever applies in one_per_language").
    A lookup that hits the DB and the filesystem would be pure waste outside
    that combination.
    """
    from services.foreign_tracks.select import MODE_ONE, SIDECAR_DROP

    if policy.sidecar_policy != SIDECAR_DROP or policy.mode != MODE_ONE:
        return set()

    from config_language_data import normalize_language_code
    from services.foreign_tracks.sidecars import real_sidecar_languages

    codes = {normalize_language_code(t) for t in keep_languages} - {""}
    return real_sidecar_languages(path, codes)


def _verdicts_for(path, probe, keep_languages, keep_und, policy) -> list[dict]:
    """Per-track keep/strip verdicts for one probed file, under its
    resolved per-file policy (global or series/movie override)."""
    from remux import make_event_counter
    from services.foreign_tracks.select import select_tracks

    real = _real_sidecars_for_policy(path, keep_languages, policy)
    verdicts = select_tracks(
        probe.get("streams", []),
        policy,
        keep_languages,
        keep_und,
        real,
        count_events=make_event_counter(path),
    )
    return [v.to_dict() for v in verdicts]


def _free_bytes(root: str) -> int:
    import shutil

    try:
        return shutil.disk_usage(root).free
    except OSError:
        return 0


def _media_root_reachable(root: str) -> bool:
    """Mirror ``cleanup_executors._media_path_reachable``.

    A brief NFS hiccup makes every ffprobe/remux call fail, which looks
    indistinguishable from every file genuinely being broken. Probing the
    root once before entering the probe or strip phase converts that into a
    logged pause instead of a backlog full of false failures.
    """
    if not root:
        return False
    try:
        os.stat(root)
        return True
    except OSError:
        return False


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
    """Run one bounded slice of the sweep and return what it did.

    Raises:
        SweepBusyError: another slice is already running. `run_slice` is the
        sweep's single serialisation point — `claim_next_affected`'s safety
        depends on callers being serialised, and a concurrent call would let
        `release_stripping()` hand one caller's in-flight remux back to
        `affected` for a second caller to claim.
    """
    if not _sweep_lock.acquire(blocking=False):
        raise SweepBusyError("a sweep slice is already running")
    try:
        return _run_slice_locked(media_root, config, budget_s, now_fn, repo)
    finally:
        _sweep_lock.release()


def _run_slice_locked(media_root: str, config: dict, budget_s: int, now_fn, repo) -> dict:
    from config import get_settings
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

    # An ABSENT key inherits the global cleanup_foreign_tracks_* setting —
    # rules are created with config_json="{}", so without this the seeded
    # sweep rule would abort forever. An EXPLICITLY empty keep_languages
    # still aborts below: inheriting there would strip every subtitle track
    # in the library. Mirrors cleanup_executors.execute_foreign_tracks.
    settings = get_settings()
    raw_keep = config.get("keep_languages")
    if raw_keep is None:
        raw_keep = getattr(settings, "cleanup_foreign_tracks_keep_languages", None) or []
    keep_languages = expand_keep_languages(raw_keep)
    if not keep_languages:
        result["paused_reason"] = "empty keep_languages — refusing to sweep"
        logger.warning("foreign_track_sweep: %s", result["paused_reason"])
        return result

    raw_keep_und = config.get("keep_und")
    if raw_keep_und is None:
        raw_keep_und = getattr(settings, "cleanup_foreign_tracks_keep_und", False)
    keep_und = bool(raw_keep_und)

    # The GLOBAL policy feeds the config hash regardless of phase (see
    # below) — it is cheap (pure settings read). `override_paths()` is not:
    # it makes a live Sonarr/Radarr call per overridden series/movie, so it
    # is resolved at most once per slice, and ONLY when this slice will
    # actually reach PROBE or STRIP (never for an idle or enumerate-only
    # slice — see the phase gate further down).
    default_policy = policy_from_settings(settings)

    state = load_state()

    # Hash the RESOLVED configured codes, not the raw rule config, and not
    # the expanded tag set. A rule seeded with config_json="{}" has no
    # keep_languages of its own — the global setting is the ONLY control —
    # so hashing `config` directly would never notice an operator changing
    # it, and every cached clean/stripped verdict would survive forever.
    # Hashing the *expanded* tag set instead of the configured codes would
    # churn the hash whenever the tag-expansion table changes, for no
    # config change at all.
    hashed_config = dict(config)
    hashed_config["keep_languages"] = raw_keep
    hashed_config["keep_und"] = keep_und
    current_hash = config_hash(hashed_config, media_root, default_policy)
    if state.config_hash and state.config_hash != current_hash:
        reset = repo.reset_all_to_pending()
        logger.info("foreign_track_sweep: config changed — reset %d cached verdicts", reset)
        # A narrowed keep-list invalidates every verdict, but NOT the
        # enumeration itself — the set of files on disk didn't change. If
        # the previous walk had already completed, jump straight to
        # re-probing the existing worklist. If it was still in progress
        # (interrupted, or config changed mid-walk), resuming at PROBE would
        # silently skip every file the walk never reached and — because
        # `_strip_phase` stamps `completed_at` once the worklist drains —
        # suppress re-enumeration for `foreign_track_sweep_rescan_days`.
        state.phase = PHASE_PROBE if state.enumeration_complete else PHASE_ENUMERATE
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

    # Resolved once per slice, and only when this slice actually reaches
    # PROBE or STRIP: enumeration may chain straight into PROBE above (when
    # it completes within this call), so the phase check happens AFTER the
    # enumerate step, not before it. An idle or enumerate-only slice never
    # touches Sonarr/Radarr at all.
    resolved = OverrideSet()
    if state.phase in (PHASE_PROBE, PHASE_STRIP):
        resolved = override_paths()
    overrides = resolved.pairs
    # Folders of series/movies with the cleanup switched off (final review
    # I7): never stripped, in probe AND strip.
    excluded = resolved.excluded

    if state.phase == PHASE_PROBE:
        _probe_phase(
            media_root,
            state,
            repo,
            keep_languages,
            keep_und,
            default_policy,
            overrides,
            deadline,
            now_fn,
            result,
            excluded,
        )
        save_state(state)

    if state.phase == PHASE_STRIP:
        if not resolved.complete:
            # Sonarr/Radarr being unreachable must never make the sweep
            # strip MORE than configured: an override that can't be
            # resolved would otherwise silently fall back to the (usually
            # less restrictive) default policy for that file. Probing
            # already happened above under the same overrides — only the
            # rewrite is paused.
            state.paused_reason = (
                "series/movie override settings unavailable for "
                + ", ".join(resolved.failed)
                + " (Sonarr/Radarr unreachable?) — strip paused this slice"
            )
            logger.warning("foreign_track_sweep: %s", state.paused_reason)
        else:
            _strip_phase(
                media_root,
                config,
                state,
                repo,
                keep_languages,
                keep_und,
                default_policy,
                overrides,
                deadline,
                now_fn,
                result,
                excluded,
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
    except (ValueError, TypeError):
        return True
    return (datetime.now(UTC) - completed).total_seconds() >= days * 86_400


def _sweep_temp_files_logged(media_root: str) -> None:
    """The abandoned-temp-file cleanup, bracketed by start/end lines.

    It is a full walk of the media root of its own, run before every
    enumeration, and was the silent first half of the 754 s gap.
    """
    started = _monotonic()
    logger.info("foreign_track_sweep: temp-file cleanup started root=%s", media_root)
    removed = sweep_stale_temp_files(media_root, _TEMP_MAX_AGE_S, time.time())
    logger.info(
        "foreign_track_sweep: temp-file cleanup complete removed=%d in %.1fs",
        removed,
        _monotonic() - started,
    )


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

    try:
        _sweep_temp_files_logged(media_root)
        started = _monotonic()
        last_report = started
        files = 0
        logger.info(
            "foreign_track_sweep: enumeration started gen=%d root=%s", state.generation, media_root
        )
        for path, size, mtime in iter_video_files(
            media_root,
            config.get("include_paths") or [],
            config.get("exclude_paths") or [],
            min_age_s=min_age,
            now=time.time(),
        ):
            files += 1
            now_mono = _monotonic()
            if files % _ENUM_PROGRESS_FILES == 0 or now_mono - last_report >= _ENUM_PROGRESS_S:
                logger.info(
                    "foreign_track_sweep: enumeration progress files=%d elapsed=%.0fs",
                    files,
                    now_mono - started,
                )
                last_report = now_mono
            # The walk itself is the longest uninterruptible stretch in the
            # sweep — 754 s on the production library — so it has to be able to
            # give up mid-way. Leaving here takes the same exit as the OSError
            # path below: the pass stays incomplete and the prune is skipped,
            # because every unvisited file would otherwise look deleted.
            if abort_requested():
                logger.info("foreign_track_sweep: enumeration stopping as asked — will restart")
                state.paused_reason = "enumeration stopped on request"
                return
            repo.upsert_seen(path, size, mtime, state.generation)
    except OSError as exc:
        logger.warning("foreign_track_sweep: enumeration interrupted (%s) — will restart", exc)
        state.paused_reason = f"enumeration interrupted: {exc}"
        return

    state.enumeration_complete = True
    logger.info(
        "foreign_track_sweep: enumeration complete files=%d in %.1fs",
        files,
        _monotonic() - started,
    )
    pruned = repo.prune_stale(state.generation)
    if pruned:
        logger.info("foreign_track_sweep: %d file(s) disappeared since the last pass", pruned)
    state.phase = PHASE_PROBE


def _probe_phase(
    media_root,
    state,
    repo,
    keep_languages,
    keep_und,
    default_policy,
    overrides,
    deadline,
    now_fn,
    result,
    excluded=(),
) -> None:
    if not _media_root_reachable(media_root):
        state.paused_reason = f"media root unreachable: {media_root}"
        logger.warning("foreign_track_sweep: %s", state.paused_reason)
        return

    consecutive_failures = 0
    while now_fn() < deadline and not abort_requested():
        rows = repo.next_pending(limit=_PROBE_BATCH)
        if not rows:
            state.phase = PHASE_STRIP
            return
        for row in rows:
            # One pending row is the unit of work: ffprobe cannot be stopped
            # once started, so the slice budget and stop requests are both
            # honoured before the next file is probed.
            if now_fn() >= deadline or abort_requested():
                return
            if is_excluded(row.path, excluded):
                # The title's cleanup is switched off: nothing to decide, no
                # ffprobe needed — the file is clean for this sweep.
                repo.mark_probed_verdicts(row.path, [])
                result["probed"] += 1
                continue
            try:
                # The whole per-file decision — probe, resolve its policy,
                # compute verdicts, persist them — is one unit of work. A
                # bad file must not stall the sweep whether ffprobe, policy
                # resolution, verdict computation, or the DB write is what
                # fails; every one of them is folded into the same
                # consecutive-failure breaker as a probe failure always was.
                probe = _probe_file(row.path)
                file_policy = policy_for_path(row.path, overrides, default_policy)
                verdicts = _verdicts_for(row.path, probe, keep_languages, keep_und, file_policy)
                repo.mark_probed_verdicts(row.path, verdicts)
            except Exception as exc:  # noqa: BLE001 — one bad file must not stop the sweep
                repo.mark_failed(row.path, str(exc), ERROR_PROBE)
                consecutive_failures += 1
                if consecutive_failures >= _MAX_CONSECUTIVE_PROBE_FAILURES:
                    state.paused_reason = (
                        f"{consecutive_failures} consecutive probe failures — pausing "
                        "before more of the backlog gets parked failed"
                    )
                    logger.warning("foreign_track_sweep: %s", state.paused_reason)
                    return
                continue
            consecutive_failures = 0
            result["probed"] += 1


def _strip_phase(
    media_root,
    config,
    state,
    repo,
    keep_languages,
    keep_und,
    default_policy,
    overrides,
    deadline,
    now_fn,
    result,
    excluded=(),
) -> None:
    if not _media_root_reachable(media_root):
        # A sweep can resume directly at PHASE_STRIP on a later tick —
        # persisted state, not something this call derived — so it needs
        # the same guard as the probe phase: a mount that died between
        # ticks must pause the sweep, not park the affected backlog failed
        # at MAX_ATTEMPTS per row.
        state.paused_reason = f"media root unreachable: {media_root}"
        logger.warning("foreign_track_sweep: %s", state.paused_reason)
        return

    min_free_gb = _min_free_gb(config)

    # One affected row is the unit of work: remuxing rewrites the file and
    # cannot be interrupted safely, so budget and stop requests both take
    # effect before the next file is claimed.
    while now_fn() < deadline and not abort_requested():
        if min_free_gb and _free_bytes(media_root) < min_free_gb * 1024**3:
            state.paused_reason = (
                f"disk floor reached (min_free_gb={min_free_gb}) — paused before the next file"
            )
            logger.warning("foreign_track_sweep: %s", state.paused_reason)
            return

        row = repo.claim_next_affected()
        if row is None:
            state.phase = PHASE_IDLE
            # Only stamp completed_at for a genuinely complete pass. Doing
            # so for an interrupted enumeration would make `_rescan_due`
            # suppress re-enumeration for `foreign_track_sweep_rescan_days`,
            # silently skipping every file the walk never reached.
            if state.enumeration_complete:
                state.completed_at = _now_iso()
            return

        if is_excluded(row.path, excluded):
            # Probed affected before its series/movie was switched off: the
            # switch wins, the file is never rewritten.
            repo.mark_probed_verdicts(row.path, [])
            continue

        try:
            # Policy resolution and the sidecar lookup are folded into the
            # same try as the rewrite itself — a bad file must not stall
            # the sweep whether the failure is in resolving its policy,
            # looking up its sidecars, or the remux.
            file_policy = policy_for_path(row.path, overrides, default_policy)
            real_sidecar_langs = _real_sidecars_for_policy(row.path, keep_languages, file_policy)
            backup, freed = _strip_file(
                row.path,
                keep_languages,
                keep_und,
                policy=file_policy,
                real_sidecar_langs=real_sidecar_langs,
            )
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
    """APScheduler entry point. Module-level and closure-free so it pickles.

    Does not acquire `_sweep_lock` itself — `run_slice` is the sweep's single
    serialisation point (a plain `Lock`, not reentrant, so a second acquire
    here would deadlock a nested call and is redundant besides).
    """
    from config import get_settings
    from db.repositories.cleanup import CleanupRepository

    settings = get_settings()
    if not getattr(settings, "foreign_track_sweep_enabled", False):
        logger.info("foreign_track_sweep: skipped (foreign_track_sweep_enabled=false)")
        return

    rule = _find_rule(CleanupRepository())
    if rule is None:
        logger.info("foreign_track_sweep: skipped (no enabled foreign_tracks rule configured)")
        return

    budget = int(getattr(settings, "foreign_track_sweep_budget_s", 1800))
    try:
        result = run_slice(settings.media_path, rule.get("config_json") or {}, budget)
    except SweepBusyError:
        logger.info("foreign_track_sweep: another slice is running, skipping this tick")
        return

    logger.info(
        "foreign_track_sweep: phase=%s probed=%d stripped=%d pending=%d affected=%d "
        "paused_reason=%s",
        result["phase"],
        result["probed"],
        result["stripped_files"],
        result["pending"],
        result["affected"],
        result.get("paused_reason") or "-",
    )


def _find_rule(repo) -> dict | None:
    for rule in repo.get_rules() or []:
        if rule.get("rule_type") == "foreign_tracks" and rule.get("enabled"):
            return rule
    return None
