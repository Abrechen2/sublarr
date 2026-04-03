"""Cleanup service layer — scan state, validation, and execution logic.

Extracted from routes/cleanup.py so that route handlers are thin
HTTP-adapter shims and all business logic lives here.
"""

import json
import logging
import os
import threading

logger = logging.getLogger(__name__)

# ── Lazy imports (importable at module level for monkeypatching in tests) ─────
# These are intentionally imported lazily to avoid circular imports at startup.
# The module-level names below are used as seams by unit tests.
try:
    from dedup_engine import scan_orphaned_subtitles  # noqa: F401
except ImportError:
    scan_orphaned_subtitles = None  # type: ignore[assignment]

try:
    from db.repositories.cleanup import CleanupRepository  # noqa: F401
except ImportError:
    CleanupRepository = None  # type: ignore[assignment]

# ── Deduplication scan state ──────────────────────────────────────────────────

_scan_state: dict = {
    "running": False,
    "scan_id": None,
    "progress": 0,
    "total": 0,
    "result": None,
}
_scan_lock = threading.Lock()

# ── Orphan scan state ─────────────────────────────────────────────────────────

_orphan_state: dict = {
    "running": False,
    "result": None,
}
_orphan_lock = threading.Lock()


def get_scan_state() -> dict:
    """Return a snapshot of the current dedup scan state (thread-safe)."""
    with _scan_lock:
        return {
            "running": _scan_state["running"],
            "scan_id": _scan_state["scan_id"],
            "result": _scan_state["result"],
        }


def get_orphan_state() -> dict:
    """Return a snapshot of the current orphan scan state (thread-safe)."""
    with _orphan_lock:
        return {
            "running": _orphan_state["running"],
            "result": _orphan_state["result"],
        }


def start_dedup_scan(media_path: str, socketio) -> tuple[str, bool]:
    """Start a background dedup scan.

    Returns:
        (scan_id, already_running) tuple.
        If already_running is True the caller should return 409.
    """
    import uuid

    with _scan_lock:
        if _scan_state["running"]:
            return _scan_state["scan_id"], True

        scan_id = str(uuid.uuid4())
        _scan_state["running"] = True
        _scan_state["scan_id"] = scan_id
        _scan_state["progress"] = 0
        _scan_state["total"] = 0
        _scan_state["result"] = None

    def _run_scan():
        from dedup_engine import scan_for_duplicates

        try:
            result = scan_for_duplicates(media_path, socketio=socketio)
            with _scan_lock:
                _scan_state["result"] = result
                _scan_state["running"] = False
            socketio.emit("scan_complete", result)
            logger.info("Dedup scan complete: %s", scan_id)
        except Exception as e:
            logger.error("Dedup scan failed: %s", e)
            with _scan_lock:
                _scan_state["result"] = {"error": str(e)}
                _scan_state["running"] = False
            socketio.emit("scan_error", {"error": str(e)})

    thread = threading.Thread(target=_run_scan, daemon=True)
    thread.start()
    return scan_id, False


def run_orphan_scan(media_path: str) -> tuple[list | None, str | None]:
    """Run an orphan subtitle scan synchronously.

    Returns:
        (result_list, error_message). One of them will be None.
    """
    import services.cleanup_scanner as _self

    with _orphan_lock:
        if _orphan_state["running"]:
            return None, "already_running"
        _orphan_state["running"] = True

    try:
        result = _self.scan_orphaned_subtitles(media_path)
        with _orphan_lock:
            _orphan_state["result"] = result
            _orphan_state["running"] = False
        return result, None
    except Exception as e:
        with _orphan_lock:
            _orphan_state["running"] = False
        logger.error("Orphan scan failed: %s", e)
        return None, str(e)


def validate_delete_groups(groups: list[dict]) -> str | None:
    """Validate duplicate-deletion groups.

    Returns:
        None if valid, or an error message string.
    """
    for i, group in enumerate(groups):
        keep = group.get("keep", "")
        delete_paths = group.get("delete", [])

        if not keep:
            return f"Group {i}: keep path is required"
        if not delete_paths:
            return f"Group {i}: delete list is empty"
        if keep in delete_paths:
            return f"Group {i}: keep path '{keep}' is in the delete list"

    return None


def delete_orphan_files(file_paths: list[str], media_root: str) -> dict:
    """Delete orphaned subtitle files that are inside *media_root*.

    Returns:
        dict with keys: deleted, bytes_freed, errors.
    """
    from db.repositories.cleanup import CleanupRepository

    deleted = 0
    bytes_freed = 0
    errors = []

    for fp in file_paths:
        try:
            real_fp = os.path.realpath(fp)
            if not real_fp.startswith(media_root + os.sep):
                errors.append(f"Rejected (outside media dir): {fp}")
                continue

            if not os.path.isfile(real_fp):
                errors.append(f"File not found: {fp}")
                continue

            file_size = os.path.getsize(real_fp)
            os.remove(real_fp)
            deleted += 1
            bytes_freed += file_size
            logger.info("Deleted orphaned subtitle: %s (%d bytes)", fp, file_size)
        except Exception as e:
            errors.append(f"Failed to delete {fp}: {e}")

    # Log to cleanup history
    try:
        repo = CleanupRepository()
        repo.log_cleanup(
            action_type="orphaned_delete",
            files_processed=len(file_paths),
            files_deleted=deleted,
            bytes_freed=bytes_freed,
            details_json=json.dumps({"deleted_paths": file_paths[:50]}),
        )
    except Exception as e:
        logger.warning("Failed to log orphan cleanup: %s", e)

    return {"deleted": deleted, "bytes_freed": bytes_freed, "errors": errors}


def execute_rule(rule_id: int, media_path: str, socketio) -> tuple[dict | None, str | None]:
    """Execute a cleanup rule by ID.

    Returns:
        (result_dict, error_message). One of them will be None.
    """
    from db.repositories.cleanup import CleanupRepository
    from dedup_engine import scan_for_duplicates, scan_orphaned_subtitles

    repo = CleanupRepository()
    rule = repo.get_rule(rule_id)

    if rule is None:
        return None, "not_found"

    if rule["rule_type"] == "dedup":
        result = scan_for_duplicates(media_path, socketio=socketio)
        repo.update_rule_last_run(rule_id)
        return {"status": "completed", "rule": rule["name"], "result": result}, None

    elif rule["rule_type"] == "orphaned":
        result = scan_orphaned_subtitles(media_path)
        repo.update_rule_last_run(rule_id)
        return {
            "status": "completed",
            "rule": rule["name"],
            "orphaned": result,
            "count": len(result),
        }, None

    elif rule["rule_type"] == "old_backups":
        bak_files = []
        for root, _dirs, files in os.walk(media_path):
            for filename in files:
                if ".bak" in filename:
                    full_path = os.path.join(root, filename)
                    try:
                        size = os.path.getsize(full_path)
                    except OSError:
                        size = 0
                    bak_files.append({"path": full_path, "size": size})

        repo.update_rule_last_run(rule_id)
        return {
            "status": "completed",
            "rule": rule["name"],
            "backup_files": bak_files,
            "count": len(bak_files),
            "total_size": sum(f["size"] for f in bak_files),
        }, None

    else:
        return None, f"unknown_type:{rule['rule_type']}"


def collect_cleanup_stats(media_path: str) -> dict:
    """Collect disk-space statistics for the cleanup dashboard.

    Returns:
        Flat stats dict expected by the frontend DiskSpaceStats type.
    """
    import services.cleanup_scanner as _self

    repo = _self.CleanupRepository()
    disk_stats = repo.get_disk_stats()

    # Reshape by_format from dict to array
    raw_by_format = disk_stats.get("by_format", {})
    if isinstance(raw_by_format, dict):
        by_format = [
            {"format": fmt, "count": v["count"], "size_bytes": v["size"]}
            for fmt, v in raw_by_format.items()
        ]
    else:
        by_format = raw_by_format  # already a list

    return {
        "total_files": disk_stats.get("total_files", 0),
        "total_size_bytes": disk_stats.get("total_size_bytes", 0),
        "by_format": by_format,
        "duplicate_files": disk_stats.get("duplicate_count", 0),
        "duplicate_size_bytes": disk_stats.get("duplicate_size_bytes", 0),
        "potential_savings_bytes": disk_stats.get("potential_savings_bytes", 0),
        "trends": disk_stats.get("recent_cleanups", []),
    }


def calculate_preview(action: str, params: dict, media_path: str) -> tuple[dict | None, str | None]:
    """Calculate a dry-run preview for a cleanup action.

    Returns:
        (result_dict, error_message). One of them will be None.
    """
    from db.repositories.cleanup import CleanupRepository
    from dedup_engine import scan_orphaned_subtitles

    valid_actions = {"dedup", "orphaned", "rule"}
    if action not in valid_actions:
        return None, f"action must be one of: {sorted(valid_actions)}"

    repo = CleanupRepository()

    if action == "dedup":
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
        }, None

    elif action == "orphaned":
        orphaned = scan_orphaned_subtitles(media_path)
        return {
            "action": "orphaned",
            "affected_files": orphaned,
            "total_size": sum(f["size"] for f in orphaned),
            "count": len(orphaned),
        }, None

    elif action == "rule":
        rule_id = params.get("rule_id")
        if not rule_id:
            return None, "params.rule_id is required for rule preview"

        rule = repo.get_rule(int(rule_id))
        if rule is None:
            return None, "rule_not_found"

        if rule["rule_type"] == "dedup":
            groups = repo.get_duplicate_groups()
            affected = []
            for g in groups:
                sorted_files = sorted(g["files"], key=lambda f: f["size"], reverse=True)
                for f in sorted_files[1:]:
                    affected.append(f)
            return {
                "action": "rule",
                "rule": rule["name"],
                "affected_files": affected,
                "total_size": sum(f["size"] for f in affected),
            }, None

        elif rule["rule_type"] == "orphaned":
            orphaned = scan_orphaned_subtitles(media_path)
            return {
                "action": "rule",
                "rule": rule["name"],
                "affected_files": orphaned,
                "total_size": sum(f["size"] for f in orphaned),
            }, None

        else:
            return {
                "action": "rule",
                "rule": rule["name"],
                "affected_files": [],
                "total_size": 0,
                "message": f"Preview not available for rule type: {rule['rule_type']}",
            }, None

    return None, "unexpected_action"
