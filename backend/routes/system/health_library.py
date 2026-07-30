"""GET /api/v1/health/library — library health overview for the Health page."""

import logging

from flask import jsonify

from cache_response import cached_get
from routes.system import bp

logger = logging.getLogger(__name__)


@bp.route("/health/library", methods=["GET"])
@cached_get(ttl_seconds=60)
def health_library():
    """Library health overview.
    ---
    get:
      tags:
        - System
      summary: Library health overview
      description: >
        Aggregated "where does it hurt" view: series/movies with missing
        subtitles, wanted items stuck in a failure state (including
        unmatched/unsourceable episodes), and per-provider health derived
        from circuit-breaker states and provider statistics.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Health overview
          content:
            application/json:
              schema:
                type: object
                properties:
                  totals:
                    type: object
                    additionalProperties:
                      type: integer
                  series:
                    type: array
                    items:
                      type: object
                  problems:
                    type: array
                    items:
                      type: object
                  providers:
                    type: array
                    items:
                      type: object
    """
    from services.health_overview import get_library_health

    return jsonify(get_library_health())
