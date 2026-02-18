"""Provider cache and statistics database operations -- delegating to SQLAlchemy repository."""

from typing import Optional

from db.repositories.providers import ProviderRepository

_repo = None


def _get_repo():
    global _repo
    if _repo is None:
        _repo = ProviderRepository()
    return _repo


# ---- Provider Cache ----

def cache_provider_results(provider_name: str, query_hash: str, results_json: str,
                          ttl_hours: int = 6, format_filter: str = None):
    """Cache provider search results."""
    return _get_repo().cache_provider_results(
        provider_name, query_hash, results_json, ttl_hours, format_filter
    )


def get_cached_results(provider_name: str, query_hash: str,
                       format_filter: str = None) -> Optional[str]:
    """Get cached provider results if not expired."""
    return _get_repo().get_cached_results(provider_name, query_hash, format_filter)


def cleanup_expired_cache():
    """Remove expired cache entries."""
    return _get_repo().cleanup_expired_cache()


def get_provider_cache_stats() -> dict:
    """Get aggregated cache stats per provider (total entries, active/expired)."""
    return _get_repo().get_provider_cache_stats()


def get_provider_download_stats() -> dict:
    """Get download counts per provider, broken down by format."""
    return _get_repo().get_provider_download_stats()


def clear_provider_cache(provider_name: str = None):
    """Clear provider cache. If provider_name is given, only clear that provider.

    Also clears the fast app cache layer (Redis or memory) so stale
    entries are not served from the fast tier.
    """
    # Clear fast cache layer
    try:
        from db.repositories.cache import CacheRepository
        prefix = f"provider:{provider_name}:" if provider_name else "provider:"
        CacheRepository.invalidate_app_cache(prefix=prefix)
    except Exception:
        pass  # Non-blocking -- DB cache clear proceeds regardless
    return _get_repo().clear_provider_cache(provider_name)


def record_subtitle_download(provider_name: str, subtitle_id: str, language: str,
                              fmt: str, file_path: str, score: int):
    """Record a subtitle download for history tracking."""
    return _get_repo().record_subtitle_download(
        provider_name, subtitle_id, language, fmt, file_path, score
    )


# ---- Provider Statistics ----

def update_provider_stats(provider_name: str, success: bool, score: int = 0,
                          response_time_ms: float = None):
    """Update provider statistics after a search/download attempt."""
    _get_repo().record_search(provider_name, success, response_time_ms)
    if success and score > 0:
        _get_repo().record_download(provider_name, score)


def record_search(provider_name: str, success: bool,
                  response_time_ms: float = None):
    """Record a search attempt."""
    return _get_repo().record_search(provider_name, success, response_time_ms)


def record_download(provider_name: str, score: int):
    """Record a successful download."""
    return _get_repo().record_download(provider_name, score)


def record_download_failure(provider_name: str):
    """Record a failed download attempt."""
    return _get_repo().record_download_failure(provider_name)


def get_provider_stats(provider_name: str = None) -> dict:
    """Get provider statistics."""
    return _get_repo().get_provider_stats(provider_name)


def get_all_provider_stats() -> list:
    """Get all provider stats as a list of dicts."""
    return _get_repo().get_all_provider_stats()


def clear_provider_stats(provider_name: str) -> bool:
    """Clear stats for a specific provider. Returns True if deleted."""
    return _get_repo().clear_provider_stats(provider_name)


# ---- Auto-disable ----

def auto_disable_provider(provider_name: str, cooldown_minutes: int = 30):
    """Auto-disable a provider with a cooldown period."""
    return _get_repo().auto_disable_provider(provider_name, cooldown_minutes)


def is_provider_auto_disabled(provider_name: str) -> bool:
    """Check if a provider is currently auto-disabled."""
    return _get_repo().is_auto_disabled(provider_name)


def clear_auto_disable(provider_name: str):
    """Manually clear the auto-disable flag for a provider."""
    return _get_repo().clear_auto_disable(provider_name)


def check_auto_disable(provider_name: str, threshold: int) -> bool:
    """Check if consecutive_failures >= threshold. If so, auto-disable."""
    return _get_repo().check_auto_disable(provider_name, threshold)


def get_disabled_providers() -> list:
    """Get all currently auto-disabled providers."""
    return _get_repo().get_disabled_providers()


def get_provider_health_history(provider_name: str = None, days: int = 7) -> list:
    """Get provider health history as daily aggregates."""
    return _get_repo().get_provider_health_history(provider_name, days)


def get_provider_success_rate(provider_name: str) -> float:
    """Get success rate for a provider (0.0 to 1.0)."""
    return _get_repo().get_provider_success_rate(provider_name)
