"""AI subtitle-quality routes — advisory LLM verdicts for downloaded sidecars.

GET  /api/v1/quality/ai         — fetch the stored verdict for one sidecar path
POST /api/v1/quality/ai/analyze — queue (re-)analysis of a sidecar (202)
"""

import logging
import os

from flask import Blueprint, jsonify, request

from config import get_settings
from security_utils import is_safe_path

bp = Blueprint("ai_quality", __name__, url_prefix="/api/v1")

logger = logging.getLogger(__name__)


@bp.route("/quality/ai", methods=["GET"])
def get_ai_quality():
    """Get the stored AI quality verdict for a subtitle sidecar.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Quality
      summary: Get AI quality verdict
      description: Returns the stored advisory LLM verdict for a subtitle sidecar path, or result null if none exists.
      parameters:
        - in: query
          name: path
          required: true
          schema:
            type: string
          description: Absolute path of the subtitle sidecar file
      responses:
        200:
          description: Verdict (result is null when not analyzed)
        400:
          description: Missing path
        403:
          description: Path outside the media directory
    """
    path = request.args.get("path", "")
    if not path:
        return jsonify({"error": "path parameter required"}), 400
    if not is_safe_path(path, get_settings().media_path):
        return jsonify({"error": "Access denied"}), 403

    import json

    from db.quality import get_ai_quality_result

    row = get_ai_quality_result(path)
    if not row:
        return jsonify({"result": None})
    try:
        scores = json.loads(row.get("scores_json") or "{}")
        reasons = json.loads(row.get("reasons_json") or "[]")
    except ValueError:
        scores, reasons = {}, []
    return jsonify(
        {
            "result": {
                "verdict": row.get("verdict"),
                "scores": scores,
                "reasons": reasons,
                "model": row.get("model") or "",
                "sampled_cues": row.get("sampled_cues") or 0,
                "created_at": row.get("created_at"),
            }
        }
    )


@bp.route("/quality/ai/analyze", methods=["POST"])
def analyze_ai_quality():
    """Queue AI quality analysis for a subtitle sidecar.
    ---
    post:
      security:
        - apiKeyAuth: []
      tags:
        - Quality
      summary: Queue AI quality analysis
      description: Runs the advisory LLM quality check for a sidecar in the background. Requires ai_quality_enabled.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [path]
              properties:
                path:
                  type: string
                  description: Absolute path of the subtitle sidecar file
                language:
                  type: string
                  description: Language code of the subtitle (used in the prompt)
      responses:
        202:
          description: Analysis queued
        400:
          description: Missing path
        403:
          description: Path outside the media directory
        404:
          description: Sidecar not found
        503:
          description: Feature disabled
    """
    settings = get_settings()
    if not getattr(settings, "ai_quality_enabled", False):
        return jsonify({"error": "AI quality check is disabled"}), 503

    data = request.get_json(silent=True) or {}
    path = data.get("path", "")
    language = (data.get("language") or "").strip()
    if not path:
        return jsonify({"error": "path required"}), 400
    if not is_safe_path(path, settings.media_path):
        return jsonify({"error": "Access denied"}), 403
    if not os.path.isfile(path):
        return jsonify({"error": "File not found"}), 404

    from flask import current_app

    from services.background_tasks import submit_background

    app = current_app._get_current_object()

    def _run():
        with app.app_context():
            from services.ai_quality import analyze_and_store

            analyze_and_store(path, language)

    submit_background(_run)
    return jsonify({"status": "queued"}), 202
