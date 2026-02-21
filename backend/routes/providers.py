"""Provider routes — /providers, /providers/test, /providers/search, /providers/stats, /providers/cache/clear."""

import logging
from flask import Blueprint, request, jsonify

from cache_response import cached_get, invalidate_response_cache

bp = Blueprint("providers", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)


@bp.route("/providers", methods=["GET"])
@cached_get(ttl_seconds=60)
def list_providers():
    """Get status of all subtitle providers.
    ---
    get:
      tags:
        - Providers
      summary: List all providers
      description: Returns the status of all registered subtitle providers including health, circuit breaker state, and configuration.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Provider list
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
                        initialized:
                          type: boolean
    """
    from providers import get_provider_manager
    manager = get_provider_manager()
    return jsonify({"providers": manager.get_provider_status()})


@bp.route("/providers/test/<provider_name>", methods=["POST"])
def test_provider(provider_name):
    """Test a specific provider's connectivity and optionally perform a search.
    ---
    post:
      tags:
        - Providers
      summary: Test a provider
      description: Runs a health check on the specified provider and optionally performs a test search.
      security:
        - apiKeyAuth: []
      parameters:
        - in: path
          name: provider_name
          required: true
          schema:
            type: string
          description: Provider name (e.g. animetosho, opensubtitles, jimaku, subdl)
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                test_search:
                  type: boolean
                  default: false
                  description: Whether to also perform a test search
                query:
                  type: object
                  properties:
                    series_title:
                      type: string
                    title:
                      type: string
                    season:
                      type: integer
                    episode:
                      type: integer
                    language:
                      type: string
                      default: en
      responses:
        200:
          description: Test results
          content:
            application/json:
              schema:
                type: object
                properties:
                  provider:
                    type: string
                  initialized:
                    type: boolean
                  health_check:
                    type: object
                    properties:
                      healthy:
                        type: boolean
                      message:
                        type: string
                  search_test:
                    type: object
                    properties:
                      success:
                        type: boolean
                      results_count:
                        type: integer
        404:
          description: Provider not found
    """
    try:
        from providers import get_provider_manager
        from providers.base import VideoQuery, ProviderAuthError, ProviderRateLimitError

        manager = get_provider_manager()
        provider = manager._providers.get(provider_name)
        if not provider:
            return jsonify({
                "error": f"Provider '{provider_name}' not found or not enabled",
                "available_providers": list(manager._providers.keys())
            }), 404

        result = {
            "provider": provider_name,
            "initialized": provider.session is not None if hasattr(provider, 'session') else True,
        }

        # Health check
        try:
            healthy, message = provider.health_check()
            result["health_check"] = {
                "healthy": healthy,
                "message": message,
            }
        except Exception as e:
            result["health_check"] = {
                "healthy": False,
                "message": f"Health check failed: {str(e)}",
                "error": str(e),
            }

        # Optional search test
        data = request.get_json(force=True, silent=True) or {}
        if data.get("test_search"):
            query_data = data.get("query", {})
            test_query = VideoQuery(
                series_title=query_data.get("series_title", ""),
                title=query_data.get("title", ""),
                season=query_data.get("season"),
                episode=query_data.get("episode"),
                languages=[query_data.get("language", "en")],
            )

            try:
                search_results = provider.search(test_query)
                result["search_test"] = {
                    "success": True,
                    "results_count": len(search_results),
                    "query": {
                        "display_name": test_query.display_name,
                        "languages": test_query.languages,
                    },
                    "top_results": [
                        {
                            "filename": r.filename,
                            "language": r.language,
                            "format": r.format.value,
                            "score": r.score,
                        }
                        for r in search_results[:5]
                    ],
                }
            except ProviderAuthError as e:
                result["search_test"] = {
                    "success": False,
                    "error": "authentication_failed",
                    "message": str(e),
                }
            except ProviderRateLimitError as e:
                result["search_test"] = {
                    "success": False,
                    "error": "rate_limit_exceeded",
                    "message": str(e),
                }
            except Exception as e:
                result["search_test"] = {
                    "success": False,
                    "error": "search_failed",
                    "message": str(e),
                }

        return jsonify(result)
    except Exception:
        raise  # Handled by global error handler


@bp.route("/providers/search", methods=["POST"])
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
    from providers import get_provider_manager
    from providers.base import VideoQuery, SubtitleFormat
    from config import get_settings

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
        try:
            format_filter = SubtitleFormat(data["format"])
        except ValueError:
            pass

    try:
        manager = get_provider_manager()
        results = manager.search(query, format_filter=format_filter)

        return jsonify({
            "results": [
                {
                    "provider": r.provider_name,
                    "subtitle_id": r.subtitle_id,
                    "language": r.language,
                    "format": r.format.value,
                    "filename": r.filename,
                    "release_info": r.release_info,
                    "score": r.score,
                    "hearing_impaired": r.hearing_impaired,
                    "matches": list(r.matches),
                }
                for r in results[:50]  # Limit response size
            ],
            "total": len(results),
        })
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
        get_provider_cache_stats, get_provider_download_stats,
        get_all_provider_stats_enriched,
    )

    cache_stats = get_provider_cache_stats()
    download_stats = get_provider_download_stats()
    # Single batch query: success_rate and auto_disabled computed inline (was N+1)
    performance_stats = get_all_provider_stats_enriched()

    return jsonify({
        "cache": cache_stats,
        "downloads": download_stats,
        "performance": performance_stats,
    })


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
        health_data.append({
            "name": s["name"],
            "healthy": s["healthy"],
            "enabled": s["enabled"],
            "initialized": s["initialized"],
            "success_rate": stats.get("success_rate", 0),
            "avg_response_time_ms": stats.get("avg_response_time_ms", 0),
            "last_response_time_ms": stats.get("last_response_time_ms", 0),
            "auto_disabled": stats.get("auto_disabled", False),
            "disabled_until": stats.get("disabled_until", ""),
            "consecutive_failures": stats.get("consecutive_failures", 0),
            "total_searches": stats.get("total_searches", 0),
        })

    return jsonify({"providers": health_data})


@bp.route("/providers/<name>/enable", methods=["POST"])
def enable_provider(name):
    """Manually re-enable an auto-disabled provider.
    ---
    post:
      tags:
        - Providers
      summary: Re-enable provider
      description: Clears auto-disable state and resets consecutive failure count for the specified provider.
      security:
        - apiKeyAuth: []
      parameters:
        - in: path
          name: name
          required: true
          schema:
            type: string
          description: Provider name
      responses:
        200:
          description: Provider re-enabled or already enabled
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                    enum: [enabled, already_enabled]
                  provider:
                    type: string
                  message:
                    type: string
    """
    from db.providers import clear_auto_disable, is_provider_auto_disabled

    if not is_provider_auto_disabled(name):
        return jsonify({
            "status": "already_enabled",
            "provider": name,
            "message": f"Provider '{name}' is not auto-disabled",
        })

    clear_auto_disable(name)
    return jsonify({
        "status": "enabled",
        "provider": name,
        "message": f"Provider '{name}' has been re-enabled",
    })


@bp.route("/providers/cache/clear", methods=["POST"])
def clear_cache():
    """Clear provider cache.
    ---
    post:
      tags:
        - Providers
      summary: Clear provider cache
      description: Clears the search result cache for all providers or a specific provider.
      security:
        - apiKeyAuth: []
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                provider_name:
                  type: string
                  description: Optional specific provider to clear. Omit to clear all.
      responses:
        200:
          description: Cache cleared
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  provider:
                    type: string
    """
    from db.providers import clear_provider_cache

    data = request.get_json(silent=True) or {}
    provider_name = data.get("provider_name")
    clear_provider_cache(provider_name)
    return jsonify({
        "status": "cleared",
        "provider": provider_name or "all",
    })
