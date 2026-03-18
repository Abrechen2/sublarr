"""Job queue integration: scan_directory, submit_translation_job, notify integrations."""

import logging

from config import get_settings
from translator.output_paths import detect_existing_target

logger = logging.getLogger(__name__)


def _get_job_queue():
    """Get the app-level job queue backend, or None.

    Uses Flask's current_app to access the job_queue. Returns None if called
    outside Flask context or if job_queue is not configured. Never raises.
    """
    try:
        from flask import current_app

        return getattr(current_app, "job_queue", None)
    except (RuntimeError, ImportError):
        return None


def _notify_integrations(context, file_path=None):
    """Notify all configured media servers about new subtitle files.

    Args:
        context: arr_context dict with sonarr_series_id, sonarr_episode_id, or radarr_movie_id
        file_path: File path for media server item lookup
    """
    if not context or not file_path:
        return

    item_type = ""
    if context.get("sonarr_series_id") or context.get("sonarr_episode_id"):
        item_type = "episode"
    elif context.get("radarr_movie_id"):
        item_type = "movie"

    try:
        from mediaserver import get_media_server_manager

        manager = get_media_server_manager()
        results = manager.refresh_all(file_path, item_type)
        for r in results:
            if r.success:
                logger.info("Media server refresh: %s", r.message)
            else:
                logger.warning("Media server refresh failed: %s", r.message)
    except Exception as e:
        logger.warning("Media server notification failed: %s", e)


def _record_config_hash_for_result(result, file_path):
    """Record the translation config hash for a successful translation job.

    Includes backend_name in the hash so that switching backends triggers
    re-translation detection.
    """
    if not result or not result.get("success") or result.get("stats", {}).get("skipped"):
        return
    try:
        settings = get_settings()
        backend_name = result.get("stats", {}).get("backend_name", "ollama")
        config_hash = settings.get_translation_config_hash(backend_name=backend_name)
        from db.translation import record_translation_config

        # For non-Ollama backends, model is not relevant
        model_info = settings.ollama_model if backend_name == "ollama" else backend_name
        record_translation_config(
            config_hash=config_hash,
            ollama_model=model_info,
            prompt_template=settings.get_prompt_template()[:200],
            target_language=settings.target_language,
        )
        # Store hash in result stats for job record
        result.setdefault("stats", {})["config_hash"] = config_hash
    except Exception as e:
        logger.debug("Failed to record config hash: %s", e)


def scan_directory(directory, force=False):
    """Scan a directory for MKV files that need translation.

    Returns:
        list: List of dicts with file info including target_status
    """
    import os

    files = []
    for root, _dirs, filenames in os.walk(directory):
        for filename in sorted(filenames):
            if not filename.lower().endswith(".mkv"):
                continue
            mkv_path = os.path.join(root, filename)

            # Check external target subs only (no ffprobe — too slow for scan)
            target_status = detect_existing_target(mkv_path)

            if target_status == "ass" and not force:
                continue  # Goal achieved, skip

            files.append(
                {
                    "path": mkv_path,
                    "target_status": target_status,
                    "size_mb": os.path.getsize(mkv_path) / (1024 * 1024),
                }
            )
    return files


def submit_translation_job(
    file_path,
    force=False,
    arr_context=None,
    target_language=None,
    target_language_name=None,
    job_id=None,
):
    """Submit a translation job via the app job queue.

    When a job queue is available (RQ with Redis, or MemoryJobQueue), the
    translate_file function is enqueued for background execution. When no
    queue is available (outside Flask context, during testing), falls back
    to direct synchronous execution.

    The translate_file function itself is unchanged -- only the submission
    mechanism is abstracted. For RQ, translate_file must be importable by
    the worker process (it is a module-level function, not a closure).

    Args:
        file_path: Path to the media file.
        force: Force re-translation even if target exists.
        arr_context: Optional dict with sonarr_series_id or radarr_movie_id.
        target_language: Override target language.
        target_language_name: Override target language name.
        job_id: Optional custom job ID. Auto-generated if not provided.

    Returns:
        str: Job ID if enqueued via queue, or the result dict if executed directly.
    """
    from translator.core import translate_file

    queue = _get_job_queue()
    if queue:
        try:
            return queue.enqueue(
                translate_file,
                file_path,
                force=force,
                arr_context=arr_context,
                target_language=target_language,
                target_language_name=target_language_name,
                job_id=job_id,
            )
        except Exception as e:
            logger.warning("Job queue submission failed, executing directly: %s", e)

    # Fallback: direct synchronous execution
    return translate_file(
        file_path,
        force=force,
        arr_context=arr_context,
        target_language=target_language,
        target_language_name=target_language_name,
    )
