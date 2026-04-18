"""Library series management routes — per-series settings + glossary suggestions."""

import logging

from flask import jsonify, request

from routes.library import bp

logger = logging.getLogger(__name__)


@bp.route("/library/series/<int:series_id>/settings", methods=["PUT"])
def update_series_settings(series_id):
    """Update per-series settings (e.g. absolute_order flag).
    ---
    put:
      tags:
        - Library
      summary: Update series settings
      description: Updates per-series configuration flags. Currently supports the absolute_order flag for AniDB absolute episode ordering.
      security:
        - apiKeyAuth: []
      parameters:
        - in: path
          name: series_id
          required: true
          schema:
            type: integer
          description: Sonarr series ID
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                absolute_order:
                  type: boolean
                  description: When true, use AniDB absolute episode numbers for provider searches
      responses:
        200:
          description: Settings updated
          content:
            application/json:
              schema:
                type: object
                properties:
                  success:
                    type: boolean
                  series_id:
                    type: integer
                  absolute_order:
                    type: boolean
        400:
          description: Invalid request body
    """
    from db.repositories.anidb import AnidbRepository

    body = request.get_json(force=True, silent=True) or {}
    if "absolute_order" not in body:
        return jsonify({"success": False, "error": "absolute_order field required"}), 400

    enabled = bool(body["absolute_order"])
    AnidbRepository().set_absolute_order(series_id, enabled)
    logger.debug("Series %d: absolute_order set to %s", series_id, enabled)
    return jsonify({"success": True, "series_id": series_id, "absolute_order": enabled})


@bp.route("/series/<int:series_id>/glossary/suggest", methods=["POST"])
def suggest_glossary_candidates(series_id):
    """Extract glossary term candidates from subtitle sidecars for a series.
    ---
    post:
      tags:
        - Library
      summary: Suggest glossary candidates
      description: >
        Scans the series subtitle sidecar files and returns frequency-based
        proper-noun candidates suitable for seeding the glossary. Does not
        write anything to the database.
      security:
        - apiKeyAuth: []
      parameters:
        - in: path
          name: series_id
          required: true
          schema:
            type: integer
          description: Sonarr series ID
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                source_lang:
                  type: string
                  default: en
                  description: Language tag used in sidecar filenames (e.g. "en")
                min_freq:
                  type: integer
                  default: 3
                  description: Minimum occurrence count to include a candidate
      responses:
        200:
          description: Candidate terms (empty list when series not found or no subs)
          content:
            application/json:
              schema:
                type: object
                properties:
                  candidates:
                    type: array
                    items:
                      type: object
                  series_id:
                    type: integer
                  message:
                    type: string
                    nullable: true
    """
    import routes.library as _lib_pkg
    from config import map_path
    from sonarr_client import get_sonarr_client

    sonarr = get_sonarr_client()
    if not sonarr:
        return jsonify(
            {"candidates": [], "series_id": series_id, "message": "Sonarr not configured"}
        )

    series = sonarr.get_series_by_id(series_id)
    if not series or not series.get("path"):
        return jsonify(
            {"candidates": [], "series_id": series_id, "message": "Series media path not found"}
        )

    body = request.get_json(silent=True) or {}
    source_lang = (body.get("source_lang") or "en").strip()
    min_freq = int(body.get("min_freq") or 3)

    media_path = map_path(series["path"])
    candidates = _lib_pkg.extract_candidates(
        media_path,
        source_lang=source_lang,
        min_freq=min_freq,
        max_candidates=100,
    )

    return jsonify({"candidates": candidates, "series_id": series_id})
