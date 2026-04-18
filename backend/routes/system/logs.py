"""System log routes — /logs, /logs/download, /logs/rotation.

Download + retrieval + rotation-config. The anonymised support-export
bundle lives in `routes.system.support`; DB vacuum + ffprobe cache live
in `routes.system.maintenance`.
"""

from __future__ import annotations

import logging
import os

from flask import jsonify, request, send_file

from routes.system import bp

logger = logging.getLogger(__name__)


@bp.route("/logs/download", methods=["GET"])
def download_logs():
    """Download the log file as an attachment.
    ---
    get:
      tags:
        - System
      summary: Download log file
      description: Downloads the Sublarr log file as a text attachment.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Log file download
          content:
            text/plain:
              schema:
                type: string
                format: binary
        404:
          description: Log file not found
    """
    from config import get_settings

    log_file = get_settings().log_file
    if not os.path.exists(log_file):
        return jsonify({"error": "Log file not found"}), 404

    return send_file(
        log_file, mimetype="text/plain", as_attachment=True, download_name="sublarr.log"
    )


@bp.route("/logs/rotation", methods=["GET"])
def get_log_rotation():
    """Get current log rotation configuration.
    ---
    get:
      tags:
        - System
      summary: Get log rotation config
      description: Returns current log rotation settings (max size and backup count).
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Log rotation configuration
          content:
            application/json:
              schema:
                type: object
                properties:
                  max_size_mb:
                    type: integer
                  backup_count:
                    type: integer
    """
    from db.config import get_config_entry

    max_size_mb = int(get_config_entry("log_max_size_mb") or "10")
    backup_count = int(get_config_entry("log_backup_count") or "5")

    return jsonify(
        {
            "max_size_mb": max_size_mb,
            "backup_count": backup_count,
        }
    )


@bp.route("/logs/rotation", methods=["PUT"])
def update_log_rotation():
    """Update log rotation configuration.
    ---
    put:
      tags:
        - System
      summary: Update log rotation config
      description: Updates log rotation settings. Changes take effect on next application restart.
      security:
        - apiKeyAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                max_size_mb:
                  type: integer
                  minimum: 1
                  maximum: 100
                  description: Maximum log file size in MB
                backup_count:
                  type: integer
                  minimum: 1
                  maximum: 20
                  description: Number of rotated log files to keep
      responses:
        200:
          description: Configuration updated
        400:
          description: Invalid parameter values
    """
    from db.config import save_config_entry

    data = request.get_json() or {}
    max_size_mb = data.get("max_size_mb")
    backup_count = data.get("backup_count")

    errors = []
    if max_size_mb is not None:
        if not isinstance(max_size_mb, (int, float)) or max_size_mb < 1 or max_size_mb > 100:
            errors.append("max_size_mb must be between 1 and 100")
    if backup_count is not None:
        if not isinstance(backup_count, (int, float)) or backup_count < 1 or backup_count > 20:
            errors.append("backup_count must be between 1 and 20")

    if errors:
        return jsonify({"error": "; ".join(errors)}), 400

    if max_size_mb is not None:
        save_config_entry("log_max_size_mb", str(int(max_size_mb)))
    if backup_count is not None:
        save_config_entry("log_backup_count", str(int(backup_count)))

    # Read back saved values
    from db.config import get_config_entry

    saved_max = int(get_config_entry("log_max_size_mb") or "10")
    saved_count = int(get_config_entry("log_backup_count") or "5")

    logger.info(
        "Log rotation config updated: max_size_mb=%d, backup_count=%d", saved_max, saved_count
    )

    return jsonify(
        {
            "status": "updated",
            "max_size_mb": saved_max,
            "backup_count": saved_count,
            "note": "Changes take effect on next application restart",
        }
    )


@bp.route("/logs", methods=["GET"])
def get_logs():
    """Get recent log entries.
    ---
    get:
      tags:
        - System
      summary: Get recent logs
      description: Returns recent log entries with optional line count and level filter.
      security:
        - apiKeyAuth: []
      parameters:
        - in: query
          name: lines
          schema:
            type: integer
            default: 200
          description: Number of recent log lines to return
        - in: query
          name: level
          schema:
            type: string
            enum: [DEBUG, INFO, WARNING, ERROR, CRITICAL]
          description: Filter by log level
      responses:
        200:
          description: Log entries
          content:
            application/json:
              schema:
                type: object
                properties:
                  entries:
                    type: array
                    items:
                      type: string
                  total:
                    type: integer
    """
    import collections

    from config import get_settings

    settings = get_settings()
    log_file = settings.log_file
    lines = request.args.get("lines", 200, type=int)
    level = request.args.get("level", "").upper()

    if not lines or lines <= 0:
        lines = 200
    lines = min(lines, 2000)
    log_entries = []
    if os.path.exists(log_file):
        try:
            with open(log_file, encoding="utf-8", errors="replace") as f:
                recent = list(collections.deque(f, maxlen=lines))
                for line in recent:
                    if level and f"[{level}]" not in line:
                        continue
                    log_entries.append(line.strip())
        except Exception as e:
            logger.warning("Failed to read log file: %s", e)

    return jsonify(
        {
            "entries": log_entries,
            "total": len(log_entries),
        }
    )
