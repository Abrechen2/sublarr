"""Read-only per-track preview of the foreign-track cleanup for one file.

`POST /api/v1/foreign-tracks/preview-file` answers with the exact
keep/strip verdict per subtitle track `select_tracks` would produce for a
real strip — without touching the file. It reaches the same keep-set as
`services.foreign_track_cleanup.maybe_run_foreign_track_cleanup` by calling
the same shared `keep_tags_for` helper, so the preview never drifts from
the real strip.
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict

from flask import Blueprint, jsonify, request

from security_utils import is_safe_path

logger = logging.getLogger(__name__)
bp = Blueprint("foreign_tracks_preview", __name__, url_prefix="/api/v1/foreign-tracks")


def _invalid_id_error(value, name: str) -> str | None:
    """Return an error message iff ``value`` is not a valid optional id.

    A valid id is either absent/``None``, or a positive ``int`` that is not
    a ``bool`` — JSON ``true``/``false`` decode as Python `bool`, which is an
    `int` subclass, so an un-guarded `isinstance(value, int)` check would
    silently accept `true` as id ``1`` and resolve an unrelated series'
    override.
    """
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return f"{name} must be a positive integer"
    return None


@bp.route("/preview-file", methods=["POST"])
def preview_file():
    """Show what the cleanup would keep and strip in one file, without touching it.
    ---
    post:
      security:
        - apiKeyAuth: []
      tags: [Cleanup]
      summary: Per-track foreign-track cleanup preview for one video
      description: >
        Read-only. Resolves the effective track variant policy and keep-set
        for the given file (optionally scoped to a series/movie override --
        the two are mutually exclusive) and returns the same per-track
        verdict `select_tracks` would produce for a real strip. Never
        remuxes or writes to the file.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [path]
              properties:
                path: {type: string}
                series_id: {type: integer, minimum: 1}
                movie_id: {type: integer, minimum: 1}
      responses:
        200: {description: Verdict per subtitle track}
        400: {description: Missing/invalid path, series_id or movie_id}
        403: {description: Path outside the media root}
        404: {description: File not found}
        503: {description: The series/movie track policy could not be resolved}
    """
    from config import get_settings
    from remux import get_media_streams
    from services.foreign_track_cleanup import keep_tags_for
    from services.foreign_tracks.policy import resolve_policy
    from services.foreign_tracks.select import SIDECAR_DROP, select_tracks
    from services.foreign_tracks.sidecars import real_sidecar_languages

    data = request.get_json(silent=True) or {}
    path = data.get("path")
    if not isinstance(path, str) or not path:
        return jsonify({"error": "path is required"}), 400

    series_id = data.get("series_id")
    movie_id = data.get("movie_id")
    error = _invalid_id_error(series_id, "series_id") or _invalid_id_error(movie_id, "movie_id")
    if error:
        return jsonify({"error": error}), 400
    if series_id is not None and movie_id is not None:
        return jsonify({"error": "series_id and movie_id are mutually exclusive"}), 400

    settings = get_settings()
    if not is_safe_path(path, settings.media_path):
        return jsonify({"error": "path outside the media root"}), 403
    if not os.path.isfile(path):
        return jsonify({"error": "file not found"}), 404

    policy = resolve_policy(series_id=series_id, movie_id=movie_id)
    if policy is None:
        # Same refusal as the real strip: an override that cannot be read is
        # never replaced by the global policy (final review I5).
        return (
            jsonify(
                {
                    "error": "The track policy for this series/movie could not be resolved "
                    "right now — try again later (see the server log)."
                }
            ),
            503,
        )
    item = {"sonarr_series_id": series_id, "radarr_movie_id": movie_id}
    base_codes, tags = keep_tags_for(item)

    real = (
        real_sidecar_languages(path, base_codes) if policy.sidecar_policy == SIDECAR_DROP else set()
    )
    verdicts = select_tracks(
        get_media_streams(path).get("streams", []),
        policy,
        tags,
        bool(getattr(settings, "cleanup_foreign_tracks_keep_und", False)),
        real,
    )
    return jsonify(
        {
            "path": path,
            "policy": asdict(policy),
            "verdicts": [v.to_dict() for v in verdicts],
        }
    )
