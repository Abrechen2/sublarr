"""System database backup routes — /database/health, /database/backup, /database/backups, /database/restore.

/backup/full/* (ZIP archive: manifest + config + DB dump) lives in
routes/system/backup_full.py (B1Ba split).
"""

import logging
import os

from flask import jsonify, request

from routes.system import bp

logger = logging.getLogger(__name__)


@bp.route("/database/health", methods=["GET"])
def database_health():
    """Check database integrity and return stats.
    ---
    get:
      tags:
        - System
      summary: Database health check
      description: Runs SQLite integrity check and returns database statistics.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Database is healthy
          content:
            application/json:
              schema:
                type: object
                properties:
                  healthy:
                    type: boolean
                  message:
                    type: string
                  stats:
                    type: object
                    additionalProperties: true
        503:
          description: Database integrity check failed
    """
    from database_health import get_health_report, get_pool_stats

    db_report = get_health_report()
    is_ok = db_report["status"] == "healthy"
    result = {
        "healthy": is_ok,
        "backend": db_report["backend"],
        "message": db_report["status"],
        "stats": db_report.get("details", {}),
    }
    pool = get_pool_stats()
    if pool is not None:
        result["pool"] = pool

    status_code = 200 if is_ok else 503
    return jsonify(result), status_code


@bp.route("/database/backup", methods=["POST"])
def create_backup():
    """Create a manual database backup.
    ---
    post:
      tags:
        - System
      summary: Create database backup
      description: Creates a manual SQLite database backup with optional label.
      security:
        - apiKeyAuth: []
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                label:
                  type: string
                  enum: [daily, weekly, monthly]
                  default: daily
      responses:
        201:
          description: Backup created
          content:
            application/json:
              schema:
                type: object
                properties:
                  path:
                    type: string
                  size_bytes:
                    type: integer
                  label:
                    type: string
    """
    from config import get_settings
    from database_backup import DatabaseBackup

    s = get_settings()
    backup = DatabaseBackup(
        db_path=s.db_path,
        backup_dir=s.backup_dir,
        retention_daily=s.backup_retention_daily,
        retention_weekly=s.backup_retention_weekly,
        retention_monthly=s.backup_retention_monthly,
    )
    data = request.get_json() or {}
    label = data.get("label", "daily")
    if label not in ("daily", "weekly", "monthly"):
        label = "daily"

    result = backup.create_backup(label=label)
    backup.rotate()
    return jsonify(result), 201


@bp.route("/database/backups", methods=["GET"])
def list_backups():
    """List all available database backups.
    ---
    get:
      tags:
        - System
      summary: List database backups
      description: Returns a list of all available SQLite database backup files.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: List of backups
          content:
            application/json:
              schema:
                type: object
                properties:
                  backups:
                    type: array
                    items:
                      type: object
                      properties:
                        filename:
                          type: string
                        size_bytes:
                          type: integer
                        created_at:
                          type: string
    """
    from config import get_settings
    from database_backup import DatabaseBackup

    s = get_settings()
    backup = DatabaseBackup(db_path=s.db_path, backup_dir=s.backup_dir)
    return jsonify({"backups": backup.list_backups()})


@bp.route("/database/restore", methods=["POST"])
def restore_backup():
    """Restore the database from a backup file.
    ---
    post:
      tags:
        - System
      summary: Restore database from backup
      description: Restores the SQLite database from a previously created backup file. Requires explicit confirmation.
      security:
        - apiKeyAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [filename, confirm]
              properties:
                filename:
                  type: string
                  description: Backup filename to restore from
                confirm:
                  type: boolean
                  description: Must be true to proceed with restore
      responses:
        200:
          description: Database restored successfully
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  restored_from:
                    type: string
        400:
          description: Missing filename or confirmation
    """
    from config import get_settings
    from database_backup import DatabaseBackup
    from db import close_db, get_db

    data = request.get_json() or {}
    filename = data.get("filename", "")
    confirm = data.get("confirm", False)

    if not filename:
        return jsonify({"error": "filename is required"}), 400
    if not confirm:
        return jsonify({"error": "Add confirm: true to proceed"}), 400

    if "/" in filename or "\\" in filename or ".." in filename:
        return jsonify({"error": "Invalid filename"}), 400

    s = get_settings()
    backup = DatabaseBackup(db_path=s.db_path, backup_dir=s.backup_dir)
    backup_path = os.path.join(s.backup_dir, filename)
    if not os.path.abspath(backup_path).startswith(os.path.abspath(s.backup_dir) + os.sep):
        return jsonify({"error": "Invalid filename"}), 400

    # Close the current connection before restore
    close_db()

    result = backup.restore_backup(backup_path)

    # Re-open connection
    get_db()

    return jsonify(result)
