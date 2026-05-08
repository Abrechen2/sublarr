"""Provider search, stats, and health routes."""

import contextlib
import logging

from flask import jsonify, request

from extensions import limiter
from routes.providers import bp

logger = logging.getLogger(__name__)


@bp.route("/providers/search", methods=["POST"])
@limiter.limit("20 per minute")
def search_providers():
    """Search subtitle providers for a specific file.
    ---
    post:
      tags:
        - Providers
      summary: Search providers
      description: Searches all enabled subtitle providers for matching subtitles. Results are scored and ranked.
      security:
        - apiKeyAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                file_path:
                  type: string
                  description: Path to the media file
                series_title:
                  type: string
                  description: Series title for search
                title:
                  type: string
                  description: Episode or movie title
                season:
                  type: integer
                episode:
                  type: integer
                language:
                  type: string
                  default: en
                  description: Language code (ISO 639-1)
                imdb_id:
                  type: string
                anilist_id:
                  type: integer
                anidb_id:
                  type: integer
                format:
                  type: string
                  enum: [ass, srt]
                  description: Optional format filter
      responses:
        200:
          description: Search results
          content:
            application/json:
              schema:
                type: object
                properties:
                  results:
                    type: array
                    items:
                      type: object
                      properties:
                        provider:
                          type: string
                        subtitle_id:
                          type: string
                        language:
                          type: string
                        format:
                          type: string
                        filename:
                          type: string
                        score:
                          type: integer
                  total:
                    type: integer
    """
    from config import get_settings
    from providers import get_provider_manager
    from providers.base import SubtitleFormat, VideoQuery

    data = request.get_json() or {}

    query = VideoQuery(
        file_path=data.get("file_path", ""),
        series_title=data.get("series_title", ""),
        title=data.get("title", ""),
        season=data.get("season"),
        episode=data.get("episode"),
        imdb_id=data.get("imdb_id", ""),
        anilist_id=data.get("anilist_id"),
        anidb_id=data.get("anidb_id"),
        languages=[data.get("language", get_settings().source_language)],
    )

    format_filter = None
    if data.get("format"):
        with contextlib.suppress(ValueError):
            format_filter = SubtitleFormat(data["format"])

    try:
        manager = get_provider_manager()
        results = manager.search(query, format_filter=format_filter)

        return jsonify(
            {
                "results": [
                    {
                        "provider": r.provider_name,
                        "subtitle_id": r.subtitle_id,
                        "language": r.language,
                        "format": r.format.value,
                        "filename": r.filename,
                        "release_info": r.release_info,
                        "score": r.score,
                        "score_breakdown": r.score_breakdown,
                        "hearing_impaired": r.hearing_impaired,
                        "matches": list(r.matches),
                    }
                    for r in results[:50]  # Limit response size
                ],
                "total": len(results),
            }
        )
    except Exception:
        raise  # Handled by global error handler


@bp.route("/providers/stats", methods=["GET"])
def provider_stats():
    """Get cache, download, and performance statistics for all providers.
    ---
    get:
      tags:
        - Providers
      summary: Get provider statistics
      description: Returns cache stats, download counts, and performance metrics for all subtitle providers.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Provider statistics
          content:
            application/json:
              schema:
                type: object
                properties:
                  cache:
                    type: object
                    additionalProperties: true
                  downloads:
                    type: object
                    additionalProperties: true
                  performance:
                    type: object
                    additionalProperties: true
    """
    from db.providers import (
        get_all_provider_stats_enriched,
        get_provider_cache_stats,
        get_provider_download_stats,
    )

    cache_stats = get_provider_cache_stats()
    download_stats = get_provider_download_stats()
    # Single batch query: success_rate and auto_disabled computed inline (was N+1)
    performance_stats = get_all_provider_stats_enriched()

    return jsonify(
        {
            "cache": cache_stats,
            "downloads": download_stats,
            "performance": performance_stats,
        }
    )


@bp.route("/providers/health", methods=["GET"])
def provider_health():
    """Get health overview for all providers (dashboard-oriented endpoint).
    ---
    get:
      tags:
        - Providers
      summary: Get provider health overview
      description: >
        Returns per-provider health data including success rate, response time,
        auto-disable status, and consecutive failures. Designed for dashboard display.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Provider health data
          content:
            application/json:
              schema:
                type: object
                properties:
                  providers:
                    type: array
                    items:
                      type: object
                      properties:
                        name:
                          type: string
                        healthy:
                          type: boolean
                        enabled:
                          type: boolean
                        success_rate:
                          type: number
                        avg_response_time_ms:
                          type: number
                        auto_disabled:
                          type: boolean
                        consecutive_failures:
                          type: integer
                        total_searches:
                          type: integer
    """
    from providers import get_provider_manager

    manager = get_provider_manager()
    statuses = manager.get_provider_status()

    health_data = []
    for s in statuses:
        stats = s.get("stats", {})
        health_data.append(
            {
                "name": s["name"],
                "healthy": s["healthy"],
                "enabled": s["enabled"],
                "initialized": s["initialized"],
                "success_rate": stats.get("success_rate", 0),
                "download_rate": stats.get("download_rate", stats.get("success_rate", 0)),
                "result_rate": stats.get("result_rate", 0),
                "successful_searches": stats.get("successful_searches", 0),
                "avg_response_time_ms": stats.get("avg_response_time_ms", 0),
                "last_response_time_ms": stats.get("last_response_time_ms", 0),
                "auto_disabled": stats.get("auto_disabled", False),
                "disabled_until": stats.get("disabled_until", ""),
                "consecutive_failures": stats.get("consecutive_failures", 0),
                "total_searches": stats.get("total_searches", 0),
                "circuit_breaker_state": s.get("circuit_breaker_state", "closed"),
                "throttled_until": s.get("throttled_until"),
                "throttle_reason": s.get("throttle_reason"),
            }
        )

    return jsonify({"providers": health_data})
