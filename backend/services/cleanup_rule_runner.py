"""Cleanup rule runner — executes and previews cleanup rules.

Encapsulates the rule-type dispatching logic that was previously inline
in routes/cleanup.py. Each rule type maps to an executor function from
cleanup_executors.py or a specialized handler.
"""

import logging
import threading

from db.repositories.cleanup import CleanupRepository

logger = logging.getLogger(__name__)

# Audit C1-4: serialize rule execution. The scheduler can fire a rule at
# the same instant a user clicks "Run Now" in the UI; without this lock
# both runs walked the same file system simultaneously, both saw the
# same files, and both queued them for deletion — racy double-deletes
# and IntegrityError noise in the cleanup_history table. The lock is
# non-blocking so a second concurrent attempt fails fast with a clear
# error instead of stacking up.
_rule_runner_lock = threading.Lock()


class CleanupBusyError(RuntimeError):
    """Raised when a cleanup rule is already executing."""


def _run_foreign_track_slice(media_path: str, config: dict) -> dict:
    """Run one budgeted sweep slice. Split out so tests can substitute it.

    Acquires the sweep's own lock, not just ``_rule_runner_lock``: the
    scheduler tick does not go through the rule runner at all, so those two
    locks would not serialise a manual "Run now" against a tick already
    remuxing a file.
    """
    from config import get_settings
    from services.foreign_tracks.sweep import SweepBusyError, run_slice

    # `run_slice` takes the sweep lock itself (corrected in Task 6 — the lock
    # used to guard only the scheduler tick, leaving this path unprotected).
    # Do NOT acquire it here as well: `_sweep_lock` is a plain Lock, not an
    # RLock, and a second acquire would deadlock.
    budget = int(getattr(get_settings(), "foreign_track_sweep_budget_s", 1800))
    try:
        return run_slice(media_path, config, budget)
    except SweepBusyError as exc:
        raise CleanupBusyError(str(exc)) from exc


def execute_rule(rule_id: int, *, socketio=None) -> dict:
    """Execute a cleanup rule by ID and log the result.

    Returns a dict with at least {"status": ..., "rule": ...}.
    Raises ValueError for unknown rule types or missing rules,
    CleanupBusyError when another rule run is already in flight.
    """
    if not _rule_runner_lock.acquire(blocking=False):
        raise CleanupBusyError("Another cleanup rule is already running")
    try:
        return _execute_rule_locked(rule_id, socketio=socketio)
    finally:
        _rule_runner_lock.release()


def _execute_rule_locked(rule_id: int, *, socketio=None) -> dict:
    """Inner implementation, runs under ``_rule_runner_lock``."""
    from config import get_settings
    from dedup_engine import scan_for_duplicates, scan_orphaned_subtitles
    from services.cleanup_executors import (
        execute_format_upgrade,
        execute_language_filter,
        execute_orphan_db,
        execute_orphan_files,
    )

    repo = CleanupRepository()
    rule = repo.get_rule(rule_id)

    if rule is None:
        raise ValueError(f"Rule {rule_id} not found")

    settings = get_settings()
    media_path = settings.media_path
    rule_type = rule["rule_type"]
    config = rule.get("config_json", {})

    if rule_type == "language_filter":
        result = execute_language_filter(media_path, config, dry_run=False)
    elif rule_type == "format_upgrade":
        result = execute_format_upgrade(media_path, config, dry_run=False)
    elif rule_type == "orphan_files":
        result = execute_orphan_files(media_path, config, dry_run=False)
    elif rule_type == "orphan_db":
        result = execute_orphan_db(config, dry_run=False)
    elif rule_type == "foreign_tracks":
        # One budgeted slice, not the whole library: the sweep is resumable and
        # the next slice picks up where this one stopped. The returned counts
        # therefore describe this slice, and `pending` / `affected` tell the UI
        # how much is left so it does not read as "the rule finished".
        result = _run_foreign_track_slice(media_path, config)
        paused = result.get("paused_reason")
        stripped = result.get("stripped_files", 0)
        # A pause is not automatically a no-op: the disk-floor check sits inside
        # the strip loop, so a slice can rewrite files and only then stop. Record
        # whatever it managed; only a slice that swept nothing leaves no trace,
        # which is what keeps a no-op distinguishable from a real sweep.
        if paused and not stripped:
            logger.warning("foreign_tracks rule %s paused: %s", rule_id, paused)
            return {"status": "aborted", "result": result}
        repo.update_rule_last_run(rule_id)
        repo.log_cleanup(
            action_type=rule_type,
            rule_id=rule_id,
            files_deleted=stripped,
            bytes_freed=result.get("bytes_freed", 0),
        )
        if paused:
            logger.warning(
                "foreign_tracks rule %s paused after %d file(s): %s", rule_id, stripped, paused
            )
            return {"status": "aborted", "result": result}
        return {"status": "ok", "result": result}
    elif rule_type == "signs_cleanup":
        from services.cleanup_signs import execute_signs_cleanup

        result = execute_signs_cleanup(media_path, config, dry_run=False)
        repo.update_rule_last_run(rule_id)
        repo.log_cleanup(
            action_type=rule_type,
            rule_id=rule_id,
            files_deleted=result.get("trashed_sidecars", 0) + result.get("stripped_files", 0),
            bytes_freed=result.get("bytes_freed", 0),
        )
        return {"status": "ok", "result": result}
    elif rule_type == "dedup":
        result = scan_for_duplicates(media_path, socketio=socketio)
        repo.update_rule_last_run(rule_id)
        return {"status": "completed", "rule": rule["name"], "result": result}
    elif rule_type == "orphaned":
        result = scan_orphaned_subtitles(media_path)
        repo.update_rule_last_run(rule_id)
        return {
            "status": "completed",
            "rule": rule["name"],
            "orphaned": result,
            "count": len(result),
        }
    elif rule_type == "old_backups":
        result = _run_old_backups(rule, config)
        # cleanup_old_backups returns {"deleted": [paths], "errors": [...],
        # "skipped": int} — convert the list to a count for log_cleanup, which
        # expects an integer for the files_deleted column. cleanup_old_backups
        # does not track bytes_freed, so pass 0.
        deleted_count = len(result.get("deleted", []) or [])
        repo.update_rule_last_run(rule_id)
        repo.log_cleanup(
            action_type=rule_type,
            rule_id=rule_id,
            files_deleted=deleted_count,
            bytes_freed=0,
        )
        return {
            "status": "completed",
            "rule": rule["name"],
            "deleted": deleted_count,
            "bytes_freed": 0,
        }
    elif rule_type == "old_subtitle_baks":
        result = _run_old_subtitle_baks(rule, config)
        deleted_count = len(result.get("deleted", []) or [])
        repo.update_rule_last_run(rule_id)
        repo.log_cleanup(
            action_type=rule_type,
            rule_id=rule_id,
            files_deleted=deleted_count,
            bytes_freed=0,
        )
        return {
            "status": "completed",
            "rule": rule["name"],
            "deleted": deleted_count,
            "orphans_purged": result.get("orphans_purged", 0),
            "bytes_freed": 0,
        }
    else:
        raise ValueError(f"Unknown rule type: {rule_type}")

    repo.update_rule_last_run(rule_id)
    repo.log_cleanup(
        action_type=rule_type,
        rule_id=rule_id,
        files_deleted=result.get("deleted", 0),
        bytes_freed=result.get("bytes_freed", 0),
    )
    return {"status": "ok", "result": result}


def preview_rule(rule_id: int) -> dict:
    """Dry-run a cleanup rule and return what would be affected.

    Returns a dict with preview results. Raises ValueError for
    unknown/unsupported rule types.
    """
    from config import get_settings
    from services.cleanup_executors import (
        execute_format_upgrade,
        execute_language_filter,
        execute_orphan_db,
        execute_orphan_files,
    )

    repo = CleanupRepository()
    rule = repo.get_rule(rule_id)
    if not rule:
        raise ValueError(f"Rule {rule_id} not found")

    settings = get_settings()
    media_path = settings.media_path
    rule_type = rule["rule_type"]
    config = rule.get("config_json", {})

    if rule_type == "language_filter":
        result = execute_language_filter(media_path, config, dry_run=True)
    elif rule_type == "format_upgrade":
        result = execute_format_upgrade(media_path, config, dry_run=True)
    elif rule_type == "orphan_files":
        result = execute_orphan_files(media_path, config, dry_run=True)
    elif rule_type == "orphan_db":
        result = execute_orphan_db(config, dry_run=True)
    elif rule_type == "foreign_tracks":
        # Deliberately NOT execute_foreign_tracks(dry_run=True): that walks and
        # ffprobes the entire library inside the request — 754 s and 2,825 s on
        # the production library, so the endpoint could only ever time out. The
        # sweep's scan table already holds a verdict per file.
        result = _preview_foreign_tracks()
    elif rule_type == "signs_cleanup":
        from services.cleanup_signs import execute_signs_cleanup

        result = execute_signs_cleanup(media_path, config, dry_run=True)
    else:
        raise ValueError(f"Preview not supported for rule type: {rule_type}")

    return {"rule_id": rule_id, "rule_type": rule_type, "preview": result}


def preview_cleanup_action(action: str, params: dict) -> dict:
    """Preview a generic cleanup action (dedup, orphaned, or rule).

    Returns a dict with affected files and size estimates.
    Raises ValueError for invalid actions.
    """
    from config import get_settings

    valid_actions = {"dedup", "orphaned", "rule"}
    if action not in valid_actions:
        raise ValueError(f"action must be one of: {sorted(valid_actions)}")

    settings = get_settings()
    media_path = settings.media_path

    if action == "dedup":
        return _preview_dedup()
    elif action == "orphaned":
        return _preview_orphaned(media_path)
    elif action == "rule":
        return _preview_by_rule(params, media_path)
    else:
        raise ValueError(f"Unknown action: {action}")


def _run_old_backups(rule, config):
    """Execute old_backups cleanup."""
    from remux.backup_cleanup import cleanup_old_backups
    from services.trash_locations import remux_trash_paths

    retention_days = int(config.get("retention_days", 7))
    return cleanup_old_backups(remux_trash_paths(), retention_days)


def _run_old_subtitle_baks(rule, config):
    """Execute old_subtitle_baks cleanup.

    Walks media roots for ``<file>.<lang>.bak.<ext>`` produced by the
    subtitle processor. Always orphan-purges (regardless of age) and
    deletes non-orphans older than ``config.retention_days`` (defaults
    to ``settings.subtitle_bak_retention_days``).

    Audit C2-7: ``extra_media_paths`` is a free-form comma-separated
    string from settings; previously every entry was walked verbatim. A
    typo like ``extra_media_paths=/etc, /proc`` would steer the cleanup
    walker into privileged paths. We now skip any entry that lands on
    one of the standalone-S0-2 / G3 forbidden roots and require each
    one to actually be a directory before walking.
    """
    import os

    from config import get_settings
    from remux import _is_forbidden_trash_root
    from services.subtitle_backups import cleanup_subtitle_baks

    settings = get_settings()
    default_retention = int(getattr(settings, "subtitle_bak_retention_days", 30) or 0)
    retention_days = int(config.get("retention_days", default_retention))

    media_roots: list[str] = []
    primary = getattr(settings, "media_path", "")
    if primary and os.path.isdir(primary):
        media_roots.append(primary)
    extra = getattr(settings, "extra_media_paths", "")
    if extra:
        for raw in extra.split(","):
            cand = raw.strip()
            if not cand:
                continue
            if _is_forbidden_trash_root(cand):
                logger.warning(
                    "old_subtitle_baks: refusing extra_media_paths entry %s (forbidden root)",
                    cand,
                )
                continue
            if not os.path.isdir(cand):
                logger.warning(
                    "old_subtitle_baks: skipping extra_media_paths entry %s (not a directory)",
                    cand,
                )
                continue
            media_roots.append(cand)

    return cleanup_subtitle_baks(
        media_roots,
        older_than_days=retention_days,
        orphans_only=False,
    )


def _preview_dedup() -> dict:
    """Preview deduplication cleanup."""
    repo = CleanupRepository()
    groups = repo.get_duplicate_groups()

    affected = []
    for g in groups:
        sorted_files = sorted(g["files"], key=lambda f: f["size"], reverse=True)
        for f in sorted_files[1:]:
            affected.append(f)

    return {
        "action": "dedup",
        "affected_files": affected,
        "total_size": sum(f["size"] for f in affected),
        "groups": len(groups),
    }


def _preview_orphaned(media_path: str) -> dict:
    """Preview orphaned subtitle cleanup."""
    from dedup_engine import scan_orphaned_subtitles

    orphaned = scan_orphaned_subtitles(media_path)
    return {
        "action": "orphaned",
        "affected_files": orphaned,
        "total_size": sum(f["size"] for f in orphaned),
        "count": len(orphaned),
    }


def _preview_by_rule(params: dict, media_path: str) -> dict:
    """Preview a specific rule by ID."""
    rule_id = params.get("rule_id")
    if not rule_id:
        raise ValueError("params.rule_id is required for rule preview")

    repo = CleanupRepository()
    rule = repo.get_rule(int(rule_id))
    if rule is None:
        raise ValueError(f"Rule {rule_id} not found")

    if rule["rule_type"] == "dedup":
        result = _preview_dedup()
        result["action"] = "rule"
        result["rule"] = rule["name"]
        return result
    elif rule["rule_type"] == "orphaned":
        result = _preview_orphaned(media_path)
        result["action"] = "rule"
        result["rule"] = rule["name"]
        return result
    elif rule["rule_type"] == "foreign_tracks":
        result = _preview_foreign_tracks()
        result["action"] = "rule"
        result["rule"] = rule["name"]
        return result
    else:
        return {
            "action": "rule",
            "rule": rule["name"],
            "affected_files": [],
            "total_size": 0,
            "message": f"Preview not available for rule type: {rule['rule_type']}",
        }


def _preview_foreign_tracks() -> dict:
    """Answer from the scan table instead of walking the library.

    A synchronous scan is not an option at library scale — 754 s to enumerate
    and 2,825 s to probe on the production library. The sweep already stores
    per-file verdicts, so the preview is a set of counts.
    """
    from db.repositories.foreign_track_scan import ForeignTrackScanRepository
    from services.foreign_tracks.state import load_state

    scan = ForeignTrackScanRepository()
    counts = scan.counts_by_state()
    total = sum(counts.values())
    state = load_state()
    affected = counts.get("affected", 0)

    if not total:
        message = "No scan has run yet — counts appear after the first sweep slice."
    else:
        message = f"{affected} file(s) still carry foreign tracks."

    return {
        "affected_files": affected,
        "clean_files": counts.get("clean", 0),
        "pending_files": counts.get("pending", 0),
        "stripped_files": counts.get("stripped", 0),
        "failed_files": counts.get("failed", 0),
        # `would_strip_files` / `would_keep` / `would_strip_tracks` are the keys
        # PreviewPanel already reads for every other rule type. Emitting them
        # here means the table-backed preview renders in the existing UI without
        # a frontend change, and the *_files names above stay for API callers.
        "would_strip_files": affected,
        "would_keep": counts.get("clean", 0),
        "would_strip_tracks": scan.affected_track_total(),
        "examples": scan.sample_affected(limit=20),
        "scanned_at": state.started_at,
        "message": message,
    }
