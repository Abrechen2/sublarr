"""Provider search functions for subtitle download."""

import logging
import os

from config import get_settings
from translator.output_paths import get_output_path_for_lang

logger = logging.getLogger(__name__)


def _build_video_query(mkv_path, context=None):
    """Build a VideoQuery from file path and optional context."""
    from providers.base import VideoQuery

    settings = get_settings()
    query = VideoQuery(
        file_path=mkv_path,
        languages=[settings.source_language],
    )

    if context:
        query.series_title = context.get("series_title", "")
        query.title = context.get("title", "")
        if context.get("season") is not None:
            query.season = context["season"]
        if context.get("episode") is not None:
            query.episode = context["episode"]
        query.imdb_id = context.get("imdb_id", "")
        query.anidb_id = context.get("anidb_id")
        query.anilist_id = context.get("anilist_id")
        query.tvdb_id = context.get("tvdb_id")
        query.sonarr_series_id = context.get("sonarr_series_id")
        query.sonarr_episode_id = context.get("sonarr_episode_id")

    return query


def _search_providers_for_target_ass(mkv_path, context=None, target_language=None):
    """Search subtitle providers for a target language ASS file.

    Returns:
        str or None: path to downloaded ASS file, or None
    """
    try:
        from providers import get_provider_manager
        from providers.base import (
            ProviderAuthError,
            ProviderRateLimitError,
            SubtitleFormat,
        )

        settings = get_settings()
        tgt_lang = target_language or settings.target_language
        manager = get_provider_manager()

        query = _build_video_query(mkv_path, context)
        query.languages = [tgt_lang]

        result = manager.search_and_download_best(query, format_filter=SubtitleFormat.ASS)
        if result and result.content:
            output_path = get_output_path_for_lang(mkv_path, "ass", tgt_lang)
            manager.save_subtitle(
                result,
                output_path,
                series_id=context.get("sonarr_series_id") if context else None,
            )
            logger.info("Provider %s delivered target ASS: %s", result.provider_name, output_path)
            return output_path
    except ProviderAuthError as e:
        logger.error("Provider authentication failed — check API keys: %s", e)
    except ProviderRateLimitError as e:
        logger.error("Provider rate limit exceeded — retry later: %s", e)
    except Exception as e:
        logger.warning("Provider search for target ASS failed: %s", e)

    return None


def _search_providers_for_source_sub(mkv_path, context=None):
    """Search subtitle providers for a source language subtitle.

    Tries ASS first, falls back to SRT.

    Returns:
        tuple: (path, format, score) or (None, None, 0)
    """
    try:
        from providers import get_provider_manager
        from providers.base import (
            ProviderAuthError,
            ProviderRateLimitError,
            SubtitleFormat,
        )

        settings = get_settings()
        manager = get_provider_manager()

        query = _build_video_query(mkv_path, context)
        query.languages = [settings.source_language]

        # Try ASS first
        result = manager.search_and_download_best(query, format_filter=SubtitleFormat.ASS)
        if result and result.content:
            base = os.path.splitext(mkv_path)[0]
            tmp_path = f"{base}.{settings.source_language}.ass"
            manager.save_subtitle(
                result,
                tmp_path,
                series_id=context.get("sonarr_series_id") if context else None,
            )
            logger.info(
                "Provider %s delivered source ASS: %s (score=%d)",
                result.provider_name,
                tmp_path,
                result.score,
            )
            return tmp_path, "ass", result.score

        # Fall back to any format (SRT most likely)
        result = manager.search_and_download_best(query)
        if result and result.content:
            base = os.path.splitext(mkv_path)[0]
            ext = result.format.value if result.format.value != "unknown" else "srt"
            tmp_path = f"{base}.{settings.source_language}.{ext}"
            manager.save_subtitle(
                result,
                tmp_path,
                series_id=context.get("sonarr_series_id") if context else None,
            )
            logger.info(
                "Provider %s delivered source %s: %s (score=%d)",
                result.provider_name,
                ext,
                tmp_path,
                result.score,
            )
            return tmp_path, ext, result.score
    except ProviderAuthError as e:
        logger.error("Provider authentication failed — check API keys: %s", e)
    except ProviderRateLimitError as e:
        logger.error("Provider rate limit exceeded — retry later: %s", e)
    except Exception as e:
        logger.warning("Provider search for source subtitle failed: %s", e)

    return None, None, 0
