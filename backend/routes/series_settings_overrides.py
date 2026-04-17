"""PATCH /api/v1/series/<id>/settings — priority_override + min_attempts_per_day (Phase 4a)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from flask import Blueprint, jsonify, request

from db.models.core import SeriesSettings
from extensions import db

logger = logging.getLogger(__name__)

bp = Blueprint("series_settings_overrides", __name__, url_prefix="/api/v1/series")

_ALLOWED_PRIORITY = {"premium", "standard", "backlog"}
_MIN_ATTEMPTS_MIN = 0
_MIN_ATTEMPTS_MAX = 50


@bp.route("/<int:series_id>/settings", methods=["PATCH"])
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

    now = datetime.now(UTC)
    row = db.session.get(SeriesSettings, series_id)
    if row is None:
        row = SeriesSettings(
            sonarr_series_id=series_id,
            absolute_order=0,
            min_attempts_per_day=0,
            updated_at=now,
        )
        db.session.add(row)

    if "priority_override" in data:
        row.priority_override = data["priority_override"]
    if "min_attempts_per_day" in data:
        row.min_attempts_per_day = int(data["min_attempts_per_day"])
    row.updated_at = now
    db.session.commit()

    return jsonify(
        {
            "sonarr_series_id": row.sonarr_series_id,
            "priority_override": row.priority_override,
            "min_attempts_per_day": row.min_attempts_per_day,
        }
    ), 200
