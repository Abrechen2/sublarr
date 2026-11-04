"""GET/PATCH /api/v1/series/<id>/settings — priority_override + min_attempts_per_day (Phase 4a)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from flask import Blueprint, jsonify, request

from db.models.core import SeriesSettings
from extensions import db
from services.media_ids import owner_key_url_values

logger = logging.getLogger(__name__)

bp = Blueprint("series_settings_overrides", __name__, url_prefix="/api/v1/series")

# Standalone titles are stored under their owner key (negated id), see
# docs/specs/standalone-ids.md; the view functions receive that key.
bp.url_value_preprocessor(owner_key_url_values)


_ALLOWED_PRIORITY = {"premium", "standard", "backlog"}
_ALLOWED_FORMAT_REQUIREMENTS = {"require_ass"}
_MIN_ATTEMPTS_MIN = 0
_MIN_ATTEMPTS_MAX = 50


def _payload(row) -> dict:
    return {
        "sonarr_series_id": getattr(row, "sonarr_series_id", None),
        "priority_override": getattr(row, "priority_override", None),
        "min_attempts_per_day": getattr(row, "min_attempts_per_day", None) or 0,
        "cleanup_foreign_tracks": getattr(row, "cleanup_foreign_tracks", None),
        "subtitle_format_requirement": getattr(row, "subtitle_format_requirement", None),
    }


@bp.route("/<int(signed=True):series_id>/settings", methods=["GET"])
def get_series_settings(series_id: int):
    """The series' saved overrides; the defaults (all inherited) when none are.

    The series page showed "inherit" and 0 whatever was saved, so saving one
    field silently reset the other two.
    """
    from services.standalone_owner_keys import get_row

    row = get_row(SeriesSettings, series_id)
    payload = _payload(row)
    payload["sonarr_series_id"] = series_id
    return jsonify(payload), 200


@bp.route("/<int(signed=True):series_id>/settings", methods=["PATCH"])
def patch_series_settings(series_id: int):
    data = request.get_json(silent=True) or {}

    # Validate priority_override
    if "priority_override" in data:
        pv = data["priority_override"]
        if pv is not None and pv not in _ALLOWED_PRIORITY:
            return jsonify(
                {"error": (f"priority_override must be one of {sorted(_ALLOWED_PRIORITY)} or null")}
            ), 400

    # Validate min_attempts_per_day
    if "min_attempts_per_day" in data:
        try:
            mv = int(data["min_attempts_per_day"])
        except (TypeError, ValueError):
            return jsonify({"error": "min_attempts_per_day must be an integer"}), 400
        if mv < _MIN_ATTEMPTS_MIN or mv > _MIN_ATTEMPTS_MAX:
            return jsonify(
                {
                    "error": (
                        f"min_attempts_per_day must be in "
                        f"[{_MIN_ATTEMPTS_MIN}, {_MIN_ATTEMPTS_MAX}]"
                    )
                }
            ), 400

    # Validate cleanup_foreign_tracks — strictly tri-state (true | false | null).
    # JSON booleans in Python are also `int` subclasses, so reject non-bool ints
    # explicitly to stop "cleanup_foreign_tracks: 1" from masquerading as True.
    if "cleanup_foreign_tracks" in data:
        cv = data["cleanup_foreign_tracks"]
        if cv is not None and not isinstance(cv, bool):
            return jsonify({"error": "cleanup_foreign_tracks must be true, false, or null"}), 400

    # Validate subtitle_format_requirement — null (inherit) or "require_ass"
    if "subtitle_format_requirement" in data:
        fv = data["subtitle_format_requirement"]
        if fv is not None and fv not in _ALLOWED_FORMAT_REQUIREMENTS:
            return jsonify(
                {
                    "error": (
                        "subtitle_format_requirement must be one of "
                        f"{sorted(_ALLOWED_FORMAT_REQUIREMENTS)} or null"
                    )
                }
            ), 400

    from services.standalone_owner_keys import row_for_write

    now = datetime.now(UTC)
    row = row_for_write(
        SeriesSettings, series_id, absolute_order=0, min_attempts_per_day=0, updated_at=now
    )

    if "priority_override" in data:
        row.priority_override = data["priority_override"]
    if "min_attempts_per_day" in data:
        row.min_attempts_per_day = int(data["min_attempts_per_day"])
    if "cleanup_foreign_tracks" in data:
        row.cleanup_foreign_tracks = data["cleanup_foreign_tracks"]
    if "subtitle_format_requirement" in data:
        row.subtitle_format_requirement = data["subtitle_format_requirement"]
    row.updated_at = now
    db.session.commit()

    return jsonify(_payload(row)), 200
