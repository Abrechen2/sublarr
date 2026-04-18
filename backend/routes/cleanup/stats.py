"""Cleanup stats + history routes."""

from flask import jsonify, request

from error_utils import handle_api_error
from routes.cleanup import bp


@bp.route("/stats", methods=["GET"])
@handle_api_error("Cleanup stats failed")
def cleanup_stats():
    """Get disk space analysis and cleanup statistics.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Cleanup
      summary: Cleanup statistics
      description: Returns comprehensive disk space analysis including total files, sizes, duplicate waste, format breakdown, and cleanup trends.
      responses:
        200:
          description: Disk space analysis
          content:
            application/json:
              schema:
                type: object
                properties:
                  disk:
                    type: object
                  cleanup:
                    type: object
    """
    from db.repositories.cleanup import CleanupRepository

    repo = CleanupRepository()

    disk_stats = repo.get_disk_stats()

    # Reshape by_format from dict to array expected by the frontend DiskSpaceStats type
    raw_by_format = disk_stats.get("by_format", {})
    by_format = [
        {"format": fmt, "count": v["count"], "size_bytes": v["size"]}
        for fmt, v in raw_by_format.items()
    ]

    return jsonify(
        {
            "total_files": disk_stats.get("total_files", 0),
            "total_size_bytes": disk_stats.get("total_size_bytes", 0),
            "by_format": by_format,
            "duplicate_files": disk_stats.get("duplicate_count", 0),
            "duplicate_size_bytes": disk_stats.get("duplicate_size_bytes", 0),
            "potential_savings_bytes": disk_stats.get("potential_savings_bytes", 0),
            "trends": disk_stats.get("recent_cleanups", []),
        }
    )


@bp.route("/history", methods=["GET"])
@handle_api_error("Cleanup history failed")
def cleanup_history():
    """Get cleanup execution history.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Cleanup
      summary: Cleanup history
      description: Returns paginated cleanup execution history with operation details.
      parameters:
        - in: query
          name: page
          schema:
            type: integer
            default: 1
        - in: query
          name: per_page
          schema:
            type: integer
            default: 50
      responses:
        200:
          description: Cleanup history
          content:
            application/json:
              schema:
                type: object
                properties:
                  items:
                    type: array
                  total:
                    type: integer
                  page:
                    type: integer
                  per_page:
                    type: integer
    """
    from db.repositories.cleanup import CleanupRepository

    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 200)

    repo = CleanupRepository()
    result = repo.get_history(page, per_page)
    return jsonify(result)
