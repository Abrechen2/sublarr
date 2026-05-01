"""Provider management routes: list, test, enable, cache/clear."""

import logging

from flask import jsonify, request

from cache_response import cached_get
from extensions import limiter
from routes.providers import bp

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
@limiter.limit("10 per minute")
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
        from providers.base import ProviderAuthError, ProviderRateLimitError, VideoQuery

        manager = get_provider_manager()
        provider = manager._providers.get(provider_name)
        if not provider:
            return jsonify(
                {
                    "error": f"Provider '{provider_name}' not found or not enabled",
                    "available_providers": list(manager._providers.keys()),
                }
            ), 404

        result = {
            "provider": provider_name,
            "initialized": provider.session is not None if hasattr(provider, "session") else True,
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
        return jsonify(
            {
                "status": "already_enabled",
                "provider": name,
                "message": f"Provider '{name}' is not auto-disabled",
            }
        )

    clear_auto_disable(name)
    return jsonify(
        {
            "status": "enabled",
            "provider": name,
            "message": f"Provider '{name}' has been re-enabled",
        }
    )


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
    return jsonify(
        {
            "status": "cleared",
            "provider": provider_name or "all",
        }
    )
