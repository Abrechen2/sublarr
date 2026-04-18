"""GET /api/v1/whisper/stats — aggregated Whisper transcription stats."""

import logging

from flask import jsonify

from routes.whisper import bp

logger = logging.getLogger(__name__)


@bp.route("/stats", methods=["GET"])
def whisper_stats():
    """Get Whisper statistics.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Whisper
      summary: Get Whisper statistics
      description: Returns aggregated Whisper transcription statistics including total jobs, status breakdown, and average processing time.
      responses:
        200:
          description: Whisper stats
          content:
            application/json:
              schema:
                type: object
                properties:
                  total:
                    type: integer
                  by_status:
                    type: object
                    additionalProperties:
                      type: integer
                  avg_processing_time:
                    type: number
    """
    from db.whisper import get_whisper_stats

    stats = get_whisper_stats()
    return jsonify(stats)
