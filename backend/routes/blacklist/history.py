"""Download history routes — /history, /history/stats, /history/<id>/rollback."""

import logging
import os

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


def _resolve_sidecar_path(entry: dict) -> str:
    """Derive the sidecar path a history entry produced (mapped + validated).

    History rows store the VIDEO file path; the sidecar lives at
    ``<video_base>.<lang>.<fmt>``. Raises ValueError when the derived path
    falls outside media_path.
    """
    from config import get_settings, map_path
    from security_utils import is_safe_path
    from translator import get_output_path_for_lang

    fmt = entry.get("format") or "srt"
    path = get_output_path_for_lang(map_path(entry["file_path"]), fmt, entry.get("language"))
    if not is_safe_path(path, get_settings().media_path):
        raise ValueError(f"Derived sidecar path {path!r} is outside media_path")
    return path


@bp.route("/history/<int:download_id>/rollback", methods=["POST"])
def rollback_history_entry(download_id):
    """Roll back a history entry: restore the previously replaced subtitle.
    ---
    post:
      security:
        - apiKeyAuth: []
      tags:
        - Blacklist
      summary: Roll back a subtitle download
      description: >
        Restores the subtitle version that this download replaced, using the
        single-slot .bak backup written at replacement time. Same-format
        entries swap active and backup (invoking rollback again flips them
        back). Format-upgrade entries (e.g. SRT->ASS) restore the old-format
        sidecar and retire the current one into its own backup slot.
      parameters:
        - in: path
          name: download_id
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Restored
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  path:
                    type: string
        404:
          description: Entry or backup not found
        409:
          description: Restore failed
    """
    from db.activity import log_activity
    from db.library import get_download_by_id
    from db.models.activity import EVENT_DOWNLOAD
    from services.subtitle_restore import RestoreError, backup_before_replace, restore_from_bak
    from subtitle_filename import find_existing_bak

    entry = get_download_by_id(download_id)
    if not entry:
        return jsonify({"error": "History entry not found"}), 404

    try:
        active_path = _resolve_sidecar_path(entry)
    except ValueError as e:
        return jsonify({"error": str(e)}), 403

    prev = None
    if entry.get("upgraded_from_id"):
        prev = get_download_by_id(entry["upgraded_from_id"])

    cross_format = bool(
        prev
        and (
            (prev.get("format") or "srt") != (entry.get("format") or "srt")
            or prev.get("language") != entry.get("language")
        )
    )

    if cross_format:
        # Format upgrade (e.g. SRT->ASS): the previous version lives at a
        # DIFFERENT sidecar path. Restore its bak, retire the current file.
        try:
            prev_active = _resolve_sidecar_path(prev)
        except ValueError as e:
            return jsonify({"error": str(e)}), 403

        bak_path = find_existing_bak(prev_active)
        if bak_path is None:
            return jsonify({"error": "No backup of the previous subtitle exists"}), 404

        if os.path.isfile(active_path):
            # Keep the retired file recoverable: park it in its own bak slot.
            backup_before_replace(active_path)
            try:
                os.remove(active_path)
            except OSError as e:
                return jsonify({"error": f"Could not remove current subtitle: {e}"}), 409
        try:
            os.replace(bak_path, prev_active)
        except OSError as e:
            return jsonify({"error": f"Could not restore backup: {e}"}), 409
        result = {"status": "restored", "path": prev_active, "removed": active_path}
    else:
        try:
            result = restore_from_bak(active_path)
        except RestoreError as e:
            return jsonify({"error": str(e)}), e.http_status

    log_activity(
        EVENT_DOWNLOAD,
        file_path=entry["file_path"],
        status="rollback",
        details={
            "provider": entry.get("provider_name"),
            "language": entry.get("language"),
            "restored_path": result.get("path"),
        },
    )
    logger.info("History %d rolled back: %s", download_id, result.get("path"))
    return jsonify(result), 200


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
