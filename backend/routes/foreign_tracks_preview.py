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


@bp.route("/preview-file", methods=["POST"])
def preview_file():
    """Show what the cleanup would keep and strip in one file, without touching it.
    ---
    post:
      tags: [Cleanup]
      summary: Per-track foreign-track cleanup preview for one video
      description: >
        Read-only. Resolves the effective track variant policy and keep-set
        for the given file (optionally scoped to a series/movie override)
        and returns the same per-track verdict `select_tracks` would
        produce for a real strip. Never remuxes or writes to the file.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [path]
              properties:
                path: {type: string}
                series_id: {type: integer}
                movie_id: {type: integer}
      responses:
        200: {description: Verdict per subtitle track}
        400: {description: Missing path}
        403: {description: Path outside the media root}
        404: {description: File not found}
    """
    from config import get_settings
    from remux import get_media_streams
    from services.foreign_track_cleanup import keep_tags_for
    from services.foreign_tracks.policy import resolve_policy
    from services.foreign_tracks.select import SIDECAR_DROP, select_tracks
    from services.foreign_tracks.sidecars import real_sidecar_languages

    data = request.get_json(silent=True) or {}
    path = data.get("path")
    if not path:
        return jsonify({"error": "path is required"}), 400

    settings = get_settings()
    if not is_safe_path(path, settings.media_path):
        return jsonify({"error": "path outside the media root"}), 403
    if not os.path.isfile(path):
        return jsonify({"error": "file not found"}), 404

    series_id = data.get("series_id")
    movie_id = data.get("movie_id")
    policy = resolve_policy(series_id=series_id, movie_id=movie_id)
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
