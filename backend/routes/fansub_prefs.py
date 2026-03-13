"""Fansub preference rules per series.

GET  /api/v1/series/<id>/fansub-prefs  — read prefs (defaults if unset)
PUT  /api/v1/series/<id>/fansub-prefs  — upsert prefs
DELETE /api/v1/series/<id>/fansub-prefs — clear prefs
"""

from flask import Blueprint, jsonify, request

from db.repositories.fansub_prefs import FansubPreferenceRepository

bp = Blueprint("fansub_prefs", __name__, url_prefix="/api/v1/series")

_DEFAULTS = {"preferred_groups": [], "excluded_groups": [], "bonus": 20}


@bp.route("/<int:series_id>/fansub-prefs", methods=["GET"])
def get_fansub_prefs(series_id: int):
    """Return fansub preferences for a series (defaults if not configured)."""
    prefs = FansubPreferenceRepository().get_fansub_prefs(series_id)
    if prefs is None:
        return jsonify({"series_id": series_id, **_DEFAULTS})
    return jsonify(prefs)


@bp.route("/<int:series_id>/fansub-prefs", methods=["PUT"])
def set_fansub_prefs(series_id: int):
    """Upsert fansub preferences for a series."""
    data = request.get_json(force=True, silent=True) or {}

    preferred = data.get("preferred_groups", [])
    excluded = data.get("excluded_groups", [])
    bonus = data.get("bonus", 20)

    if not isinstance(preferred, list) or not all(isinstance(g, str) for g in preferred):
        return jsonify({"error": "preferred_groups must be a list of strings"}), 400
    if not isinstance(excluded, list) or not all(isinstance(g, str) for g in excluded):
        return jsonify({"error": "excluded_groups must be a list of strings"}), 400
    if not isinstance(bonus, int):
        return jsonify({"error": "bonus must be an integer"}), 400

    FansubPreferenceRepository().set_fansub_prefs(
        series_id=series_id,
        preferred=preferred,
        excluded=excluded,
        bonus=bonus,
    )
    return jsonify(
        {
            "series_id": series_id,
            "preferred_groups": preferred,
            "excluded_groups": excluded,
            "bonus": bonus,
        }
    )


@bp.route("/<int:series_id>/fansub-prefs", methods=["DELETE"])
def delete_fansub_prefs(series_id: int):
    """Remove fansub preferences for a series (resets to defaults)."""
    FansubPreferenceRepository().delete_fansub_prefs(series_id)
    return jsonify({"series_id": series_id, "deleted": True})
