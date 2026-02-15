"""Provider routes — /providers, /providers/test, /providers/search, /providers/stats, /providers/cache/clear."""

import logging
from flask import Blueprint, request, jsonify

bp = Blueprint("providers", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)


@bp.route("/providers", methods=["GET"])
def list_providers():
    """Get status of all subtitle providers."""
    from providers import get_provider_manager
    manager = get_provider_manager()
    return jsonify({"providers": manager.get_provider_status()})


@bp.route("/providers/test/<provider_name>", methods=["POST"])
def test_provider(provider_name):
    """Test a specific provider's connectivity and optionally perform a search.

    Body (optional): {
        "test_search": true,
        "query": {
            "series_title": "...",
            "season": 1,
            "episode": 1,
            "language": "en"
        }
    }
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
        data = request.get_json() or {}
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

    Body: {
        "file_path": "/media/anime/...",
        "series_title": "...",
        "season": 1,
        "episode": 1,
        "language": "en",
        "format": "ass"  // optional filter
    }
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
    """Get cache, download, and performance statistics for all providers."""
    from db.providers import (
        get_provider_cache_stats, get_provider_download_stats,
        get_provider_stats, get_provider_success_rate, is_provider_auto_disabled,
    )

    cache_stats = get_provider_cache_stats()
    download_stats = get_provider_download_stats()
    performance_stats = get_provider_stats()  # All provider stats

    # Add success rates and response time data to performance stats
    for provider_name in performance_stats:
        performance_stats[provider_name]["success_rate"] = get_provider_success_rate(provider_name)
        performance_stats[provider_name]["auto_disabled"] = is_provider_auto_disabled(provider_name)

    return jsonify({
        "cache": cache_stats,
        "downloads": download_stats,
        "performance": performance_stats,
    })


@bp.route("/providers/health", methods=["GET"])
def provider_health():
    """Get health overview for all providers (dashboard-oriented endpoint).

    Returns per-provider: name, healthy, success_rate, avg_response_time_ms,
    last_response_time_ms, auto_disabled, disabled_until, consecutive_failures.
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
    """Manually re-enable an auto-disabled provider."""
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
    """Clear provider cache. Optional body: {provider_name: "..."}"""
    from db.providers import clear_provider_cache

    data = request.get_json(silent=True) or {}
    provider_name = data.get("provider_name")
    clear_provider_cache(provider_name)
    return jsonify({
        "status": "cleared",
        "provider": provider_name or "all",
    })
