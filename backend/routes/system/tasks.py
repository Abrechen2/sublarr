"""System task/notification routes — /notifications/*, /tasks/*, /openapi.json."""

import logging
from datetime import datetime

from flask import current_app, jsonify, request

from routes.system import bp

logger = logging.getLogger(__name__)


@bp.route("/notifications/test", methods=["POST"])
def notification_test():
    """Send a test notification.
    ---
    post:
      tags:
        - System
      summary: Send test notification
      description: Sends a test notification via Apprise. Optionally test a specific notification URL.
      security:
        - apiKeyAuth: []
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                url:
                  type: string
                  description: Optional specific Apprise URL to test
      responses:
        200:
          description: Notification sent successfully
          content:
            application/json:
              schema:
                type: object
                properties:
                  success:
                    type: boolean
                  message:
                    type: string
        500:
          description: Notification failed
    """
    from notifier import test_notification

    data = request.get_json() or {}
    url = data.get("url")  # Optional: test a specific URL
    result = test_notification(url=url)
    status_code = 200 if result["success"] else 500
    return jsonify(result), status_code


@bp.route("/notifications/status", methods=["GET"])
def notification_status():
    """Get notification configuration status.
    ---
    get:
      tags:
        - System
      summary: Get notification status
      description: Returns whether notifications are configured and the count of notification URLs.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Notification configuration status
          content:
            application/json:
              schema:
                type: object
                properties:
                  configured:
                    type: boolean
                  url_count:
                    type: integer
    """
    from notifier import get_notification_status

    return jsonify(get_notification_status())


@bp.route("/tasks", methods=["GET"])
def list_tasks():
    """List background scheduler tasks with status and timing info.
    ---
    get:
      tags:
        - System
      summary: List background tasks
      description: Returns all background scheduler tasks with their current status, last run time, interval, and enabled state.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: List of scheduler tasks
          content:
            application/json:
              schema:
                type: object
                properties:
                  tasks:
                    type: array
                    items:
                      type: object
                      properties:
                        name:
                          type: string
                        display_name:
                          type: string
                        running:
                          type: boolean
                        last_run:
                          type: string
                          nullable: true
                          format: date-time
                        next_run:
                          type: string
                          nullable: true
                          format: date-time
                        interval_hours:
                          type: number
                          nullable: true
                        enabled:
                          type: boolean
    """
    from config import get_settings
    from wanted_scanner import get_scanner

    s = get_settings()
    tasks = []

    try:
        scanner = get_scanner()

        # Wanted scan
        scan_interval = getattr(s, "wanted_scan_interval_hours", 6)
        scan_last = scanner.last_scan_at or None
        scan_next = None
        if scan_last and scan_interval:
            try:
                from datetime import timedelta

                last_dt = datetime.fromisoformat(str(scan_last))
                scan_next = (last_dt + timedelta(hours=scan_interval)).isoformat()
            except Exception:
                pass
        tasks.append(
            {
                "name": "wanted_scan",
                "display_name": "Wanted Scan",
                "running": scanner.is_scanning,
                "last_run": str(scan_last) if scan_last else None,
                "next_run": scan_next,
                "interval_hours": scan_interval,
                "enabled": scan_interval > 0,
            }
        )

        # Wanted search
        search_interval = getattr(s, "wanted_search_interval_hours", 24)
        search_last = scanner.last_search_at or None
        search_next = None
        if search_last and search_interval:
            try:
                from datetime import timedelta

                last_dt = datetime.fromisoformat(str(search_last))
                search_next = (last_dt + timedelta(hours=search_interval)).isoformat()
            except Exception:
                pass
        tasks.append(
            {
                "name": "wanted_search",
                "display_name": "Wanted Search",
                "running": scanner.is_searching,
                "last_run": str(search_last) if search_last else None,
                "next_run": search_next,
                "interval_hours": search_interval,
                "enabled": search_interval > 0,
            }
        )
    except Exception as exc:
        logger.warning("Failed to read scanner tasks: %s", exc)

    # Backup scheduler
    backup_enabled = bool(getattr(s, "backup_schedule_enabled", False))
    tasks.append(
        {
            "name": "backup",
            "display_name": "Database Backup",
            "running": False,
            "last_run": None,
            "next_run": None,
            "interval_hours": 24 if backup_enabled else None,
            "enabled": backup_enabled,
            "cancellable": False,
        }
    )

    # Batch Extraction
    try:
        from routes.batch_state import _batch_extract_lock, _batch_extract_state

        with _batch_extract_lock:
            ext = dict(_batch_extract_state)
        tasks.append(
            {
                "name": "batch_extraction",
                "display_name": "Batch Extraction",
                "running": ext["running"],
                "last_run": None,
                "next_run": None,
                "interval_hours": None,
                "enabled": True,
                "cancellable": False,
                "progress": (
                    {"processed": ext["processed"], "total": ext["total"]}
                    if ext["running"]
                    else None
                ),
            }
        )
    except Exception as exc:
        logger.warning("Failed to read batch extraction state: %s", exc)

    # Cleanup scheduler
    try:
        from cleanup_scheduler import get_cleanup_scheduler

        cs = get_cleanup_scheduler()
        cleanup_interval = getattr(s, "cleanup_schedule_interval_hours", 168)
        cleanup_enabled = cs is not None and cs._running
        tasks.append(
            {
                "name": "cleanup",
                "display_name": "Cleanup",
                "running": cs.is_executing if cs else False,
                "last_run": cs.last_run_at if cs else None,
                "next_run": cs.next_run_at if cs else None,
                "interval_hours": cleanup_interval if cleanup_enabled else None,
                "enabled": cleanup_enabled,
                "cancellable": False,
            }
        )
    except Exception as exc:
        logger.warning("Failed to read cleanup scheduler state: %s", exc)

    # Upgrade Scheduler
    try:
        from upgrade_scheduler import get_upgrade_scheduler

        us = get_upgrade_scheduler()
        upgrade_interval = getattr(s, "upgrade_scan_interval_hours", 0)
        upgrade_enabled = us is not None and us._running
        tasks.append(
            {
                "name": "upgrade_scan",
                "display_name": "Subtitle Upgrade Scan",
                "running": us.is_executing if us else False,
                "last_run": us.last_run_at if us else None,
                "next_run": us.next_run_at if us else None,
                "interval_hours": upgrade_interval if upgrade_enabled else None,
                "enabled": upgrade_enabled,
                "cancellable": False,
            }
        )
    except Exception as exc:
        logger.warning("Failed to read upgrade scheduler state: %s", exc)

    # AniDB Sync
    try:
        from anidb_sync import DEFAULT_INTERVAL_HOURS as ANIDB_INTERVAL
        from anidb_sync import sync_state as anidb_sync_state

        tasks.append(
            {
                "name": "anidb_sync",
                "display_name": "AniDB Sync",
                "running": anidb_sync_state["running"],
                "last_run": anidb_sync_state["last_run"],
                "next_run": None,
                "interval_hours": ANIDB_INTERVAL,
                "enabled": True,
                "cancellable": False,
            }
        )
    except Exception as exc:
        logger.warning("Failed to read AniDB sync state: %s", exc)

    # Bulk Auto-Sync (Video timing)
    tasks.append(
        {
            "name": "bulk_auto_sync",
            "display_name": "Bulk Auto-Sync",
            "running": False,
            "last_run": None,
            "next_run": None,
            "interval_hours": None,
            "enabled": True,
            "cancellable": False,
        }
    )

    # Cleanup Old Jobs
    tasks.append(
        {
            "name": "cleanup_jobs",
            "display_name": "Cleanup Old Jobs",
            "running": False,
            "last_run": None,
            "next_run": None,
            "interval_hours": None,
            "enabled": True,
            "cancellable": False,
        }
    )

    return jsonify({"tasks": tasks})


@bp.route("/tasks/<name>/cancel", methods=["POST"])
def cancel_task(name):
    """Cancel a running background task by name.
    ---
    post:
      tags:
        - System
      summary: Cancel running task
      parameters:
        - in: path
          name: name
          required: true
          schema:
            type: string
      responses:
        200:
          description: Task cancelled
        400:
          description: Task not cancellable
        404:
          description: Unknown task
        409:
          description: Task not currently running
    """
    from wanted_scanner import get_scanner

    scanner = get_scanner()
    if name == "wanted_search":
        if not scanner.is_searching:
            return jsonify({"error": "Task not running"}), 409
        scanner.cancel_search()
        return jsonify({"status": "cancelled", "task": name})
    if name == "wanted_scan":
        return jsonify({"error": "Scan cannot be cancelled mid-run"}), 400
    return jsonify({"error": f"Unknown task or not cancellable: {name}"}), 404


@bp.route("/tasks/cleanup/trigger", methods=["POST"])
def trigger_cleanup():
    """Manually trigger the cleanup task.
    ---
    post:
      tags:
        - System
      summary: Trigger cleanup
      responses:
        200:
          description: Cleanup started
        409:
          description: Cleanup already running
        503:
          description: Cleanup scheduler not initialized
    """
    import threading

    from cleanup_scheduler import get_cleanup_scheduler

    cs = get_cleanup_scheduler()
    if not cs:
        return jsonify({"error": "Cleanup scheduler not initialized"}), 503
    if cs.is_executing:
        return jsonify({"error": "Cleanup already running"}), 409
    app = current_app._get_current_object()

    def _run():
        with app.app_context():
            cs._execute_cleanup()

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "started"})


@bp.route("/tasks/upgrade-scan/trigger", methods=["POST"])
def trigger_upgrade_scan():
    """Manually trigger the subtitle upgrade scan.
    ---
    post:
      tags:
        - System
      summary: Trigger upgrade scan
      responses:
        200:
          description: Scan started
        409:
          description: Scan already running
        503:
          description: Upgrade scheduler not initialized
    """
    import threading

    from upgrade_scheduler import get_upgrade_scheduler

    us = get_upgrade_scheduler()
    if not us:
        return jsonify({"error": "Upgrade scheduler not initialized"}), 503
    if us.is_executing:
        return jsonify({"error": "Upgrade scan already running"}), 409

    def _run():
        us._execute_scan()

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "started"})


@bp.route("/tasks/cleanup-jobs", methods=["POST"])
def trigger_cleanup_jobs():
    """Delete completed/failed translation jobs older than N days.
    ---
    post:
      tags:
        - System
      summary: Cleanup old jobs
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                days:
                  type: integer
                  default: 7
      responses:
        200:
          description: Cleanup complete
    """
    from db.jobs import delete_old_jobs

    data = request.get_json(silent=True) or {}
    days = max(1, int(data.get("days", 7)))
    deleted = delete_old_jobs(days)
    return jsonify({"deleted": deleted, "older_than_days": days})


@bp.route("/openapi.json", methods=["GET"])
def openapi_spec():
    """Serve the OpenAPI 3.0.3 specification as JSON."""
    from openapi import spec

    return jsonify(spec.to_dict())
