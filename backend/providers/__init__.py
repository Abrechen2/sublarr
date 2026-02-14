"""Subtitle provider system — search and download subtitles from multiple sources.

The ProviderManager orchestrates searches across enabled providers,
scores results, and returns the best match.

Usage:
    from providers import get_provider_manager

    manager = get_provider_manager()
    results = manager.search(query)
    if results:
        content = manager.download(results[0])
"""

import os
import logging
from typing import Optional

from providers.base import (
    SubtitleProvider,
    SubtitleResult,
    SubtitleFormat,
    VideoQuery,
    compute_score,
)

logger = logging.getLogger(__name__)

# Provider registry — maps name to class
_PROVIDER_CLASSES: dict[str, type[SubtitleProvider]] = {}

# Singleton manager
_manager: Optional["ProviderManager"] = None


def register_provider(cls: type[SubtitleProvider]) -> type[SubtitleProvider]:
    """Decorator to register a provider class."""
    _PROVIDER_CLASSES[cls.name] = cls
    return cls


def get_provider_manager() -> "ProviderManager":
    """Get or create the singleton ProviderManager."""
    global _manager
    if _manager is None:
        _manager = ProviderManager()
    return _manager


def invalidate_manager():
    """Reset the manager (call after config changes)."""
    global _manager
    if _manager:
        _manager.shutdown()
    _manager = None


class ProviderManager:
    """Manages multiple subtitle providers with priority ordering and scoring."""

    def __init__(self):
        from config import get_settings
        self.settings = get_settings()
        self._providers: dict[str, SubtitleProvider] = {}
        self._init_providers()

    def _init_providers(self):
        """Initialize enabled providers based on config."""
        # Import providers to trigger registration
        try:
            from providers import opensubtitles  # noqa: F401
        except ImportError as e:
            logger.debug("OpenSubtitles provider not available: %s", e)
        try:
            from providers import jimaku  # noqa: F401
        except ImportError as e:
            logger.debug("Jimaku provider not available: %s", e)
        try:
            from providers import animetosho  # noqa: F401
        except ImportError as e:
            logger.debug("AnimeTosho provider not available: %s", e)
        try:
            from providers import subdl  # noqa: F401
        except ImportError as e:
            logger.debug("SubDL provider not available: %s", e)

        # Get priority order from config
        priority_str = getattr(self.settings, "provider_priorities", "animetosho,jimaku,opensubtitles,subdl")
        priority_list = [p.strip() for p in priority_str.split(",") if p.strip()]

        # Get enabled providers
        enabled_str = getattr(self.settings, "providers_enabled", "")
        if enabled_str:
            enabled_set = {p.strip() for p in enabled_str.split(",") if p.strip()}
        else:
            # Default: enable all registered providers
            enabled_set = set(_PROVIDER_CLASSES.keys())

        # Initialize providers in priority order
        for name in priority_list:
            if name not in _PROVIDER_CLASSES:
                continue
            if name not in enabled_set:
                continue

            try:
                config = self._get_provider_config(name)
                provider = _PROVIDER_CLASSES[name](**config)
                provider.initialize()
                self._providers[name] = provider
                logger.info("Provider initialized: %s", name)
            except Exception as e:
                logger.warning("Failed to initialize provider %s: %s", name, e)

        # Add any enabled providers not in priority list
        for name in enabled_set:
            if name in self._providers:
                continue
            if name not in _PROVIDER_CLASSES:
                continue
            try:
                config = self._get_provider_config(name)
                provider = _PROVIDER_CLASSES[name](**config)
                provider.initialize()
                self._providers[name] = provider
                logger.info("Provider initialized: %s", name)
            except Exception as e:
                logger.warning("Failed to initialize provider %s: %s", name, e)

        logger.info("Active providers: %s", list(self._providers.keys()))

    def _get_provider_config(self, name: str) -> dict:
        """Get provider-specific config from settings."""
        config = {}

        if name == "opensubtitles":
            config["api_key"] = getattr(self.settings, "opensubtitles_api_key", "")
            config["username"] = getattr(self.settings, "opensubtitles_username", "")
            config["password"] = getattr(self.settings, "opensubtitles_password", "")
        elif name == "jimaku":
            config["api_key"] = getattr(self.settings, "jimaku_api_key", "")
        elif name == "animetosho":
            pass  # No auth needed
        elif name == "subdl":
            config["api_key"] = getattr(self.settings, "subdl_api_key", "")

        return config

    def search(
        self,
        query: VideoQuery,
        format_filter: Optional[SubtitleFormat] = None,
        min_score: int = 0,
    ) -> list[SubtitleResult]:
        """Search all providers and return scored, sorted results.

        Args:
            query: What to search for
            format_filter: Only return results of this format (e.g. ASS)
            min_score: Minimum score threshold

        Returns:
            List of SubtitleResult sorted by score (highest first)
        """
        all_results: list[SubtitleResult] = []

        for name, provider in self._providers.items():
            try:
                results = provider.search(query)
                logger.info("Provider %s returned %d results", name, len(results))
                all_results.extend(results)
            except Exception as e:
                logger.warning("Provider %s search failed: %s", name, e)

        # Score all results
        for result in all_results:
            compute_score(result, query)

        # Filter by format
        if format_filter:
            all_results = [r for r in all_results if r.format == format_filter]

        # Filter by min score
        if min_score > 0:
            all_results = [r for r in all_results if r.score >= min_score]

        # Sort by score descending
        all_results.sort(key=lambda r: r.score, reverse=True)

        return all_results

    def download(self, result: SubtitleResult) -> Optional[bytes]:
        """Download a subtitle from its provider.

        Args:
            result: A SubtitleResult from search()

        Returns:
            Raw subtitle file content, or None on failure
        """
        provider = self._providers.get(result.provider_name)
        if not provider:
            logger.error("Provider %s not available for download", result.provider_name)
            return None

        try:
            content = provider.download(result)
            result.content = content
            return content
        except Exception as e:
            logger.error("Download from %s failed: %s", result.provider_name, e)
            return None

    def search_and_download_best(
        self,
        query: VideoQuery,
        format_filter: Optional[SubtitleFormat] = None,
        min_score: int = 0,
    ) -> Optional[SubtitleResult]:
        """Convenience: search, pick best, download it.

        Returns:
            SubtitleResult with content populated, or None
        """
        results = self.search(query, format_filter=format_filter, min_score=min_score)
        if not results:
            return None

        # Try results in order until one downloads successfully
        for result in results:
            content = self.download(result)
            if content:
                return result
            logger.warning("Download failed for %s, trying next", result.subtitle_id)

        return None

    def save_subtitle(self, result: SubtitleResult, output_path: str) -> str:
        """Save a downloaded subtitle to disk.

        Args:
            result: SubtitleResult with content populated
            output_path: Base path (without extension — extension from format)

        Returns:
            Path to saved file
        """
        if not result.content:
            raise ValueError("SubtitleResult has no content (download first)")

        # Determine extension
        ext = result.format.value if result.format != SubtitleFormat.UNKNOWN else "srt"
        if not output_path.endswith(f".{ext}"):
            # If output_path already has an extension, replace it
            base, _ = os.path.splitext(output_path)
            output_path = f"{base}.{ext}"

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, "wb") as f:
            f.write(result.content)

        logger.info("Saved subtitle: %s (%s, %s, score=%d)",
                     output_path, result.provider_name, result.language, result.score)
        return output_path

    def get_provider_status(self) -> list[dict]:
        """Get status of all providers (for API/UI) with priority, downloads, config_fields."""
        from database import get_provider_download_stats

        # Build priority order
        priority_str = getattr(self.settings, "provider_priorities", "animetosho,jimaku,opensubtitles,subdl")
        priority_list = [p.strip() for p in priority_str.split(",") if p.strip()]

        # Get enabled set
        enabled_str = getattr(self.settings, "providers_enabled", "")
        if enabled_str:
            enabled_set = {p.strip() for p in enabled_str.split(",") if p.strip()}
        else:
            enabled_set = set(_PROVIDER_CLASSES.keys())

        # Download stats from DB
        download_stats = get_provider_download_stats()

        statuses = []
        for name, cls in _PROVIDER_CLASSES.items():
            priority = priority_list.index(name) if name in priority_list else len(priority_list)
            downloads = download_stats.get(name, {}).get("total", 0)
            config_fields = self._get_provider_config_fields(name)

            provider = self._providers.get(name)
            if provider:
                try:
                    healthy, msg = provider.health_check()
                except Exception as e:
                    healthy, msg = False, str(e)
                statuses.append({
                    "name": name,
                    "enabled": True,
                    "initialized": True,
                    "healthy": healthy,
                    "message": msg,
                    "priority": priority,
                    "downloads": downloads,
                    "config_fields": config_fields,
                })
            else:
                statuses.append({
                    "name": name,
                    "enabled": name in enabled_set,
                    "initialized": False,
                    "healthy": False,
                    "message": "Not initialized",
                    "priority": priority,
                    "downloads": downloads,
                    "config_fields": config_fields,
                })

        # Sort by priority
        statuses.sort(key=lambda s: s["priority"])
        return statuses

    @staticmethod
    def _get_provider_config_fields(name: str) -> list[dict]:
        """Return config field definitions for a provider (for dynamic UI forms)."""
        fields_map = {
            "opensubtitles": [
                {"key": "opensubtitles_api_key", "label": "API Key", "type": "password", "required": True},
                {"key": "opensubtitles_username", "label": "Username", "type": "text", "required": False},
                {"key": "opensubtitles_password", "label": "Password", "type": "password", "required": False},
            ],
            "jimaku": [
                {"key": "jimaku_api_key", "label": "API Key", "type": "password", "required": True},
            ],
            "animetosho": [],  # No auth needed
            "subdl": [
                {"key": "subdl_api_key", "label": "API Key", "type": "password", "required": True},
            ],
        }
        return fields_map.get(name, [])

    def shutdown(self):
        """Terminate all providers."""
        for name, provider in self._providers.items():
            try:
                provider.terminate()
            except Exception as e:
                logger.warning("Error terminating provider %s: %s", name, e)
        self._providers.clear()
