"""AniDB Absolute Episode Order API endpoints.

Blueprint: /api/v1/anidb-mapping

Provides:
  POST /api/v1/anidb-mapping/refresh            -- trigger full sync
  GET  /api/v1/anidb-mapping/status             -- sync state
  GET  /api/v1/anidb-mapping/series/<tvdb_id>   -- list mappings for a series
  DELETE /api/v1/anidb-mapping/series/<tvdb_id> -- clear mappings for a series

  GET  /api/v1/anidb-mapping/settings/<sonarr_id>      -- get series settings
  PUT  /api/v1/anidb-mapping/settings/<sonarr_id>      -- update absolute_order flag
"""

import logging
import threading

from flask import Blueprint, current_app, jsonify, request

bp = Blueprint("anidb_mapping", __name__, url_prefix="/api/v1/anidb-mapping")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sync endpoints
# ---------------------------------------------------------------------------

@bp.route("/refresh", methods=["POST"])
def trigger_refresh():
    """Trigger a manual AniDB absolute episode mapping sync.

    Runs asynchronously in a background thread so the request returns
    immediately. Poll GET /status to track progress.
    ---
    post:
      tags: [AniDB]
      summary: Trigger AniDB mapping sync
      responses:
        202:
          description: Sync started
        409:
          description: Sync already running
    """
    from anidb_sync import sync_state, run_sync

    if sync_state["running"]:
        return jsonify({"success": False, "error": "Sync already running"}), 409

    app = current_app._get_current_object()

    def _bg():
        run_sync(app)

    t = threading.Thread(target=_bg, daemon=True)
    t.start()

    return jsonify({"success": True, "message": "AniDB sync started"}), 202


@bp.route("/status", methods=["GET"])
def get_status():
    """Return the current AniDB sync state.
    ---
    get:
      tags: [AniDB]
      summary: AniDB sync status
      responses:
        200:
          description: Sync state
    """
    from anidb_sync import sync_state
    from db.repositories.anidb import AnidbRepository

    try:
        total = AnidbRepository().count_mappings()
    except Exception:
        total = None

    return jsonify({
        "success": True,
        "data": {
            **sync_state,
            "total_mappings": total,
        },
    })


# ---------------------------------------------------------------------------
# Series mapping endpoints
# ---------------------------------------------------------------------------

@bp.route("/series/<int:tvdb_id>", methods=["GET"])
def get_series_mappings(tvdb_id: int):
    """Return all absolute episode mappings for a TVDB series.
    ---
    get:
      tags: [AniDB]
      parameters:
        - name: tvdb_id
          in: path
          required: true
          schema:
            type: integer
      responses:
        200:
          description: List of mappings
    """
    from db.repositories.anidb import AnidbRepository

    mappings = AnidbRepository().list_by_tvdb(tvdb_id)
    return jsonify({"success": True, "data": mappings, "total": len(mappings)})


@bp.route("/series/<int:tvdb_id>", methods=["DELETE"])
def clear_series_mappings(tvdb_id: int):
    """Delete all absolute episode mappings for a TVDB series.
    ---
    delete:
      tags: [AniDB]
      parameters:
        - name: tvdb_id
          in: path
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Mappings deleted
    """
    from db.repositories.anidb import AnidbRepository

    deleted = AnidbRepository().clear_for_tvdb(tvdb_id)
    return jsonify({"success": True, "deleted": deleted})


# ---------------------------------------------------------------------------
# Series settings (absolute_order flag)
# ---------------------------------------------------------------------------

@bp.route("/settings/<int:sonarr_series_id>", methods=["GET"])
def get_series_settings(sonarr_series_id: int):
    """Return series-level settings including absolute_order flag.
    ---
    get:
      tags: [AniDB]
      parameters:
        - name: sonarr_series_id
          in: path
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Series settings
    """
    from db.repositories.anidb import AnidbRepository

    settings = AnidbRepository().get_series_settings(sonarr_series_id)
    if settings is None:
        settings = {"sonarr_series_id": sonarr_series_id, "absolute_order": False}
    else:
        settings["absolute_order"] = bool(settings.get("absolute_order"))
    return jsonify({"success": True, "data": settings})


@bp.route("/settings/<int:sonarr_series_id>", methods=["PUT"])
def update_series_settings(sonarr_series_id: int):
    """Update series-level settings.

    Accepted body (JSON):
      { "absolute_order": true | false }
    ---
    put:
      tags: [AniDB]
      parameters:
        - name: sonarr_series_id
          in: path
          required: true
          schema:
            type: integer
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                absolute_order:
                  type: boolean
      responses:
        200:
          description: Settings updated
        400:
          description: Invalid body
    """
    from db.repositories.anidb import AnidbRepository

    body = request.get_json(force=True, silent=True) or {}
    if "absolute_order" not in body:
        return jsonify({"success": False, "error": "absolute_order field required"}), 400

    enabled = bool(body["absolute_order"])
    AnidbRepository().set_absolute_order(sonarr_series_id, enabled)
    return jsonify({"success": True, "sonarr_series_id": sonarr_series_id,
                    "absolute_order": enabled})
