"""Translator helper utilities — small functions with no intra-package dependencies."""

import logging
import os
import shutil

from config import get_settings

logger = logging.getLogger(__name__)

MIN_FREE_SPACE_MB = 100

# Common English words that indicate a subtitle was not actually translated
ENGLISH_MARKER_WORDS = {
    "the",
    "and",
    "that",
    "have",
    "for",
    "not",
    "with",
    "you",
    "this",
    "but",
    "from",
    "they",
    "will",
    "what",
    "about",
}


def _get_whisper_fallback_min_score() -> int:
    """Read whisper_fallback_min_score from config_entries.

    Returns:
        int 0-100. 0 means disabled (only fall back on no results at all).
    """
    try:
        from db.config import get_config_entry

        value = get_config_entry("whisper_fallback_min_score")
        if value is None:
            return 0  # disabled by default
        n = int(value)
        return max(0, min(100, n))
    except Exception:
        return 0


def _is_whisper_enabled() -> bool:
    """Check if Whisper transcription is enabled in config."""
    try:
        from db.config import get_config_entry

        enabled = get_config_entry("whisper_enabled")
        return enabled is not None and enabled.lower() in ("true", "1", "yes")
    except Exception:
        return False


def _submit_whisper_job(mkv_path: str, arr_context: dict = None):
    """Submit a Whisper transcription job for the given media file.

    Case D is async: submits to the Whisper queue and returns a
    'whisper_pending' status. The queue worker handles transcription and
    can re-enter the translation pipeline after completion.

    Returns:
        Dict with status='whisper_pending' and job_id, or None if Whisper
        is not available.
    """
    try:
        import uuid

        from extensions import socketio
        from routes.whisper import _get_queue
        from whisper import get_whisper_manager

        manager = get_whisper_manager()
        backend = manager.get_active_backend()
        if not backend:
            logger.info("Case D: No Whisper backend configured")
            return None

        # Determine source language from config
        settings = get_settings()
        source_lang = settings.source_language or "ja"

        job_id = uuid.uuid4().hex
        queue = _get_queue()
        queue.submit(
            job_id=job_id,
            file_path=mkv_path,
            language=source_lang,
            source_language=source_lang,
            whisper_manager=manager,
            socketio=socketio,
        )

        logger.info(
            "Case D: Submitted Whisper job %s for %s (language: %s)",
            job_id,
            os.path.basename(mkv_path),
            source_lang,
        )

        return {
            "success": True,
            "status": "whisper_pending",
            "whisper_job_id": job_id,
            "message": f"Whisper transcription queued (job {job_id[:8]}...)",
            "stats": {"source": "whisper", "whisper_job_id": job_id},
        }
    except Exception as e:
        logger.warning("Case D: Failed to submit Whisper job: %s", e)
        return None


def _extract_series_id(arr_context):
    """Extract Sonarr series_id from arr_context.

    Returns:
        int or None: Series ID if found, None otherwise
    """
    if not arr_context:
        return None

    # Try direct series_id field
    if arr_context.get("sonarr_series_id"):
        return arr_context["sonarr_series_id"]

    # Try series.id (from webhook)
    series = arr_context.get("series", {})
    if isinstance(series, dict) and series.get("id"):
        return series["id"]

    return None


def _resolve_backend_for_context(arr_context, target_language):
    """Resolve translation backend and fallback chain from language profile.

    Uses the arr_context to determine which series/movie profile to use.
    Falls back to the default profile if no specific assignment exists.

    Args:
        arr_context: Dict with sonarr_series_id or radarr_movie_id (or None)
        target_language: Target language code (unused currently, for future per-lang backends)

    Returns:
        tuple: (translation_backend: str, fallback_chain: list[str])
    """
    from db.profiles import get_default_profile, get_movie_profile, get_series_profile

    profile = None
    if arr_context:
        if arr_context.get("sonarr_series_id"):
            profile = get_series_profile(arr_context["sonarr_series_id"])
        elif arr_context.get("radarr_movie_id"):
            profile = get_movie_profile(arr_context["radarr_movie_id"])

    if not profile:
        profile = get_default_profile()

    backend = profile.get("translation_backend", "ollama")
    chain = profile.get("fallback_chain", ["ollama"])

    # Ensure primary backend is first in chain
    if backend not in chain:
        chain = [backend] + list(chain)

    return (backend, chain)


def _get_cache_config() -> tuple:
    """Read translation memory config from config_entries DB.

    Returns:
        (enabled: bool, similarity_threshold: float)
    """
    try:
        from db.config import get_config_entry

        enabled_val = get_config_entry("translation_memory_enabled")
        enabled = enabled_val is None or enabled_val.lower() not in ("false", "0", "no")
        threshold_val = get_config_entry("translation_memory_similarity_threshold")
        if threshold_val is not None:
            threshold = float(threshold_val)
            threshold = max(0.0, min(1.0, threshold))
        else:
            threshold = 1.0
        return enabled, threshold
    except Exception:
        return True, 1.0


def _get_quality_config():
    """Read translation quality scoring config from config_entries DB.

    Returns:
        (enabled: bool, threshold: int, max_retries: int)
        enabled -- whether LLM quality evaluation is active
        threshold -- minimum acceptable score (0-100); lines below this are retried
        max_retries -- maximum retry attempts per low-quality line
    """
    try:
        from db.config import get_config_entry

        enabled_val = get_config_entry("translation_quality_enabled")
        enabled = enabled_val is None or enabled_val.lower() not in ("false", "0", "no")
        threshold_val = get_config_entry("translation_quality_threshold")
        threshold = int(threshold_val) if threshold_val is not None else 50
        threshold = max(0, min(100, threshold))
        retries_val = get_config_entry("translation_quality_max_retries")
        max_retries = int(retries_val) if retries_val is not None else 2
        max_retries = max(0, min(5, max_retries))
        return enabled, threshold, max_retries
    except Exception:
        return True, 50, 2


def check_disk_space(path):
    """Check if there's enough free disk space."""
    stat = shutil.disk_usage(os.path.dirname(path))
    free_mb = stat.free / (1024 * 1024)
    if free_mb < MIN_FREE_SPACE_MB:
        raise RuntimeError(
            f"Insufficient disk space: {free_mb:.0f}MB free, need at least {MIN_FREE_SPACE_MB}MB"
        )


def find_external_source_sub(mkv_path):
    """Find an external source language subtitle file next to the MKV."""
    settings = get_settings()
    base = os.path.splitext(mkv_path)[0]

    # Check both ASS and SRT patterns for the source language
    all_patterns = settings.get_source_patterns("srt") + settings.get_source_patterns("ass")
    for pattern in all_patterns:
        path = base + pattern
        if os.path.exists(path):
            logger.info("Found external source subtitle: %s", path)
            return path
    return None


def _skip_result(reason, output_path=None):
    """Create a skip result dict."""
    return {
        "success": True,
        "output_path": output_path,
        "stats": {"skipped": True, "reason": reason},
        "error": None,
    }


def _fail_result(error):
    """Create a failure result dict."""
    return {
        "success": False,
        "output_path": None,
        "stats": {},
        "error": error,
    }
