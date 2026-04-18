"""System maintenance routes — database vacuum + ffprobe cache.

Routes:
  /api/v1/database/vacuum        — Run VACUUM to reclaim space (SQLite only)
  /api/v1/cache/ffprobe/stats    — ffprobe cache statistics
  /api/v1/cache/ffprobe/cleanup  — Remove stale ffprobe cache entries
"""

from __future__ import annotations

from flask import jsonify, request

from routes.system import bp


@bp.route("/database/vacuum", methods=["POST"])
def vacuum_database():
    """Run VACUUM to reclaim unused space.
    ---
    post:
      tags:
        - System
      summary: Vacuum database
      description: Runs SQLite VACUUM command to reclaim unused disk space and defragment the database.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Vacuum completed
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  size_before:
                    type: integer
                  size_after:
                    type: integer
    """
    from config import get_settings
    from database_health import _is_postgresql, vacuum
    from db import get_db

    if _is_postgresql():
        return jsonify(
            {
                "error": "VACUUM is not available for PostgreSQL. Use VACUUM ANALYZE directly on the database server."
            }
        ), 501

    db = get_db()
    result = vacuum(db, get_settings().db_path)
    return jsonify(result)


@bp.route("/cache/ffprobe/stats", methods=["GET"])
def ffprobe_cache_stats():
    """Return ffprobe cache statistics.
    ---
    get:
      tags:
        - System
      summary: FFprobe cache stats
      description: Returns the number of cached ffprobe entries and timestamps.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Cache statistics
    """
    from db.cache import get_ffprobe_cache_stats

    return jsonify(get_ffprobe_cache_stats())


@bp.route("/cache/ffprobe/cleanup", methods=["POST"])
def ffprobe_cache_cleanup():
    """Remove stale ffprobe cache entries for files that no longer exist.
    ---
    post:
      tags:
        - System
      summary: Clean up stale ffprobe cache entries
      description: Deletes cache entries whose video files no longer exist on disk. Supports dry_run.
      security:
        - apiKeyAuth: []
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                dry_run:
                  type: boolean
                  default: false
      responses:
        200:
          description: Cleanup result
          content:
            application/json:
              schema:
                type: object
                properties:
                  removed:
                    type: integer
                  dry_run:
                    type: boolean
                  paths:
                    type: array
                    items:
                      type: string
    """
    from db.cache import cleanup_stale_ffprobe_cache

    data = request.get_json() or {}
    dry_run = bool(data.get("dry_run", False))
    result = cleanup_stale_ffprobe_cache(dry_run=dry_run)
    return jsonify(result)
