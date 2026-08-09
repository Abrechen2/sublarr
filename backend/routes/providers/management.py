"""Provider management routes: list, test, enable, cache/clear."""

import logging
import re

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


def _probe_query_from_wanted() -> dict:
    """Build a search query from the first wanted item, or return {}.

    A provider test is only informative against something the provider might
    plausibly have. Inventing a famous title would test a provider's catalogue
    rather than this install's; the wanted list is by definition what the
    operator cares about and expects to be found.
    """
    try:
        from db.repositories.wanted import WantedRepository

        page = WantedRepository().get_wanted_items(page=1, per_page=1, status="wanted")
        items = page.get("data") or page.get("items") or []
        if not items:
            return {}
        item = items[0]
        season_episode = item.get("season_episode") or ""
        season = episode = None
        match = re.match(r"[Ss](\d+)[Ee](\d+)", season_episode)
        if match:
            season, episode = int(match.group(1)), int(match.group(2))
        title = item.get("title") or ""
        # Titles are stored as "Series — S01E02"; the provider wants the series.
        series_title = title.split("—")[0].strip() if "—" in title else title
        return {
            "series_title": series_title,
            "title": series_title,
            "season": season,
            "episode": episode,
            "language": item.get("target_language") or "en",
        }
    except Exception:  # noqa: BLE001 — a probe that cannot be built is not a test failure
        logger.debug("provider test: could not build a probe query", exc_info=True)
        return {}


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
                test_download:
                  type: boolean
                  description: >
                    Fetch one real subtitle from the top search result and
                    discard it, to exercise the download path. Requires
                    `test_search`. Nothing is stored and no statistics are
                    recorded. Worth using because a provider can pass every
                    search while its download path is dead — search and
                    download use different credentials.
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
            if not query_data:
                # Probe with something the install actually wants. A caller
                # that sends no query searches for the empty string, finds
                # nothing, and the download path — the whole point of the
                # download test — is never reached, so the button answers a
                # question nobody asked.
                query_data = _probe_query_from_wanted()
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

            # Optional download test — only meaningful on top of a search.
            #
            # A search-only test passes while the download path is dead, and
            # that is not hypothetical: an OpenSubtitles token expires after
            # 24h while search keeps working on the API key alone, which hid a
            # three-day outage. Fetching one real subtitle is the only way to
            # answer the question people press this button to answer.
            #
            # Nothing is recorded and nothing is written to disk: the bytes are
            # measured and dropped. A test that bumped `successful_downloads`
            # would inflate the very counter an operator reads to decide
            # whether downloads work.
            if data.get("test_download"):
                found = result.get("search_test", {}).get("success") and search_results
                if not found:
                    result["download_test"] = {
                        "success": False,
                        "error": "no_results_to_download",
                        "message": "The search returned nothing, so there was nothing to fetch.",
                    }
                else:
                    try:
                        payload = provider.download(search_results[0])
                        result["download_test"] = {
                            "success": True,
                            "bytes": len(payload or b""),
                            "filename": search_results[0].filename,
                        }
                    except ProviderAuthError as e:
                        result["download_test"] = {
                            "success": False,
                            "error": "authentication_failed",
                            "message": str(e),
                        }
                    except ProviderRateLimitError as e:
                        result["download_test"] = {
                            "success": False,
                            "error": "rate_limit_exceeded",
                            "message": str(e),
                        }
                    except Exception as e:
                        result["download_test"] = {
                            "success": False,
                            "error": "download_failed",
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
