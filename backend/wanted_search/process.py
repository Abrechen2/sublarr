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
from upgrade_scorer import should_upgrade
from wanted_search.metadata import _set_adaptive_retry_after, build_query_from_wanted
from wanted_search.post_processor import (
    _process_forced_wanted_item,
    _try_auto_sync,
    download_specific_for_item,  # noqa: F401 — re-exported for callers
)

logger = logging.getLogger(__name__)


def process_wanted_item(item_id: int) -> dict:
    """Full pipeline for one item: search -> download best -> translate.

    Returns:
        dict: {wanted_id, status, output_path, provider, error}
    """
    # NOTE: item_id-only API ist absichtlich — der Caller (ThreadPoolExecutor) übergibt
    # nur die ID damit jeder Thread seinen eigenen DB-Session-Scope bekommt.
    # Trade-off: N einzelne SELECTs statt 1 Bulk-Fetch. Akzeptiert, solange
    # wanted_search_max_items_per_run < 200 bleibt (typisch: 50).
    item = get_wanted_item(item_id)
    if not item:
        return {"wanted_id": item_id, "status": "error", "error": "Item not found"}

    settings = get_settings()
    item_lang = item.get("target_language") or settings.target_language

    # ── Language profile filters ──────────────────────────────────────────────
    from db.models.core import LanguageProfile, MovieLanguageProfile, SeriesLanguageProfile
    from extensions import db as _db
    from wanted_search.profile_filters import load_profile_filters

    _profile_obj = None
    try:
        _sonarr_sid = item.get("sonarr_series_id")
        _radarr_mid = item.get("radarr_movie_id")
        if _sonarr_sid:
            _slp = _db.session.get(SeriesLanguageProfile, int(_sonarr_sid))
            if _slp:
                _profile_obj = _db.session.get(LanguageProfile, _slp.profile_id)
        elif _radarr_mid:
            _mlp = _db.session.get(MovieLanguageProfile, int(_radarr_mid))
            if _mlp:
                _profile_obj = _db.session.get(LanguageProfile, _mlp.profile_id)
    except Exception as _pe:
        logger.debug("Could not load language profile for wanted %d: %s", item_id, _pe)
    _pf = load_profile_filters(_profile_obj)

    # Cutoff check: if cutoff_language subtitle already exists on disk, skip
    _cutoff = _pf["cutoff_language"]
    if _cutoff:
        from translator import get_output_path_for_lang

        for _ext in ("ass", "srt", "vtt"):
            _cutoff_path = get_output_path_for_lang(item["file_path"], _ext, _cutoff)
            if _cutoff_path and os.path.exists(_cutoff_path):
                logger.info(
                    "Wanted %d: cutoff language '%s' already present at %s, skipping",
                    item_id,
                    _cutoff,
                    _cutoff_path,
                )
                update_wanted_status(item_id, "found")
                return {
                    "wanted_id": item_id,
                    "status": "skipped",
                    "reason": f"cutoff language '{_cutoff}' already present",
                }

    # Audio-exclude check: skip if video audio is already in target language
    _audio_exclude = _pf["audio_exclude_languages"]
    if _audio_exclude and item_lang in _audio_exclude:
        try:
            from ass_utils import has_target_language_audio, run_ffprobe

            _ffprobe_data = run_ffprobe(item["file_path"])
            if has_target_language_audio(_ffprobe_data, item_lang):
                logger.info(
                    "Wanted %d: audio already in '%s', skipping (audio_exclude)",
                    item_id,
                    item_lang,
                )
                update_wanted_status(item_id, "found")
                return {
                    "wanted_id": item_id,
                    "status": "skipped",
                    "reason": f"audio already in '{item_lang}'",
                }
        except Exception as _ae:
            logger.debug("Audio-exclude check failed (non-fatal): %s", _ae)
    # ── End language profile filters ─────────────────────────────────────────

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
        result = manager.search_and_download_best(
            query,
            format_filter=SubtitleFormat.ASS,
            must_contain=_pf["must_contain"] or None,
            must_not_contain=_pf["must_not_contain"] or None,
        )
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

            # Resolve upgraded_from_id for upgrade chain audit trail
            _upgraded_from_id: int | None = None
            if is_upgrade:
                try:
                    from db.providers import get_latest_download_id

                    _upgraded_from_id = get_latest_download_id(file_path)
                except Exception as _uid_err:
                    logger.debug("Could not resolve upgraded_from_id: %s", _uid_err)

            try:
                manager.save_subtitle(result, output_path, series_id=item.get("sonarr_series_id"))
                record_subtitle_download(
                    result.provider_name,
                    result.subtitle_id,
                    item_lang,
                    result.format.value if result.format.value != "unknown" else "ass",
                    file_path,
                    result.score,
                    upgraded_from_id=_upgraded_from_id,
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
                _try_auto_sync(output_path, file_path, settings)
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
                source_query,
                format_filter=SubtitleFormat.ASS,
                must_contain=_pf["must_contain"] or None,
                must_not_contain=_pf["must_not_contain"] or None,
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
                    _try_auto_sync(translate_result.get("output_path"), file_path, settings)
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
            result = manager.search_and_download_best(
                query,
                format_filter=SubtitleFormat.SRT,
                must_contain=_pf["must_contain"] or None,
                must_not_contain=_pf["must_not_contain"] or None,
            )
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
                    _try_auto_sync(output_path, file_path, settings)
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
                source_query,
                format_filter=SubtitleFormat.SRT,
                must_contain=_pf["must_contain"] or None,
                must_not_contain=_pf["must_not_contain"] or None,
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
                    _try_auto_sync(translate_result.get("output_path"), file_path, settings)
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
