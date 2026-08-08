"""System log routes — /logs, /logs/download, /logs/rotation.

Download + retrieval + rotation-config. The anonymised support-export
bundle lives in `routes.system.support`; DB vacuum + ffprobe cache live
in `routes.system.maintenance`.
"""

from __future__ import annotations

import logging
import os

from flask import jsonify, request, send_file

from cache_response import cached_get, invalidate_response_cache
from routes.system import bp

logger = logging.getLogger(__name__)


def _tail_log_lines(log_file: str, lines: int, level: str) -> list[str]:
    """Tail-read the log without decoding the whole file per poll.

    Reads a growing tail window (64 KB, 256 KB, 1 MB, ... up to the full file)
    until enough matching lines are collected. Fixed-size heuristics fail on
    multiline stack traces and sparse level filters; growing until satisfied is
    correct by construction — the worst case (filter matches nothing) equals
    today's full read, every other case reads a fraction of it.
    """
    chunk_size = 64 * 1024
    with open(log_file, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        while True:
            start = max(0, size - chunk_size)
            f.seek(start)
            raw = f.read(size - start)
            recent = raw.decode("utf-8", errors="replace").splitlines()
            if start > 0 and recent:
                recent = recent[1:]  # first line is likely cut mid-way

            matched = [line.strip() for line in recent if not level or f"[{level}]" in line]
            if len(matched) >= lines or start == 0:
                return matched[-lines:]
            chunk_size *= 4


@bp.route("/logs/download", methods=["GET"])
def download_logs():
    """Download the anonymised support bundle (or the raw log with ?raw=1).
    ---
    get:
      tags:
        - System
      summary: Download logs as a support bundle
      description: >
        Returns the anonymised support bundle as a ZIP — the rotated log files
        with IPs, API keys, e-mail addresses and the hostname redacted, plus a
        diagnostic report (version, platform, deployment mode, top errors).
        This is the file to attach to a bug report. Pass `raw=1` for the plain,
        unredacted log file, which was this endpoint's behaviour before 1.11.0.
      security:
        - apiKeyAuth: []
      parameters:
        - in: query
          name: raw
          schema:
            type: string
            enum: ["1", "true"]
          description: Serve the unredacted log file instead of the support bundle
      responses:
        200:
          description: Support bundle ZIP, or the raw log file when raw=1
          content:
            application/zip:
              schema:
                type: string
                format: binary
            text/plain:
              schema:
                type: string
                format: binary
        404:
          description: Log file not found (raw mode only)
    """
    # Serving the raw log by default was actively unhelpful: users attached it to
    # bug reports, which leaked host paths and addresses the export would have
    # redacted, and arrived without the version/platform/mode context needed to
    # act on it. Delegating means there is one bundle builder, so the two paths
    # cannot drift in what they redact.
    if request.args.get("raw", "").lower() not in ("1", "true"):
        from routes.system.support import support_export

        return support_export()

    from config import get_settings

    log_file = get_settings().log_file
    if not os.path.exists(log_file):
        return jsonify({"error": "Log file not found"}), 404

    return send_file(
        log_file, mimetype="text/plain", as_attachment=True, download_name="sublarr.log"
    )


@bp.route("/logs/rotation", methods=["GET"])
@cached_get(ttl_seconds=60)
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
    from app_logging import LOG_BACKUP_COUNT_DEFAULT, LOG_MAX_SIZE_MB_DEFAULT
    from db.config import get_config_entry

    max_size_mb = int(get_config_entry("log_max_size_mb") or LOG_MAX_SIZE_MB_DEFAULT)
    backup_count = int(get_config_entry("log_backup_count") or LOG_BACKUP_COUNT_DEFAULT)

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
    from app_logging import (
        LOG_BACKUP_COUNT_DEFAULT,
        LOG_BACKUP_COUNT_MAX,
        LOG_BACKUP_COUNT_MIN,
        LOG_MAX_SIZE_MB_DEFAULT,
        LOG_MAX_SIZE_MB_MAX,
        LOG_MAX_SIZE_MB_MIN,
    )
    from db.config import save_config_entry

    data = request.get_json() or {}
    max_size_mb = data.get("max_size_mb")
    backup_count = data.get("backup_count")

    errors = []
    if max_size_mb is not None:
        if (
            not isinstance(max_size_mb, (int, float))
            or max_size_mb < LOG_MAX_SIZE_MB_MIN
            or max_size_mb > LOG_MAX_SIZE_MB_MAX
        ):
            errors.append(
                f"max_size_mb must be between {LOG_MAX_SIZE_MB_MIN} and {LOG_MAX_SIZE_MB_MAX}"
            )
    if backup_count is not None:
        if (
            not isinstance(backup_count, (int, float))
            or backup_count < LOG_BACKUP_COUNT_MIN
            or backup_count > LOG_BACKUP_COUNT_MAX
        ):
            errors.append(
                f"backup_count must be between {LOG_BACKUP_COUNT_MIN} and {LOG_BACKUP_COUNT_MAX}"
            )

    if errors:
        return jsonify({"error": "; ".join(errors)}), 400

    if max_size_mb is not None:
        save_config_entry("log_max_size_mb", str(int(max_size_mb)))
    if backup_count is not None:
        save_config_entry("log_backup_count", str(int(backup_count)))

    # Read back saved values
    from db.config import get_config_entry

    saved_max = int(get_config_entry("log_max_size_mb") or LOG_MAX_SIZE_MB_DEFAULT)
    saved_count = int(get_config_entry("log_backup_count") or LOG_BACKUP_COUNT_DEFAULT)

    invalidate_response_cache()

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
            log_entries = _tail_log_lines(log_file, lines, level)
        except Exception as e:
            logger.warning("Failed to read log file: %s", e)

    return jsonify(
        {
            "entries": log_entries,
            "total": len(log_entries),
        }
    )
