"""Post-processing helpers for wanted search results.

Extracted from wanted_search/process.py — contains helpers that run
after a subtitle is downloaded: auto-sync, forced-subtitle handling,
and interactive download of specific provider results.
"""

import logging
import os

from config import get_settings
from db.jobs import create_job, record_stat, update_job
from db.providers import record_subtitle_download
from db.wanted import delete_wanted_item, get_wanted_item, update_wanted_status
from error_handler import DuplicateSubtitleError
from providers import get_provider_manager
from providers.base import SubtitleFormat
from translator import get_forced_output_path
from wanted_search.metadata import build_query_from_wanted

logger = logging.getLogger(__name__)


def _try_auto_sync(
    subtitle_path: str,
    video_path: str,
    settings,
    *,
    item_id: int,
    target_language: str,
) -> None:
    """Queue a sync job if auto_sync_after_download is enabled.

    Only ffsubsync is supported for auto-sync (alass requires a reference track).
    Errors are logged but never propagated — sync is best-effort.

    This used to run ffsubsync right here, on the search thread. It cannot:
    `sync_with_ffsubsync` caps a single run at 600s and cannot be interrupted
    once started, so one item could hold a `wanted_search` tick for ten
    minutes — against a cancel grace sized for the "6-143s" this comment used
    to claim. Three consecutive prod sweeps ended `timeout_abandoned` on it
    (2026-08-15/16). The drain worker owns the expensive part now; the search
    only records that it is due, which is the same move that took sidecar
    translation off this path in 1.11.3.

    Both paths are written to the row. The video cannot be resolved from the
    wanted item later: two of the four call sites delete the item on the very
    next line.
    """
    if not getattr(settings, "auto_sync_after_download", False):
        return
    engine = getattr(settings, "auto_sync_engine", "ffsubsync")
    if engine != "ffsubsync":
        logger.warning(
            "Auto-sync: alass requires a reference track — skipping auto-sync for %s", subtitle_path
        )
        return
    if not subtitle_path or not os.path.isfile(subtitle_path):
        logger.warning("Auto-sync skipped: subtitle path does not exist on disk: %s", subtitle_path)
        return
    if not os.path.isfile(video_path):
        logger.warning("Auto-sync skipped: video path does not exist on disk: %s", video_path)
        return
    # No abort check here any more. Enqueueing is a single INSERT, so there is
    # nothing left worth refusing to start — and refusing would silently drop
    # the sync instead of deferring it, which is what the old inline version
    # had to do.
    try:
        from db.models.core import SubtitleAutomationQueueEntry
        from db.repositories.subtitle_automation_queue import (
            SubtitleAutomationQueueRepository,
        )

        SubtitleAutomationQueueRepository().enqueue(
            wanted_item_id=item_id,
            file_path=subtitle_path,
            video_path=video_path,
            target_language=target_language,
            task_type=SubtitleAutomationQueueEntry.TASK_AUTO_SYNC,
        )
        logger.info("Auto-sync: queued %s against %s", subtitle_path, video_path)
    except Exception as e:
        # A queue that is unavailable must not cost us the download that just
        # succeeded — the sidecar is already on disk and usable, only its
        # timing correction is lost.
        logger.error("Auto-sync could not be queued for %s: %s", subtitle_path, e)


def _try_auto_combine(item, video_path: str) -> None:
    """Fire automatic per-profile combine after a subtitle landed for a video.

    Best-effort — ``maybe_auto_combine`` never raises, but keep the call guarded
    so a lazy-import hiccup can never break the download pipeline.
    """
    try:
        from services.combine_service import maybe_auto_combine

        maybe_auto_combine(video_path, item=item)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("auto-combine hook failed for %s: %s", video_path, exc)


def _process_forced_wanted_item(item, item_id, item_lang, manager):
    """Process a forced wanted item: search with forced_only, download, skip translation.

    Forced subtitles are download-only (no translation per research recommendation).
    Saves to the forced output path (.lang.forced.ext).

    Returns:
        dict: {wanted_id, status, output_path, provider, error}
    """
    file_path = item["file_path"]

    # Build forced query
    query = build_query_from_wanted(item)
    query.languages = [item_lang]
    query.forced_only = True

    # Try target language forced ASS first, then forced SRT
    for fmt in (SubtitleFormat.ASS, SubtitleFormat.SRT):
        try:
            result = manager.search_and_download_best(query, format_filter=fmt)
            if result and result.content:
                ext = result.format.value if result.format != SubtitleFormat.UNKNOWN else fmt.value
                output_path = get_forced_output_path(file_path, fmt=ext, target_language=item_lang)
                try:
                    # save_subtitle may rewrite the extension when actual format
                    # differs from the requested one — always use the return.
                    saved_path = manager.save_subtitle(
                        result, output_path, series_id=item.get("sonarr_series_id")
                    )
                    record_subtitle_download(
                        result.provider_name,
                        result.subtitle_id,
                        item_lang,
                        result.format.value if result.format.value != "unknown" else fmt.value,
                        file_path,
                        result.score,
                        score_breakdown=result.score_breakdown,
                    )
                    logger.info(
                        "Wanted %d: Forced subtitle downloaded from %s, skipping translation",
                        item_id,
                        result.provider_name,
                    )
                    delete_wanted_item(item_id)
                    return {
                        "wanted_id": item_id,
                        "status": "found",
                        "output_path": saved_path,
                        "provider": result.provider_name,
                        "forced": True,
                    }
                except DuplicateSubtitleError as dup_err:
                    logger.info(
                        "Wanted %d: Duplicate forced subtitle skipped, already at %s",
                        item_id,
                        dup_err.existing_path,
                    )
                    delete_wanted_item(item_id)
                    return {
                        "wanted_id": item_id,
                        "status": "duplicate_skipped",
                        "output_path": dup_err.existing_path,
                        "provider": result.provider_name,
                        "forced": True,
                    }
                except (OSError, RuntimeError) as save_error:
                    logger.error(
                        "Wanted %d: Failed to save forced subtitle from %s: %s",
                        item_id,
                        result.provider_name,
                        save_error,
                    )
                    # Try next format
                    continue
        except Exception as e:
            logger.warning(
                "Wanted %d: Forced %s search failed: %s", item_id, fmt.value, e, exc_info=True
            )

    # Also try source language forced subtitles (download-only, no translation)
    settings = get_settings()
    source_lang = settings.source_language
    source_query = build_query_from_wanted(item)
    source_query.languages = [source_lang]
    source_query.forced_only = True

    for fmt in (SubtitleFormat.ASS, SubtitleFormat.SRT):
        try:
            result = manager.search_and_download_best(source_query, format_filter=fmt)
            if result and result.content:
                ext = result.format.value if result.format != SubtitleFormat.UNKNOWN else fmt.value
                output_path = get_forced_output_path(
                    file_path, fmt=ext, target_language=source_lang
                )
                try:
                    # save_subtitle may rewrite the extension when actual format
                    # differs from the requested one — always use the return.
                    saved_path = manager.save_subtitle(
                        result, output_path, series_id=item.get("sonarr_series_id")
                    )
                    record_subtitle_download(
                        result.provider_name,
                        result.subtitle_id,
                        source_lang,
                        result.format.value if result.format.value != "unknown" else fmt.value,
                        file_path,
                        result.score,
                        score_breakdown=result.score_breakdown,
                    )
                    logger.info(
                        "Wanted %d: Forced subtitle (source lang) downloaded from %s, skipping translation",
                        item_id,
                        result.provider_name,
                    )
                    delete_wanted_item(item_id)
                    return {
                        "wanted_id": item_id,
                        "status": "found",
                        "output_path": saved_path,
                        "provider": result.provider_name,
                        "forced": True,
                    }
                except DuplicateSubtitleError as dup_err:
                    logger.info(
                        "Wanted %d: Duplicate forced subtitle (source) skipped, already at %s",
                        item_id,
                        dup_err.existing_path,
                    )
                    delete_wanted_item(item_id)
                    return {
                        "wanted_id": item_id,
                        "status": "duplicate_skipped",
                        "output_path": dup_err.existing_path,
                        "provider": result.provider_name,
                        "forced": True,
                    }
                except (OSError, RuntimeError) as save_error:
                    logger.error(
                        "Wanted %d: Failed to save forced subtitle (source) from %s: %s",
                        item_id,
                        result.provider_name,
                        save_error,
                    )
                    # Try next format
                    continue
        except Exception as e:
            logger.warning(
                "Wanted %d: Forced source %s search failed: %s",
                item_id,
                fmt.value,
                e,
                exc_info=True,
            )

    # No forced subtitle found
    error = "No forced subtitle found from any provider"
    update_wanted_status(item_id, "failed", error=error)
    return {
        "wanted_id": item_id,
        "status": "failed",
        "error": error,
        "forced": True,
    }


def download_specific_for_item(
    item_id: int,
    provider_name: str,
    subtitle_id: str,
    language: str,
    translate: bool,
) -> dict:
    """Download a specific subtitle result and optionally translate it.

    Re-searches providers to find the specific result by provider_name + subtitle_id,
    downloads it, saves it to disk, and optionally runs the translation pipeline.
    When translate=True and language != item_lang, the subtitle is saved as a
    temporary source file and the translation pipeline is triggered.

    Returns:
        dict: {success, path, format, translated, error}
    """
    item = get_wanted_item(item_id)
    if not item:
        return {"success": False, "error": "Item not found"}

    settings = get_settings()
    item_lang = item.get("target_language") or settings.target_language
    manager = get_provider_manager()
    file_path = item["file_path"]

    # Build query for the given language and re-search to find the specific result
    query = build_query_from_wanted(item)
    query.languages = [language]

    try:
        # early_exit=False: must scan all results to find the exact subtitle_id
        results = manager.search(query, early_exit=False)
    except Exception as e:
        logger.error("Search failed during download_specific for wanted %d: %s", item_id, e)
        return {"success": False, "error": f"Search failed: {e}"}

    target_result = None
    for r in results:
        if r.provider_name == provider_name and r.subtitle_id == subtitle_id:
            target_result = r
            break

    if not target_result:
        return {"success": False, "error": f"Result not found: {provider_name}/{subtitle_id}"}

    content = manager.download(target_result)
    if content is None:
        return {"success": False, "error": "Download failed"}

    from translator import get_output_path_for_lang

    fmt_ext = target_result.format.value if target_result.format.value != "unknown" else "srt"

    # When translate=True and we have a non-target language: save + translate
    if translate and language != item_lang:
        base = os.path.splitext(file_path)[0]
        tmp_source_path = f"{base}.{language}.{fmt_ext}"

        try:
            actual_source_path = manager.save_subtitle(
                target_result, tmp_source_path, series_id=item.get("sonarr_series_id")
            )
            source_created_this_run = True
            record_subtitle_download(
                provider_name,
                subtitle_id,
                language,
                fmt_ext,
                file_path,
                target_result.score,
                score_breakdown=target_result.score_breakdown,
            )
        except DuplicateSubtitleError as dup_err:
            # existing_path is a PRE-EXISTING file on disk (often the user's
            # own sidecar) — it must never be deleted as "temp cleanup".
            actual_source_path = dup_err.existing_path
            source_created_this_run = False
        except (OSError, RuntimeError) as e:
            return {"success": False, "error": f"Failed to save subtitle: {e}"}

        arr_context = {}
        for key in ("sonarr_series_id", "sonarr_episode_id", "radarr_movie_id"):
            if item.get(key):
                arr_context[key] = item[key]

        # Create a translation job so it appears in Activity/Queue
        job = create_job(file_path, force=False, arr_context=arr_context or None)
        update_job(job["id"], "running")
        try:
            if actual_source_path.endswith(".ass"):
                from translator import _translate_external_ass

                translate_result = _translate_external_ass(
                    file_path,
                    actual_source_path,
                    target_language=item_lang,
                    target_language_name=settings.target_language_name,
                    arr_context=arr_context or None,
                )
            else:
                from translator import translate_srt_from_file

                translate_result = translate_srt_from_file(
                    file_path,
                    actual_source_path,
                    source="provider_interactive",
                    target_language=item_lang,
                    arr_context=arr_context or None,
                )
        except Exception as e:
            error_msg = str(e)
            logger.error(
                "Translation failed in download_specific for wanted %d: %s",
                item_id,
                error_msg,
                exc_info=True,
            )
            update_job(job["id"], "failed", error=error_msg)
            record_stat(success=False)
            try:
                if source_created_this_run and os.path.exists(actual_source_path):
                    os.remove(actual_source_path)
            except OSError as cleanup_err:
                logger.debug("Temp file cleanup failed: %s", cleanup_err)
            return {"success": False, "error": f"Translation failed: {error_msg}"}

        # Only delete the source file if this run created it — the duplicate
        # branch above rebinds actual_source_path to a pre-existing user file.
        try:
            if source_created_this_run and os.path.exists(actual_source_path):
                os.remove(actual_source_path)
        except OSError as e:
            logger.debug("Temp file cleanup failed: %s", e)

        if not translate_result or not translate_result.get("success"):
            err = (
                translate_result.get("error", "Translation failed")
                if translate_result
                else "Translation failed"
            )
            update_job(job["id"], "failed", result=translate_result, error=err)
            record_stat(success=False)
            return {"success": False, "error": err}

        status = "completed"
        update_job(job["id"], status, result=translate_result, error=translate_result.get("error"))
        s = translate_result.get("stats", {})
        record_stat(
            success=True,
            skipped=s.get("skipped", False),
            fmt=s.get("format", ""),
            source=s.get("source", ""),
        )
        out = translate_result.get("output_path")

        from services.mt_provisional import finalize_translation

        mt_fmt = "ass" if actual_source_path.endswith(".ass") else "srt"
        finalize_translation(item_id, item, out, item_lang, mt_fmt)

        if out:
            # `item_lang`, not `language`: what landed on disk here is the
            # translation, not the source that was downloaded to make it.
            _try_auto_sync(out, file_path, settings, item_id=item_id, target_language=item_lang)
        _try_auto_combine(item, file_path)
        return {
            "success": True,
            "path": out,
            "format": "ass",
            "translated": True,
        }

    # Download only (no translation)
    output_path = get_output_path_for_lang(file_path, fmt_ext, language)
    try:
        actual_path = manager.save_subtitle(
            target_result, output_path, series_id=item.get("sonarr_series_id")
        )
        record_subtitle_download(
            provider_name,
            subtitle_id,
            language,
            fmt_ext,
            file_path,
            target_result.score,
            score_breakdown=target_result.score_breakdown,
        )
    except DuplicateSubtitleError as dup_err:
        delete_wanted_item(item_id)
        _try_auto_sync(
            dup_err.existing_path,
            file_path,
            settings,
            item_id=item_id,
            target_language=language,
        )
        _try_auto_combine(item, file_path)
        return {
            "success": True,
            "path": dup_err.existing_path,
            "format": fmt_ext,
            "translated": False,
            "duplicate_skipped": True,
        }
    except (OSError, RuntimeError) as e:
        return {"success": False, "error": f"Failed to save subtitle: {e}"}

    delete_wanted_item(item_id)
    _try_auto_sync(actual_path, file_path, settings, item_id=item_id, target_language=language)
    _try_auto_combine(item, file_path)
    return {
        "success": True,
        "path": actual_path,
        "format": fmt_ext,
        "translated": False,
    }
