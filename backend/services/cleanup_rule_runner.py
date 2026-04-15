"""Cleanup rule runner — executes and previews cleanup rules.

Encapsulates the rule-type dispatching logic that was previously inline
in routes/cleanup.py. Each rule type maps to an executor function from
cleanup_executors.py or a specialized handler.
"""

import logging

from db.repositories.cleanup import CleanupRepository

logger = logging.getLogger(__name__)


def execute_rule(rule_id: int, *, socketio=None) -> dict:
    """Execute a cleanup rule by ID and log the result.

    Returns a dict with at least {"status": ..., "rule": ...}.
    Raises ValueError for unknown rule types or missing rules.
    """
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
    from routes.remux import _trash_paths

    retention_days = int(config.get("retention_days", 7))
    return cleanup_old_backups(_trash_paths(), retention_days)


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
    else:
        return {
            "action": "rule",
            "rule": rule["name"],
            "affected_files": [],
            "total_size": 0,
            "message": f"Preview not available for rule type: {rule['rule_type']}",
        }
