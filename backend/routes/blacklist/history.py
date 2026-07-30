"""Download history routes — /history, /history/stats."""

import logging

from flask import jsonify, request

from routes.blacklist import bp

logger = logging.getLogger(__name__)


@bp.route("/history", methods=["GET"])
def list_history():
    """Get paginated download history.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Blacklist
      summary: List download history
      description: Returns paginated subtitle download history with optional provider and language filters.
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
            maximum: 200
        - in: query
          name: provider
          schema:
            type: string
          description: Filter by provider name
        - in: query
          name: language
          schema:
            type: string
          description: Filter by language code
        - in: query
          name: format
          schema:
            type: string
            enum: [ass, srt]
          description: Filter by subtitle format
        - in: query
          name: score_min
          schema:
            type: integer
          description: Minimum score filter
        - in: query
          name: score_max
          schema:
            type: integer
          description: Maximum score filter
        - in: query
          name: search
          schema:
            type: string
          description: Text search in file_path and provider_name
        - in: query
          name: sort_by
          schema:
            type: string
            default: downloaded_at
            enum: [downloaded_at, score, provider_name, language]
          description: Sort field
        - in: query
          name: sort_dir
          schema:
            type: string
            default: desc
            enum: [asc, desc]
          description: Sort direction
      responses:
        200:
          description: Paginated history
          content:
            application/json:
              schema:
                type: object
                properties:
                  data:
                    type: array
                    items:
                      type: object
                  page:
                    type: integer
                  per_page:
                    type: integer
                  total:
                    type: integer
                  total_pages:
                    type: integer
    """
    from db.library import get_download_history

    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 200)
    provider = request.args.get("provider")
    language = request.args.get("language")
    format_filter = request.args.get("format") or None
    score_min = request.args.get("score_min", type=int)
    score_max = request.args.get("score_max", type=int)
    search = request.args.get("search") or None
    sort_by = request.args.get("sort_by", "downloaded_at")
    sort_dir = request.args.get("sort_dir", "desc")

    result = get_download_history(
        page=page,
        per_page=per_page,
        provider=provider,
        language=language,
        format=format_filter,
        score_min=score_min,
        score_max=score_max,
        search=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    return jsonify(result)


@bp.route("/history/<int:download_id>/decision", methods=["GET"])
def get_history_decision(download_id: int):
    """Get the selection decision log for a download.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Blacklist
      summary: Get download decision log
      description: >
        Returns the recorded selection pipeline for a downloaded subtitle:
        which providers were searched (hits, latency, skip reasons), which
        candidates each filter stage rejected, the upgrade decision, download
        attempts, and the final selection with its score breakdown.
      parameters:
        - in: path
          name: download_id
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Decision log payload
          content:
            application/json:
              schema:
                type: object
        404:
          description: No decision log recorded for this download
    """
    import json

    from db.providers import get_download_decision_log

    raw = get_download_decision_log(download_id)
    if not raw:
        return jsonify({"error": "No decision log recorded for this download"}), 404
    try:
        return jsonify(json.loads(raw))
    except ValueError:
        logger.warning("Corrupt decision log JSON for download %d", download_id)
        return jsonify({"error": "Decision log is corrupt"}), 500


@bp.route("/history/stats", methods=["GET"])
def history_stats():
    """Get aggregated download statistics.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Blacklist
      summary: Get download statistics
      description: Returns aggregated download statistics including totals by provider, format, and language.
      responses:
        200:
          description: Download statistics
          content:
            application/json:
              schema:
                type: object
                properties:
                  total_downloads:
                    type: integer
                  by_provider:
                    type: object
                    additionalProperties:
                      type: integer
                  by_format:
                    type: object
                    additionalProperties:
                      type: integer
                  by_language:
                    type: object
                    additionalProperties:
                      type: integer
    """
    from db.library import get_download_stats

    return jsonify(get_download_stats())
