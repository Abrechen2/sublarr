"""Wanted search processing — item processing, downloading, and result helpers."""

import contextlib
import logging
import os

from config import get_settings
from db.jobs import create_job, record_stat, update_job
from db.library import record_upgrade
from db.providers import record_subtitle_download
from db.wanted import get_wanted_item, update_wanted_search, update_wanted_status
from error_handler import DuplicateSubtitleError
from providers import get_provider_manager
from providers.base import SubtitleFormat
from translator import get_forced_output_path
from upgrade_scorer import should_upgrade
from wanted_search.metadata import _set_adaptive_retry_after, build_query_from_wanted

logger = logging.getLogger(__name__)


def _try_auto_sync(subtitle_path: str, video_path: str, settings) -> None:
    """Enqueue a sync job if auto_sync_after_download is enabled.

    Only ffsubsync is supported for auto-sync (alass requires a reference track).
    Errors are logged but never propagated — sync is best-effort.
    """
    if not getattr(settings, "auto_sync_after_download", False):
        return
    engine = getattr(settings, "auto_sync_engine", "ffsubsync")
    if engine != "ffsubsync":
        logger.warning(
            "Auto-sync: alass requires a reference track — skipping auto-sync for %s", subtitle_path
        )
        return
    try:
        from services.video_sync import SyncUnavailableError, sync_with_ffsubsync

        logger.info("Auto-sync: starting ffsubsync for %s against %s", subtitle_path, video_path)
        sync_with_ffsubsync(subtitle_path, video_path)
        logger.info("Auto-sync: complete for %s", subtitle_path)
    except SyncUnavailableError as e:
        logger.warning("Auto-sync skipped: %s", e)
    except Exception as e:
        logger.error("Auto-sync failed for %s: %s", subtitle_path, e)


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
                    manager.save_subtitle(
                        result, output_path, series_id=item.get("sonarr_series_id")
                    )
                    record_subtitle_download(
                        result.provider_name,
                        result.subtitle_id,
                        item_lang,
                        result.format.value if result.format.value != "unknown" else fmt.value,
                        file_path,
                        result.score,
                    )
                    logger.info(
                        "Wanted %d: Forced subtitle downloaded from %s, skipping translation",
                        item_id,
                        result.provider_name,
                    )
                    update_wanted_status(item_id, "found")
                    return {
                        "wanted_id": item_id,
                        "status": "found",
                        "output_path": output_path,
                        "provider": result.provider_name,
                        "forced": True,
                    }
                except DuplicateSubtitleError as dup_err:
                    logger.info(
                        "Wanted %d: Duplicate forced subtitle skipped, already at %s",
                        item_id,
                        dup_err.existing_path,
                    )
                    update_wanted_status(item_id, "found")
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
                    manager.save_subtitle(
                        result, output_path, series_id=item.get("sonarr_series_id")
                    )
                    record_subtitle_download(
                        result.provider_name,
                        result.subtitle_id,
                        source_lang,
                        result.format.value if result.format.value != "unknown" else fmt.value,
                        file_path,
                        result.score,
                    )
                    logger.info(
                        "Wanted %d: Forced subtitle (source lang) downloaded from %s, skipping translation",
                        item_id,
                        result.provider_name,
                    )
                    update_wanted_status(item_id, "found")
                    return {
                        "wanted_id": item_id,
                        "status": "found",
                        "output_path": output_path,
                        "provider": result.provider_name,
                        "forced": True,
                    }
                except DuplicateSubtitleError as dup_err:
                    logger.info(
                        "Wanted %d: Duplicate forced subtitle (source) skipped, already at %s",
                        item_id,
                        dup_err.existing_path,
                    )
                    update_wanted_status(item_id, "found")
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


def process_wanted_item(item_id: int) -> dict:
    """Full pipeline for one item: search -> download best -> translate.

    Returns:
        dict: {wanted_id, status, output_path, provider, error}
    """
    item = get_wanted_item(item_id)
    if not item:
        return {"wanted_id": item_id, "status": "error", "error": "Item not found"}

    settings = get_settings()
    item_lang = item.get("target_language") or settings.target_language

    # Check max search attempts
    if item["search_count"] >= settings.wanted_max_search_attempts:
        update_wanted_status(item_id, "failed", error="Max search attempts reached")
        return {
            "wanted_id": item_id,
            "status": "failed",
            "error": "Max search attempts reached",
        }

    update_wanted_status(item_id, "searching")
    update_wanted_search(item_id)

    file_path = item["file_path"]
    if not os.path.exists(file_path):
        update_wanted_status(item_id, "failed", error="File not found on disk")
        return {
            "wanted_id": item_id,
            "status": "failed",
            "error": f"File not found: {file_path}",
        }

    is_upgrade = bool(item.get("upgrade_candidate"))
    current_score = item.get("current_score", 0)
    subtitle_type = item.get("subtitle_type", "full")
    manager = get_provider_manager()
    auto_translate = getattr(settings, "wanted_auto_translate", True)

    # Forced subtitle handling: download-only, no translation
    if subtitle_type == "forced":
        return _process_forced_wanted_item(item, item_id, item_lang, manager)

    # Track whether any ASS content was found in Steps 1+2 (for SRT early-exit, Phase 2)
    _ass_had_results = False

    # Step 1: Try to find target language ASS directly from providers (Priority 1)
    query = build_query_from_wanted(item)
    query.languages = [item_lang]

    try:
        result = manager.search_and_download_best(query, format_filter=SubtitleFormat.ASS)
        if result and result.content:
            _ass_had_results = True
            new_score = result.score

            # For upgrade candidates, check if the new sub is actually better
            if is_upgrade and current_score > 0:
                from translator import get_output_path_for_lang

                existing_srt = get_output_path_for_lang(file_path, "srt", item_lang)
                do_upgrade, reason = should_upgrade(
                    "srt",
                    current_score,
                    "ass",
                    new_score,
                    upgrade_prefer_ass=settings.upgrade_prefer_ass,
                    upgrade_min_score_delta=settings.upgrade_min_score_delta,
                    upgrade_window_days=settings.upgrade_window_days,
                    existing_file_path=existing_srt,
                )
                if not do_upgrade:
                    logger.info("Wanted %d: Upgrade rejected — %s", item_id, reason)
                    update_wanted_status(item_id, "wanted")
                    return {
                        "wanted_id": item_id,
                        "status": "skipped",
                        "reason": reason,
                    }
                logger.info("Wanted %d: Upgrade approved — %s", item_id, reason)

            from translator import get_output_path_for_lang

            output_path = get_output_path_for_lang(file_path, "ass", item_lang)

            # If upgrading from SRT, remove old SRT file
            if is_upgrade:
                old_srt = get_output_path_for_lang(file_path, "srt", item_lang)
                if os.path.exists(old_srt):
                    os.remove(old_srt)
                    logger.info("Wanted %d: Removed old SRT: %s", item_id, old_srt)
                record_upgrade(
                    file_path=file_path,
                    old_format="srt",
                    old_score=current_score,
                    new_format="ass",
                    new_score=new_score,
                    provider_name=result.provider_name,
                    upgrade_reason=f"SRT->ASS via {result.provider_name}",
                )

            try:
                manager.save_subtitle(result, output_path, series_id=item.get("sonarr_series_id"))
                record_subtitle_download(
                    result.provider_name,
                    result.subtitle_id,
                    item_lang,
                    result.format.value if result.format.value != "unknown" else "ass",
                    file_path,
                    result.score,
                )
                logger.info(
                    "Wanted %d: Provider %s delivered target ASS directly",
                    item_id,
                    result.provider_name,
                )
                from nfo_export import maybe_write_nfo

                maybe_write_nfo(
                    output_path,
                    {
                        "provider": result.provider_name,
                        "source_language": getattr(result, "language", ""),
                        "target_language": item_lang,
                        "score": result.score,
                    },
                )
                update_wanted_status(item_id, "found")
                return {
                    "wanted_id": item_id,
                    "status": "found",
                    "output_path": output_path,
                    "provider": result.provider_name,
                    "upgraded": is_upgrade,
                }
            except DuplicateSubtitleError as dup_err:
                logger.info(
                    "Wanted %d: Duplicate subtitle skipped, already at %s",
                    item_id,
                    dup_err.existing_path,
                )
                update_wanted_status(item_id, "found")
                return {
                    "wanted_id": item_id,
                    "status": "duplicate_skipped",
                    "output_path": dup_err.existing_path,
                    "provider": result.provider_name,
                    "upgraded": False,
                }
            except (OSError, RuntimeError) as save_error:
                logger.error(
                    "Wanted %d: Failed to save subtitle from %s: %s",
                    item_id,
                    result.provider_name,
                    save_error,
                )
                # Fall through to next step
    except Exception as e:
        logger.warning("Wanted %d: Direct target ASS search failed: %s", item_id, e, exc_info=True)

    # Step 2: Try to find source language ASS for translation (Priority 2)
    if auto_translate:
        source_query = build_query_from_wanted(item)
        source_query.languages = [settings.source_language]
        try:
            result = manager.search_and_download_best(
                source_query, format_filter=SubtitleFormat.ASS
            )
            if result and result.content:
                _ass_had_results = True
                # Download source ASS and translate it
                from translator import _translate_external_ass, get_output_path_for_lang

                base = os.path.splitext(file_path)[0]
                tmp_source_path = f"{base}.{settings.source_language}.ass"
                try:
                    # Use the returned path — save_subtitle may adjust the extension
                    # (e.g. if the downloaded file turns out to be SRT, not ASS)
                    actual_source_path = manager.save_subtitle(
                        result, tmp_source_path, series_id=item.get("sonarr_series_id")
                    )
                    record_subtitle_download(
                        result.provider_name,
                        result.subtitle_id,
                        settings.source_language,
                        result.format.value if result.format.value != "unknown" else "ass",
                        file_path,
                        result.score,
                    )
                except DuplicateSubtitleError as dup_err:
                    logger.info(
                        "Wanted %d: Duplicate source ASS skipped, using existing %s",
                        item_id,
                        dup_err.existing_path,
                    )
                    actual_source_path = dup_err.existing_path
                except (OSError, RuntimeError) as save_error:
                    logger.error(
                        "Wanted %d: Failed to save source ASS from %s: %s",
                        item_id,
                        result.provider_name,
                        save_error,
                    )
                    raise  # skip to next step

                # Build arr_context for glossary lookup
                arr_context = {}
                if item.get("sonarr_series_id"):
                    arr_context["sonarr_series_id"] = item["sonarr_series_id"]
                if item.get("sonarr_episode_id"):
                    arr_context["sonarr_episode_id"] = item["sonarr_episode_id"]
                if item.get("radarr_movie_id"):
                    arr_context["radarr_movie_id"] = item["radarr_movie_id"]

                job = create_job(
                    file_path, force=False, arr_context=arr_context if arr_context else None
                )
                update_job(job["id"], "running")
                try:
                    translate_result = _translate_external_ass(
                        file_path,
                        actual_source_path,
                        target_language=item_lang,
                        target_language_name=settings.target_language_name,
                        arr_context=arr_context if arr_context else None,
                    )
                except Exception as trans_error:
                    logger.error(
                        "Wanted %d: Translation failed for source ASS: %s",
                        item_id,
                        trans_error,
                        exc_info=True,
                    )
                    update_job(job["id"], "failed", error=str(trans_error))
                    record_stat(success=False)
                    try:
                        if os.path.exists(actual_source_path):
                            os.remove(actual_source_path)
                    except OSError as e:
                        logger.debug("Temp file cleanup failed: %s", e)
                    raise  # skip to next step

                # Clean up temporary source file
                try:
                    if os.path.exists(actual_source_path):
                        os.remove(actual_source_path)
                except OSError as e:
                    logger.debug("Temp file cleanup failed: %s", e)

                if translate_result and translate_result.get("success"):
                    update_job(
                        job["id"],
                        "completed",
                        result=translate_result,
                        error=translate_result.get("error"),
                    )
                    s = translate_result.get("stats", {})
                    record_stat(
                        success=True,
                        skipped=s.get("skipped", False),
                        fmt=s.get("format", ""),
                        source=s.get("source", ""),
                    )
                    logger.info(
                        "Wanted %d: Translated source ASS from provider %s",
                        item_id,
                        result.provider_name,
                    )
                    update_wanted_status(item_id, "found")
                    return {
                        "wanted_id": item_id,
                        "status": "found",
                        "output_path": translate_result.get("output_path"),
                        "provider": f"{result.provider_name} (translated)",
                    }
                else:
                    update_job(
                        job["id"],
                        "failed",
                        result=translate_result,
                        error=translate_result.get("error")
                        if translate_result
                        else "Translation failed",
                    )
                    record_stat(success=False)
        except Exception as e:
            logger.warning(
                "Wanted %d: Source ASS search/translation failed: %s", item_id, e, exc_info=True
            )
    else:
        logger.debug("Wanted %d: auto_translate disabled, skipping source ASS translation", item_id)

    # Early exit: skip SRT steps if no ASS was found in Steps 1+2 (providers likely have nothing)
    _skip_srt = getattr(settings, "wanted_skip_srt_on_no_ass", True) and not _ass_had_results
    if _skip_srt:
        logger.debug("Wanted %d: No ASS found in Steps 1+2, skipping SRT steps", item_id)

    # Step 3: Try to find target language SRT directly (Priority 3)
    if not _skip_srt:
        try:
            result = manager.search_and_download_best(query, format_filter=SubtitleFormat.SRT)
            if result and result.content:
                from translator import get_output_path_for_lang

                output_path = get_output_path_for_lang(file_path, "srt", item_lang)
                try:
                    manager.save_subtitle(
                        result, output_path, series_id=item.get("sonarr_series_id")
                    )
                    record_subtitle_download(
                        result.provider_name,
                        result.subtitle_id,
                        item_lang,
                        result.format.value if result.format.value != "unknown" else "srt",
                        file_path,
                        result.score,
                    )
                    logger.info(
                        "Wanted %d: Provider %s delivered target SRT directly",
                        item_id,
                        result.provider_name,
                    )
                    from nfo_export import maybe_write_nfo

                    maybe_write_nfo(
                        output_path,
                        {
                            "provider": result.provider_name,
                            "source_language": getattr(result, "language", ""),
                            "target_language": item_lang,
                            "score": result.score,
                        },
                    )
                    update_wanted_status(item_id, "found")
                    return {
                        "wanted_id": item_id,
                        "status": "found",
                        "output_path": output_path,
                        "provider": result.provider_name,
                    }
                except DuplicateSubtitleError as dup_err:
                    logger.info(
                        "Wanted %d: Duplicate target SRT skipped, already at %s",
                        item_id,
                        dup_err.existing_path,
                    )
                    update_wanted_status(item_id, "found")
                    return {
                        "wanted_id": item_id,
                        "status": "duplicate_skipped",
                        "output_path": dup_err.existing_path,
                        "provider": result.provider_name,
                    }
                except (OSError, RuntimeError) as save_error:
                    logger.error(
                        "Wanted %d: Failed to save target SRT from %s: %s",
                        item_id,
                        result.provider_name,
                        save_error,
                    )
                    # Fall through to next step
        except Exception as e:
            logger.warning(
                "Wanted %d: Direct target SRT search failed: %s", item_id, e, exc_info=True
            )

    # Step 4: Try to find source language SRT for translation (Priority 4)
    if not _skip_srt and auto_translate:
        try:
            result = manager.search_and_download_best(
                source_query, format_filter=SubtitleFormat.SRT
            )
            if result and result.content:
                # Download source SRT and translate it
                from translator import get_output_path_for_lang, translate_srt_from_file

                base = os.path.splitext(file_path)[0]
                tmp_source_path = f"{base}.{settings.source_language}.srt"
                try:
                    actual_source_path = manager.save_subtitle(
                        result, tmp_source_path, series_id=item.get("sonarr_series_id")
                    )
                    record_subtitle_download(
                        result.provider_name,
                        result.subtitle_id,
                        settings.source_language,
                        result.format.value if result.format.value != "unknown" else "srt",
                        file_path,
                        result.score,
                    )
                except DuplicateSubtitleError as dup_err:
                    logger.info(
                        "Wanted %d: Duplicate source SRT skipped, using existing %s",
                        item_id,
                        dup_err.existing_path,
                    )
                    actual_source_path = dup_err.existing_path
                except (OSError, RuntimeError) as save_error:
                    logger.error(
                        "Wanted %d: Failed to save source SRT from %s: %s",
                        item_id,
                        result.provider_name,
                        save_error,
                    )
                    raise  # skip to next step

                # Build arr_context for glossary lookup
                arr_context = {}
                if item.get("sonarr_series_id"):
                    arr_context["sonarr_series_id"] = item["sonarr_series_id"]
                if item.get("sonarr_episode_id"):
                    arr_context["sonarr_episode_id"] = item["sonarr_episode_id"]
                if item.get("radarr_movie_id"):
                    arr_context["radarr_movie_id"] = item["radarr_movie_id"]

                job = create_job(
                    file_path, force=False, arr_context=arr_context if arr_context else None
                )
                update_job(job["id"], "running")
                try:
                    translate_result = translate_srt_from_file(
                        file_path,
                        actual_source_path,
                        source="provider_source_srt",
                        target_language=item_lang,
                        arr_context=arr_context if arr_context else None,
                    )
                except Exception as trans_error:
                    logger.error(
                        "Wanted %d: Translation failed for source SRT: %s",
                        item_id,
                        trans_error,
                        exc_info=True,
                    )
                    update_job(job["id"], "failed", error=str(trans_error))
                    record_stat(success=False)
                    try:
                        if os.path.exists(actual_source_path):
                            os.remove(actual_source_path)
                    except OSError as e:
                        logger.debug("Temp file cleanup failed: %s", e)
                    raise  # skip to next step

                # Clean up temporary source file
                try:
                    if os.path.exists(actual_source_path):
                        os.remove(actual_source_path)
                except OSError as e:
                    logger.debug("Temp file cleanup failed: %s", e)

                if translate_result and translate_result.get("success"):
                    update_job(
                        job["id"],
                        "completed",
                        result=translate_result,
                        error=translate_result.get("error"),
                    )
                    s = translate_result.get("stats", {})
                    record_stat(
                        success=True,
                        skipped=s.get("skipped", False),
                        fmt=s.get("format", ""),
                        source=s.get("source", ""),
                    )
                    logger.info(
                        "Wanted %d: Translated source SRT from provider %s",
                        item_id,
                        result.provider_name,
                    )
                    update_wanted_status(item_id, "found")
                    return {
                        "wanted_id": item_id,
                        "status": "found",
                        "output_path": translate_result.get("output_path"),
                        "provider": f"{result.provider_name} (translated)",
                    }
                else:
                    update_job(
                        job["id"],
                        "failed",
                        result=translate_result,
                        error=translate_result.get("error")
                        if translate_result
                        else "Translation failed",
                    )
                    record_stat(success=False)
        except Exception as e:
            logger.warning(
                "Wanted %d: Source SRT search/translation failed: %s", item_id, e, exc_info=True
            )

    # Step 5: Fall back to translate_file() which handles embedded subtitles (B1/C1-C4)
    if not auto_translate:
        logger.debug(
            "Wanted %d: auto_translate disabled, no subtitle found without translation", item_id
        )
        update_wanted_status(item_id, "wanted")
        return {
            "wanted_id": item_id,
            "status": "not_found",
            "reason": "No subtitle found; translation disabled",
        }
    try:
        from translator import translate_file

        # Build arr_context from wanted_item for glossary lookup
        arr_context = {}
        if item.get("sonarr_series_id"):
            arr_context["sonarr_series_id"] = item["sonarr_series_id"]
        if item.get("sonarr_episode_id"):
            arr_context["sonarr_episode_id"] = item["sonarr_episode_id"]
        if item.get("radarr_movie_id"):
            arr_context["radarr_movie_id"] = item["radarr_movie_id"]
        job = create_job(file_path, force=False, arr_context=arr_context if arr_context else None)
        update_job(job["id"], "running")
        translate_result = translate_file(
            file_path, target_language=item_lang, arr_context=arr_context if arr_context else None
        )

        if translate_result["success"]:
            update_job(
                job["id"], "completed", result=translate_result, error=translate_result.get("error")
            )
            s = translate_result.get("stats", {})
            record_stat(
                success=True,
                skipped=s.get("skipped", False),
                fmt=s.get("format", ""),
                source=s.get("source", ""),
            )
            if translate_result["stats"].get("skipped"):
                update_wanted_status(item_id, "found")
                return {
                    "wanted_id": item_id,
                    "status": "found",
                    "output_path": translate_result.get("output_path"),
                    "provider": "translate_pipeline",
                }
            else:
                update_wanted_status(item_id, "found")
                return {
                    "wanted_id": item_id,
                    "status": "found",
                    "output_path": translate_result.get("output_path"),
                    "provider": translate_result.get("stats", {}).get("source", "unknown"),
                }
        else:
            error = translate_result.get("error", "Translation failed")
            update_job(job["id"], "failed", result=translate_result, error=error)
            record_stat(success=False)
            update_wanted_status(item_id, "failed", error=error)
            _set_adaptive_retry_after(item_id, item["search_count"] + 1, settings)
            return {
                "wanted_id": item_id,
                "status": "failed",
                "error": error,
            }
    except Exception as e:
        error = str(e)
        try:
            update_job(job["id"], "failed", error=error)
        except Exception as e:
            logger.debug(
                "Failed to update job to failed status (job may not have been created): %s", e
            )
        with contextlib.suppress(Exception):
            record_stat(success=False)
        logger.exception("Wanted %d: Process failed: %s", item_id, error)
        update_wanted_status(item_id, "failed", error=error)
        _set_adaptive_retry_after(item_id, item["search_count"] + 1, settings)
        return {
            "wanted_id": item_id,
            "status": "failed",
            "error": error,
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
        results = manager.search(query)
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
            record_subtitle_download(
                provider_name,
                subtitle_id,
                language,
                fmt_ext,
                file_path,
                target_result.score,
            )
        except DuplicateSubtitleError as dup_err:
            actual_source_path = dup_err.existing_path
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
            logger.error(
                "Translation failed in download_specific for wanted %d: %s",
                item_id,
                e,
                exc_info=True,
            )
            update_job(job["id"], "failed", error=str(e))
            record_stat(success=False)
            try:
                if os.path.exists(actual_source_path):
                    os.remove(actual_source_path)
            except OSError as e:
                logger.debug("Temp file cleanup failed: %s", e)
            return {"success": False, "error": f"Translation failed: {e}"}

        try:
            if os.path.exists(actual_source_path):
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
        update_wanted_status(item_id, "found")
        out = translate_result.get("output_path")
        if out:
            _try_auto_sync(out, file_path, settings)
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
        )
    except DuplicateSubtitleError as dup_err:
        update_wanted_status(item_id, "found")
        _try_auto_sync(dup_err.existing_path, file_path, settings)
        return {
            "success": True,
            "path": dup_err.existing_path,
            "format": fmt_ext,
            "translated": False,
            "duplicate_skipped": True,
        }
    except (OSError, RuntimeError) as e:
        return {"success": False, "error": f"Failed to save subtitle: {e}"}

    update_wanted_status(item_id, "found")
    _try_auto_sync(actual_path, file_path, settings)
    return {
        "success": True,
        "path": actual_path,
        "format": fmt_ext,
        "translated": False,
    }
