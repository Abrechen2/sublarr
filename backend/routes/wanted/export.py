"""Wanted list export — GET /wanted/export as CSV or JSON download."""

import csv
import io
import json
import logging
from datetime import UTC, datetime

from flask import Response, jsonify, request

from routes.wanted import bp

logger = logging.getLogger(__name__)

# Stable, documented column order for both formats.
_EXPORT_FIELDS = [
    "id",
    "item_type",
    "title",
    "season_episode",
    "target_language",
    "subtitle_type",
    "status",
    "existing_sub",
    "upgrade_candidate",
    "current_score",
    "search_count",
    "last_search_at",
    "added_at",
    "error",
    "file_path",
]

_EXPORT_ROW_CAP = 50000


def _export_row(item: dict) -> dict:
    """Project a wanted-item dict onto the stable export columns."""
    row = {}
    for field in _EXPORT_FIELDS:
        value = item.get(field)
        if isinstance(value, datetime):
            value = value.isoformat()
        row[field] = "" if value is None else value
    return row


@bp.route("/wanted/export", methods=["GET"])
def export_wanted():
    """Export the wanted list as a CSV or JSON file download.
    ---
    get:
      tags:
        - Wanted
      summary: Export wanted items
      description: Exports wanted items (optionally filtered like the list endpoint) as a downloadable CSV or JSON file.
      security:
        - apiKeyAuth: []
      parameters:
        - in: query
          name: format
          schema:
            type: string
            enum: [csv, json]
            default: csv
          description: Export file format
        - in: query
          name: item_type
          schema:
            type: string
            enum: [episode, movie]
          description: Filter by item type
        - in: query
          name: status
          schema:
            type: string
            enum: [wanted, ignored, failed, found, extracted]
          description: Filter by item status
        - in: query
          name: subtitle_type
          schema:
            type: string
            enum: [full, forced]
          description: Filter by subtitle type
        - in: query
          name: search
          schema:
            type: string
          description: Text search in title and file_path
      responses:
        200:
          description: Export file
          content:
            text/csv:
              schema:
                type: string
            application/json:
              schema:
                type: array
                items:
                  type: object
        400:
          description: Invalid format value
    """
    from db.wanted import get_wanted_items

    export_format = request.args.get("format", "csv").lower()
    if export_format not in ("csv", "json"):
        return jsonify({"error": f"Invalid format: {export_format}. Use: csv, json"}), 400

    result = get_wanted_items(
        page=1,
        per_page=_EXPORT_ROW_CAP,
        item_type=request.args.get("item_type"),
        status=request.args.get("status"),
        subtitle_type=request.args.get("subtitle_type"),
        sort_by="added_at",
        sort_dir="desc",
        search=request.args.get("search") or None,
    )
    rows = [_export_row(item) for item in result.get("data", [])]

    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    filename = f"sublarr-wanted-{stamp}.{export_format}"

    if export_format == "json":
        body = json.dumps(rows, ensure_ascii=False, indent=2)
        mimetype = "application/json"
    else:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=_EXPORT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        body = buf.getvalue()
        mimetype = "text/csv"

    logger.info("Exported %d wanted items as %s", len(rows), export_format)
    return Response(
        body,
        mimetype=mimetype,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
