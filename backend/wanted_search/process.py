"""Wanted search processing — item processing, downloading, and result helpers."""

import contextlib
import logging
import os

from config import get_settings
from db.jobs import create_job, record_stat, update_job
from db.library import record_upgrade
from db.providers import record_subtitle_download
from db.wanted import (
    delete_wanted_item,
    get_wanted_item,
    update_existing_sub,
    update_wanted_status,
)
from error_handler import DuplicateSubtitleError
from providers import get_provider_manager
from providers.base import SubtitleFormat
from upgrade_scorer import should_upgrade
from wanted_search.dubtitle_verify import verify_dubtitle_on_keep
from wanted_search.metadata import _set_adaptive_retry_after, build_query_from_wanted
from wanted_search.post_processor import (
    _process_forced_wanted_item,
    _try_auto_sync,
    download_specific_for_item,  # noqa: F401 — re-exported for callers
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------


def _load_profile_filters(item: dict, item_id: int) -> dict:
    """Resolve the effective language profile filters for a wanted item."""
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
    return load_profile_filters(_profile_obj)


def _check_profile_cutoff_and_audio(
    item: dict, item_id: int, item_lang: str, _pf: dict
) -> dict | None:
    """Apply cutoff_language and audio_exclude profile gates. Returns skip-dict or None."""
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
                delete_wanted_item(item_id)
                return {
                    "wanted_id": item_id,
                    "status": "skipped",
                    "reason": f"cutoff language '{_cutoff}' already present",
                }

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
                delete_wanted_item(item_id)
                return {
                    "wanted_id": item_id,
                    "status": "skipped",
                    "reason": f"audio already in '{item_lang}'",
                }
        except Exception as _ae:
            logger.debug("Audio-exclude check failed (non-fatal): %s", _ae)
    return None


def _check_existing_sidecar(item: dict, item_id: int, item_lang: str, settings) -> dict | None:
    """Short-circuit when the target-language sidecar already exists on disk."""
    try:
        from translator import detect_existing_target_for_lang

        _existing = detect_existing_target_for_lang(item["file_path"], item_lang, probe_data=None)
    except Exception as _dex:
        logger.debug("existing-sidecar probe failed (non-fatal): %s", _dex)
        _existing = None
    if _existing == "ass" or (_existing == "srt" and not settings.upgrade_enabled):
        logger.info(
            "Wanted %d: target lang %s already satisfied by .%s sidecar, skipping provider search",
            item_id,
            item_lang,
            _existing,
        )
        update_existing_sub(item_id, _existing)
        update_wanted_status(item_id, "extracted")
        return {
            "wanted_id": item_id,
            "status": "skipped",
            "reason": f"target '{item_lang}' already on disk as .{_existing}",
        }
    return None


def _check_max_search_attempts(item: dict, item_id: int, settings) -> dict | None:
    """Enter slow-mode (1x / 30d) when search_count exceeded the configured max.

    Historic behaviour (freeze as failed forever) was replaced by slow-mode so
    items still get revisited; search_count may be NULL for pre-migration rows,
    hence the ``or 0``.
    """
    search_count = item.get("search_count") or 0
    if search_count >= settings.wanted_max_search_attempts:
        from services.wanted_search_runner import record_search_outcome

        record_search_outcome(item_id, kind="no_result")
        return {
            "wanted_id": item_id,
            "status": "skipped",
            "reason": "slow-mode (max attempts reached, retry in 30 days)",
        }
    return None


# ---------------------------------------------------------------------------
# Dub-mismatch flagging (best-effort, never raises)
# ---------------------------------------------------------------------------


def _flag_dub_mismatch(saved_path: str) -> None:
    """Log a warning when audio verification identifies a likely dub mismatch.

    Best-effort: the subtitle has already been saved and is kept regardless.
    This function only records the observation so it shows up in logs.
    """
    logger.warning(
        "dub_audio_mismatch: %s kept but flagged as a likely dub mismatch by audio verification",
        saved_path,
    )


# ---------------------------------------------------------------------------
# Step 1: target-language ASS direct download
# ---------------------------------------------------------------------------


def _try_target_ass_direct(ctx: dict) -> dict | None:
    """Step 1: search providers directly for a target-language ASS subtitle.

    Mutates ``ctx['ass_had_results']`` when providers returned ASS content
    (used later to decide whether SRT steps can be skipped). Returns an
    outcome dict when the wanted item is satisfied or explicitly skipped.
    Returns ``None`` to fall through to the next step.
    """
    item = ctx["item"]
    item_id = ctx["item_id"]
    item_lang = ctx["item_lang"]
    settings = ctx["settings"]
    manager = ctx["manager"]
    query = ctx["query"]
    _pf = ctx["_pf"]
    file_path = ctx["file_path"]
    is_upgrade = ctx["is_upgrade"]
    current_score = ctx["current_score"]

    try:
        result = manager.search_and_download_best(
            query,
            format_filter=SubtitleFormat.ASS,
            must_contain=_pf["must_contain"] or None,
            must_not_contain=_pf["must_not_contain"] or None,
        )
        if not (result and result.content):
            return None

        ctx["ass_had_results"] = True
        new_score = result.score

        if ctx.get("dry_run"):
            from translator import get_output_path_for_lang

            return {
                "wanted_id": item_id,
                "status": "found",
                "dry_run": True,
                "output_path": get_output_path_for_lang(file_path, "ass", item_lang),
                "provider": result.provider_name,
                "score": new_score,
                "format": "ass",
            }

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
                return {"wanted_id": item_id, "status": "skipped", "reason": reason}
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
            # save_subtitle MAY rewrite the extension when the actual format
            # differs from output_path's extension (e.g. asked for .ass but
            # content detection determined SRT). Always use the returned
            # path for downstream operations — the input is a hint only.
            saved_path = manager.save_subtitle(
                result, output_path, series_id=item.get("sonarr_series_id")
            )
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
                saved_path,
                {
                    "provider": result.provider_name,
                    "source_language": getattr(result, "language", ""),
                    "target_language": item_lang,
                    "score": result.score,
                },
            )
            if not verify_dubtitle_on_keep(saved_path, file_path, settings):
                _flag_dub_mismatch(saved_path)
            _try_auto_sync(saved_path, file_path, settings)
            delete_wanted_item(item_id)
            return {
                "wanted_id": item_id,
                "status": "found",
                "output_path": saved_path,
                "provider": result.provider_name,
                "upgraded": is_upgrade,
            }
        except DuplicateSubtitleError as dup_err:
            logger.info(
                "Wanted %d: Duplicate subtitle skipped, already at %s",
                item_id,
                dup_err.existing_path,
            )
            delete_wanted_item(item_id)
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
    return None


# ---------------------------------------------------------------------------
# Step 2: source-language ASS download + translation
# ---------------------------------------------------------------------------


def _try_source_ass_translation(ctx: dict) -> dict | None:
    """Step 2: download a source-language ASS and translate it to the target lang."""
    item = ctx["item"]
    item_id = ctx["item_id"]
    item_lang = ctx["item_lang"]
    settings = ctx["settings"]
    manager = ctx["manager"]
    _pf = ctx["_pf"]
    file_path = ctx["file_path"]

    source_query = build_query_from_wanted(item)
    source_query.languages = [settings.source_language]
    ctx["source_query"] = source_query
    try:
        result = manager.search_and_download_best(
            source_query,
            format_filter=SubtitleFormat.ASS,
            must_contain=_pf["must_contain"] or None,
            must_not_contain=_pf["must_not_contain"] or None,
        )
        if not (result and result.content):
            return None

        ctx["ass_had_results"] = True
        from translator import _translate_external_ass, get_output_path_for_lang  # noqa: F401

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

        arr_context = _build_arr_context(item)

        job = create_job(file_path, force=False, arr_context=arr_context if arr_context else None)
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

            from services.mt_provisional import finalize_translation

            finalize_translation(
                item_id, item, translate_result.get("output_path"), item_lang, "ass"
            )
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
                error=translate_result.get("error") if translate_result else "Translation failed",
            )
            record_stat(success=False)
    except Exception as e:
        logger.warning(
            "Wanted %d: Source ASS search/translation failed: %s", item_id, e, exc_info=True
        )
    return None


# ---------------------------------------------------------------------------
# Step 3: target-language SRT direct download
# ---------------------------------------------------------------------------


def _try_target_srt_direct(ctx: dict) -> dict | None:
    """Step 3: search providers directly for a target-language SRT subtitle."""
    item = ctx["item"]
    item_id = ctx["item_id"]
    item_lang = ctx["item_lang"]
    settings = ctx["settings"]
    manager = ctx["manager"]
    _pf = ctx["_pf"]
    file_path = ctx["file_path"]
    query = ctx["query"]

    try:
        result = manager.search_and_download_best(
            query,
            format_filter=SubtitleFormat.SRT,
            must_contain=_pf["must_contain"] or None,
            must_not_contain=_pf["must_not_contain"] or None,
        )
        if not (result and result.content):
            return None

        from translator import get_output_path_for_lang

        output_path = get_output_path_for_lang(file_path, "srt", item_lang)

        if ctx.get("dry_run"):
            return {
                "wanted_id": item_id,
                "status": "found",
                "dry_run": True,
                "output_path": output_path,
                "provider": result.provider_name,
                "score": result.score,
                "format": "srt",
            }
        try:
            # Use the returned path — see comment at Step 1: save_subtitle
            # may rewrite the extension if the format differs.
            saved_path = manager.save_subtitle(
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
                saved_path,
                {
                    "provider": result.provider_name,
                    "source_language": getattr(result, "language", ""),
                    "target_language": item_lang,
                    "score": result.score,
                },
            )
            if not verify_dubtitle_on_keep(saved_path, file_path, settings):
                _flag_dub_mismatch(saved_path)
            _try_auto_sync(saved_path, file_path, settings)
            delete_wanted_item(item_id)
            return {
                "wanted_id": item_id,
                "status": "found",
                "output_path": saved_path,
                "provider": result.provider_name,
            }
        except DuplicateSubtitleError as dup_err:
            logger.info(
                "Wanted %d: Duplicate target SRT skipped, already at %s",
                item_id,
                dup_err.existing_path,
            )
            delete_wanted_item(item_id)
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
        logger.warning("Wanted %d: Direct target SRT search failed: %s", item_id, e, exc_info=True)
    return None


# ---------------------------------------------------------------------------
# Step 4: source-language SRT download + translation
# ---------------------------------------------------------------------------


def _try_source_srt_translation(ctx: dict) -> dict | None:
    """Step 4: download a source-language SRT and translate it to the target lang."""
    item = ctx["item"]
    item_id = ctx["item_id"]
    item_lang = ctx["item_lang"]
    settings = ctx["settings"]
    manager = ctx["manager"]
    _pf = ctx["_pf"]
    file_path = ctx["file_path"]
    source_query = ctx.get("source_query")
    if source_query is None:
        source_query = build_query_from_wanted(item)
        source_query.languages = [settings.source_language]
        ctx["source_query"] = source_query

    try:
        result = manager.search_and_download_best(
            source_query,
            format_filter=SubtitleFormat.SRT,
            must_contain=_pf["must_contain"] or None,
            must_not_contain=_pf["must_not_contain"] or None,
        )
        if not (result and result.content):
            return None

        from translator import get_output_path_for_lang, translate_srt_from_file  # noqa: F401

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

        arr_context = _build_arr_context(item)

        job = create_job(file_path, force=False, arr_context=arr_context if arr_context else None)
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

            from services.mt_provisional import finalize_translation

            finalize_translation(
                item_id, item, translate_result.get("output_path"), item_lang, "srt"
            )
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
                error=translate_result.get("error") if translate_result else "Translation failed",
            )
            record_stat(success=False)
    except Exception as e:
        logger.warning(
            "Wanted %d: Source SRT search/translation failed: %s", item_id, e, exc_info=True
        )
    return None


# ---------------------------------------------------------------------------
# Step 5: fallback to translate_file (embedded-subtitle pipeline)
# ---------------------------------------------------------------------------


def _fallback_translate_file(ctx: dict) -> dict:
    """Step 5: defer to translator.translate_file which handles embedded subs.

    Called last when providers produced nothing for the wanted item. When
    auto_translate is off this just marks the item as not_found.
    """
    item = ctx["item"]
    item_id = ctx["item_id"]
    item_lang = ctx["item_lang"]
    settings = ctx["settings"]
    auto_translate = ctx["auto_translate"]
    file_path = ctx["file_path"]

    if not auto_translate:
        logger.debug(
            "Wanted %d: auto_translate disabled, no subtitle found without translation", item_id
        )
        # Funnel no-result through record_search_outcome so failure_kind
        # and retry_after are set — otherwise the item ends up legacy_frozen.
        from services.wanted_search_runner import record_search_outcome

        update_wanted_status(item_id, "wanted")
        record_search_outcome(item_id, kind="no_result")
        return {
            "wanted_id": item_id,
            "status": "not_found",
            "reason": "No subtitle found; translation disabled",
        }
    try:
        from translator import translate_file

        arr_context = _build_arr_context(item)
        job = create_job(file_path, force=False, arr_context=arr_context if arr_context else None)
        update_job(job["id"], "running")
        # Prefer the item's profile source language (per-profile translation
        # direction); translate_file falls back to the global source when None.
        profile_source = None
        try:
            from services.mt_provisional import _resolve_profile_for_item

            prof = _resolve_profile_for_item(item)
            profile_source = (prof or {}).get("source_language") or None
        except Exception:  # pragma: no cover - defensive
            profile_source = None
        translate_result = translate_file(
            file_path,
            target_language=item_lang,
            arr_context=arr_context if arr_context else None,
            source_language=profile_source,
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
                delete_wanted_item(item_id)
                return {
                    "wanted_id": item_id,
                    "status": "found",
                    "output_path": translate_result.get("output_path"),
                    "provider": "translate_pipeline",
                }
            else:
                # A genuine new machine translation was produced (embedded
                # fallback). Flag it + keep the wanted provisional per profile
                # (feature #8), same as the other translate-completion sites.
                from services.mt_provisional import finalize_translation

                finalize_translation(
                    item_id,
                    item,
                    translate_result.get("output_path"),
                    item_lang,
                    translate_result.get("stats", {}).get("format") or "ass",
                )
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


def _build_arr_context(item: dict) -> dict:
    """Return a minimal arr_context dict for translator glossary / integration lookup."""
    arr_context: dict = {}
    if item.get("sonarr_series_id"):
        arr_context["sonarr_series_id"] = item["sonarr_series_id"]
    if item.get("sonarr_episode_id"):
        arr_context["sonarr_episode_id"] = item["sonarr_episode_id"]
    if item.get("radarr_movie_id"):
        arr_context["radarr_movie_id"] = item["radarr_movie_id"]
    return arr_context


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def process_wanted_item(
    item_id: int,
    auto_translate: bool | None = None,
    dry_run: bool = False,
    bypass_existing_target_check: bool = False,
) -> dict:
    """Full pipeline for one item: search -> download best -> translate.

    Args:
        item_id: The wanted item to process.
        auto_translate: Override for the translate gate. ``None`` (default)
            reads ``settings.wanted_auto_translate`` as before. Passing
            ``False`` forces ORIGINAL-ONLY mode (skip the source-language
            translate steps 2/4/5) — used by the provisional-MT re-seek job
            (feature #8b) to look for a genuine provider/embedded original
            without re-translating. ``True`` forces translation on.
        dry_run: When ``True``, PREVIEW only — a genuine provider original
            found via Step 1 (target ASS direct) or Step 3 (target SRT
            direct) short-circuits BEFORE ``save_subtitle`` /
            ``record_subtitle_download`` / ``delete_wanted_item`` and returns
            ``{"status": "found", "dry_run": True, "provider", "score",
            "output_path"}`` instead. Nothing is written to disk or the DB.
            The normal "found" path is atomic (search -> download -> save ->
            record -> delete, all before returning) so there is no other
            point at which a caller can pause it — ``dry_run`` exists for
            that purpose. Step 5 (embedded/translate fallback) is NOT
            preview-safe (it triggers real extraction/translation as a side
            effect of computing its own result) — in dry_run mode the
            orchestrator stops before Step 5 and reports
            ``{"status": "not_found", "dry_run": True}``. Used by the
            provisional-MT re-seek job (feature #8b Phase 2 Task 2) to detect
            a qualifying original before deciding replace-vs-notify.
            Default ``False`` preserves the exact prior behaviour.
            Scope note: ``dry_run`` only guards the PROVIDER-SEARCH write path
            (Steps 1/3/5). The pre-flight gates that run before it
            (``_check_profile_cutoff_and_audio``, ``_check_existing_sidecar``
            unless bypassed, ``_check_max_search_attempts``) can still mutate
            the wanted row or delete it — their outcomes are deterministic
            file-presence/attempt-count facts independent of whether a
            provider search happens, so letting them run identically in
            preview and real calls is intentional, not an oversight.
        bypass_existing_target_check: When ``True``, skip the early
            "target-language sidecar already exists" short-circuit
            (``_check_existing_sidecar``). Provisional-MT items already HAVE
            a target-language sidecar — it IS the machine translation being
            re-sought against — so the ordinary gate (which only checks file
            presence, not provenance) would otherwise make the re-seek job a
            permanent no-op for MT rows saved as ``.ass``. Used by
            ``services.mt_reseek`` on both the preview and (for
            ``auto_replace``) the real write call. Default ``False``
            preserves the exact prior behaviour.

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
    _pf = _load_profile_filters(item, item_id)

    skip = _check_profile_cutoff_and_audio(item, item_id, item_lang, _pf)
    if skip is not None:
        return skip

    if not bypass_existing_target_check:
        skip = _check_existing_sidecar(item, item_id, item_lang, settings)
        if skip is not None:
            return skip

    skip = _check_max_search_attempts(item, item_id, settings)
    if skip is not None:
        return skip

    update_wanted_status(item_id, "searching")
    # search_count + last_search_at are bumped at no-result exits via
    # record_search_outcome — keeping it the single mutation point keeps
    # failure_kind in sync with the count and avoids legacy_frozen rows.

    file_path = item["file_path"]
    if not os.path.exists(file_path):
        update_wanted_status(item_id, "failed", error="File not found on disk")
        return {
            "wanted_id": item_id,
            "status": "failed",
            "error": f"File not found: {file_path}",
        }

    subtitle_type = item.get("subtitle_type", "full")
    manager = get_provider_manager()

    # Forced subtitle handling: download-only, no translation
    if subtitle_type == "forced":
        return _process_forced_wanted_item(item, item_id, item_lang, manager)

    # Build primary target-language query shared across Step 1 / Step 3
    query = build_query_from_wanted(item)
    query.languages = [item_lang]
    query.hi_preference = _pf.get("hi_preference", "include")
    query.forced_scoring = _pf.get("forced_scoring", "include")

    ctx = {
        "item": item,
        "item_id": item_id,
        "settings": settings,
        "item_lang": item_lang,
        "_pf": _pf,
        "file_path": file_path,
        "is_upgrade": bool(item.get("upgrade_candidate")),
        "current_score": item.get("current_score", 0),
        "manager": manager,
        "auto_translate": (
            getattr(settings, "wanted_auto_translate", True)
            if auto_translate is None
            else bool(auto_translate)
        ),
        "query": query,
        "source_query": None,
        "ass_had_results": False,
        "dry_run": dry_run,
    }

    # Step 1: target-language ASS direct
    result = _try_target_ass_direct(ctx)
    if result is not None:
        return result

    # Step 2: source-language ASS + translate (guarded by auto_translate)
    if ctx["auto_translate"]:
        result = _try_source_ass_translation(ctx)
        if result is not None:
            return result
    else:
        logger.debug("Wanted %d: auto_translate disabled, skipping source ASS translation", item_id)

    # Phase 2: skip SRT steps if no ASS was found in Steps 1+2 (providers likely have nothing)
    _skip_srt = getattr(settings, "wanted_skip_srt_on_no_ass", True) and not ctx["ass_had_results"]
    if _skip_srt:
        logger.debug("Wanted %d: No ASS found in Steps 1+2, skipping SRT steps", item_id)
    else:
        # Step 3: target-language SRT direct
        result = _try_target_srt_direct(ctx)
        if result is not None:
            return result

        # Step 4: source-language SRT + translate (guarded by auto_translate)
        if ctx["auto_translate"]:
            result = _try_source_srt_translation(ctx)
            if result is not None:
                return result

    # Step 5: fallback to translate_file (embedded subtitle pipeline).
    # NOT preview-safe (extraction/translation happen as a side effect of
    # computing translate_file's own result) — dry_run stops here instead of
    # entering it. See process_wanted_item's dry_run docstring.
    if ctx.get("dry_run"):
        logger.debug(
            "Wanted %d: dry_run stops before the embedded/translate fallback (Step 5)", item_id
        )
        return {"wanted_id": item_id, "status": "not_found", "dry_run": True}
    return _fallback_translate_file(ctx)
