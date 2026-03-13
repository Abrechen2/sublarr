"""Series audio track preference endpoints.

GET  /api/v1/series/<series_id>/audio-track-pref
PUT  /api/v1/series/<series_id>/audio-track-pref
"""

import logging

from flask import Blueprint, jsonify, request

from db.repositories.series_audio import SeriesAudioRepository

bp = Blueprint("series_audio", __name__, url_prefix="/api/v1/series")
logger = logging.getLogger(__name__)


@bp.route("/<int:series_id>/audio-track-pref", methods=["GET"])
def get_audio_track_pref(series_id: int):
    """Return the pinned audio track index for a series.

    Returns {"series_id": int, "preferred_audio_track_index": int | null}.
    Returns null when no preference is set (auto-select will be used).
    """
    pref = SeriesAudioRepository().get_audio_track_pref(series_id)
    return jsonify({"series_id": series_id, "preferred_audio_track_index": pref})


@bp.route("/<int:series_id>/audio-track-pref", methods=["PUT"])
def set_audio_track_pref(series_id: int):
    """Set or clear the pinned audio track index for a series.

    Body: {"preferred_audio_track_index": int | null}
    Pass null to clear the preference (auto-select resumes).
    """
    data = request.get_json(force=True, silent=True) or {}
    raw = data.get("preferred_audio_track_index", "MISSING")

    if raw == "MISSING":
        return jsonify({"error": "preferred_audio_track_index is required"}), 400

    if raw is not None and (not isinstance(raw, int) or raw < 0):
        return (
            jsonify(
                {"error": "preferred_audio_track_index must be a non-negative integer or null"}
            ),
            400,
        )

    SeriesAudioRepository().set_audio_track_pref(series_id=series_id, track_index=raw)
    logger.info("Series %d: preferred_audio_track_index -> %s", series_id, raw)
    return jsonify({"series_id": series_id, "preferred_audio_track_index": raw})
