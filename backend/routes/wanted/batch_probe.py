"""Wanted batch-probe route — ffprobe all items, extract embedded streams, update DB."""

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import current_app, jsonify, request

from config import get_settings
from events import emit_event
from extensions import socketio
from remux import RemuxError, remove_subtitle_streams
from routes.batch_state import _batch_probe_lock, _batch_probe_state
from routes.wanted import bp

logger = logging.getLogger(__name__)


def _resolve_profile_for_item(item: dict, settings) -> dict:
    """Return the language profile that governs a wanted item.

    Preference order:
      1. Per-series profile (for episodes) via get_series_profile
      2. Per-movie profile (for movies) via get_movie_profile
      3. Default profile (falls back to synthetic default derived from
         settings when no profile exists in the DB)

    The return value always has ``target_languages`` populated, so callers
    can treat it as a simple dict without defensive ``get`` calls.
    """
    from db.profiles import get_default_profile, get_movie_profile, get_series_profile

    try:
        if item.get("sonarr_series_id"):
            profile = get_series_profile(item["sonarr_series_id"])
        elif item.get("radarr_movie_id"):
            profile = get_movie_profile(item["radarr_movie_id"])
        else:
            profile = get_default_profile()
    except Exception as exc:  # pragma: no cover — DB hiccup shouldn't kill the cleanup
        logger.debug("Profile lookup failed for item %s: %s", item.get("id"), exc)
        profile = get_default_profile()

    if not profile.get("target_languages"):
        # Guaranteed minimum so the caller doesn't need a fallback branch.
        fallback = getattr(settings, "target_language", "")
        profile = dict(profile)
        profile["target_languages"] = [fallback] if fallback else []
    return profile


def _init_batch_probe_state(total: int) -> None:
    """Thread-safe state reset at the start of a batch-probe run."""
    with _batch_probe_lock:
        _batch_probe_state.update(
            {
                "total": total,
                "processed": 0,
                "found": 0,
                "extracted": 0,
                "skipped": 0,
                "failed": 0,
                "current_item": None,
            }
        )


def _finalize_batch_probe(start_time: float) -> None:
    """DB session cleanup + final socketio completion event."""
    try:
        from extensions import db as _db

        _db.session.remove()
    except Exception:
        pass
    duration_ms = int((time.time() - start_time) * 1000)
    with _batch_probe_lock:
        _batch_probe_state["running"] = False
        snapshot = dict(_batch_probe_state)
    emit_event("batch_probe_completed", {**snapshot, "duration_ms": duration_ms})


def _bump_probe_state_counter(key: str) -> None:
    """Thread-safe increment of a single _batch_probe_state counter."""
    with _batch_probe_lock:
        _batch_probe_state[key] += 1


def _collect_subtitle_streams(probe_data: dict) -> list[dict]:
    """Classify text-subtitle streams from ffprobe output.

    Returns a list of dicts with keys: sub_index, stream_index, format,
    language, is_sdh. Skips image-based formats (PGS, VobSub, etc.).

    0.71.0: honours `embedded_allow_sdh`. When False, SDH/CC/HI streams
    are dropped entirely so the batch-probe ignores them. Default True.
    """
    from ass_probe import is_sdh_stream

    allow_sdh = True
    try:
        allow_sdh = bool(getattr(get_settings(), "embedded_allow_sdh", True))
    except Exception:
        logger.debug("batch_probe: embedded_allow_sdh unavailable; assuming True")

    sub_streams = []
    sub_index = 0
    for stream in probe_data.get("streams", []):
        if stream.get("codec_type") != "subtitle":
            continue
        codec = stream.get("codec_name", "").lower()
        if codec in ("ass", "ssa"):
            fmt = "ass"
        elif codec in ("subrip", "srt", "mov_text", "webvtt", "text", "microdvd"):
            fmt = "srt"
        else:
            sub_index += 1
            continue  # skip PGS, VobSub, etc.
        sdh = is_sdh_stream(stream)
        if sdh and not allow_sdh:
            sub_index += 1
            continue
        lang = (stream.get("tags", {}).get("language", "und") or "und").lower()
        sub_streams.append(
            {
                "sub_index": sub_index,
                "stream_index": stream.get("index"),
                "format": fmt,
                "language": lang,
                "is_sdh": sdh,
            }
        )
        sub_index += 1
    return sub_streams


def _extract_stream_candidates(
    item_id: int, file_path: str, sub_streams: list[dict]
) -> tuple[bool, list[tuple[int, int]]]:
    """Extract subtitle streams from the container to sidecar files.

    Returns (any_extracted, streams_to_remove) where streams_to_remove is a list
    of (global_stream_index, sub_index) tuples for the subsequent container-removal pass.
    """
    from ass_utils import extract_subtitle_stream, get_subtitle_stream_output_path

    any_extracted = False
    streams_to_remove: list[tuple[int, int]] = []
    seen_lang_fmt: set[tuple[str, str]] = set()

    for stream_info in sub_streams:
        lang_fmt = (stream_info["language"], stream_info["format"])
        out = get_subtitle_stream_output_path(file_path, stream_info)

        if os.path.exists(out):
            any_extracted = True
            # Stream already on disk — still schedule for removal
            if stream_info.get("stream_index") is not None:
                streams_to_remove.append((stream_info["stream_index"], stream_info["sub_index"]))
            seen_lang_fmt.add(lang_fmt)
            continue

        if lang_fmt in seen_lang_fmt:
            # Duplicate lang+format: skip extraction but still remove
            if stream_info.get("stream_index") is not None:
                streams_to_remove.append((stream_info["stream_index"], stream_info["sub_index"]))
            continue

        try:
            extract_subtitle_stream(file_path, stream_info, out)
            logger.info(
                "[batch-probe] item %d: extracted %s → %s",
                item_id,
                stream_info["language"],
                out,
            )
            any_extracted = True
            seen_lang_fmt.add(lang_fmt)
            if stream_info.get("stream_index") is not None:
                streams_to_remove.append((stream_info["stream_index"], stream_info["sub_index"]))
        except Exception as sub_exc:
            logger.warning(
                "[batch-probe] item %d stream %d: %s",
                item_id,
                stream_info["sub_index"],
                sub_exc,
            )

    return any_extracted, streams_to_remove


def _remove_streams_from_container(
    item_id: int, file_path: str, streams_to_remove: list[tuple[int, int]]
) -> None:
    """Remove all extracted subtitle streams from the video container in one pass."""
    if not streams_to_remove:
        return
    try:
        _settings = get_settings()
        bak = remove_subtitle_streams(
            video_path=file_path,
            streams=streams_to_remove,
            use_reflink=getattr(_settings, "remux_use_reflink", True),
            trash_dir=getattr(_settings, "remux_trash_dir", ".sublarr"),
        )
        logger.info(
            "[batch-probe] item %d: removed %d stream(s) from container (backup: %s)",
            item_id,
            len(streams_to_remove),
            bak,
        )
    except (RemuxError, Exception) as remux_exc:
        logger.warning(
            "[batch-probe] item %d: container removal failed: %s",
            item_id,
            remux_exc,
        )


def _trash_non_target_sidecars_for_probe(item: dict, file_path: str) -> None:
    """Move sidecar files whose language is not in the item's profile to the trash folder.

    Named with _for_probe suffix to avoid collision with remux.trash_non_target_sidecars
    (which this function imports and calls). Non-fatal: errors are logged as warnings.
    """
    from config_language_data import normalize_language_code
    from remux import trash_non_target_sidecars

    item_id = item["id"]
    try:
        _settings = get_settings()
        _profile = _resolve_profile_for_item(item, _settings)
        _keep = {
            normalize_language_code(code) for code in _profile.get("target_languages", []) if code
        }
        if getattr(_settings, "wanted_auto_translate", False):
            _keep.add(normalize_language_code(_settings.source_language))
        _keep.discard("")  # defensive
        if _keep:
            trashed = trash_non_target_sidecars(
                video_path=file_path,
                keep_langs=_keep,
                trash_dir=getattr(_settings, "remux_trash_dir", ".sublarr"),
            )
            if trashed:
                logger.info(
                    "[batch-probe] item %d: trashed %d non-target sidecar(s) (keep=%s)",
                    item_id,
                    len(trashed),
                    sorted(_keep),
                )
    except Exception as cleanup_exc:
        logger.warning(
            "[batch-probe] item %d: sidecar cleanup failed: %s",
            item_id,
            cleanup_exc,
        )


def _update_item_db_state(item_id: int, file_path: str, target_lang: str | None) -> None:
    """Check whether the target-lang subtitle landed on disk and update the DB accordingly.

    Bumps `found` when the target-language file is present, `extracted` when only
    source-language subs were extracted (translation still needed).
    """
    from db.wanted import update_existing_sub
    from translator import get_output_path_for_lang

    target_ass = get_output_path_for_lang(file_path, "ass", target_lang)
    target_srt = get_output_path_for_lang(file_path, "srt", target_lang)
    if os.path.exists(target_ass):
        update_existing_sub(item_id, "ass")
        logger.info("[batch-probe] item %d: target-lang ASS found", item_id)
        _bump_probe_state_counter("found")
    elif os.path.exists(target_srt):
        update_existing_sub(item_id, "srt")
        logger.info("[batch-probe] item %d: target-lang SRT found", item_id)
        _bump_probe_state_counter("found")
    else:
        # Source-lang subs extracted, need translation
        _bump_probe_state_counter("extracted")


def _process_probe_result(item: dict, future) -> None:
    """Handle the probe result for a single item: classify → extract → remux → cleanup → DB.

    Contains the full per-item try/except so that errors never propagate to the
    executor loop and processed+progress-emit always runs in the outer finally path.
    """
    from ass_utils import has_target_language_audio

    item_id = item["id"]
    file_path = item["file_path"]
    target_lang = item.get("target_language") or None

    with _batch_probe_lock:
        _batch_probe_state["current_item"] = item.get("title", f"Item {item_id}")

    try:
        probe_data = future.result()
        if probe_data is None:
            raise ValueError("ffprobe returned no data")

        if has_target_language_audio(probe_data, target_lang):
            _bump_probe_state_counter("skipped")
        else:
            # Collect all text-based subtitle streams (language-agnostic).
            # Capture both sub_index (0-based subtitle-only) and stream_index
            # (global ffprobe index, needed for container removal).
            sub_streams = _collect_subtitle_streams(probe_data)

            if not sub_streams:
                _bump_probe_state_counter("skipped")
            else:
                any_extracted, streams_to_remove = _extract_stream_candidates(
                    item_id, file_path, sub_streams
                )

                # Remove all extracted streams from the container in one pass
                _remove_streams_from_container(item_id, file_path, streams_to_remove)

                # Trash sidecars whose language is not in this item's
                # language profile. We just extracted everything the
                # container offered, so any file we keep must match
                # what the user configured (target_languages, plus
                # source_language when translation is enabled). All
                # other language tags are moved to the same trash
                # folder the remux backup uses — nothing is hard-
                # deleted, so recovery is always possible.
                if any_extracted:
                    _trash_non_target_sidecars_for_probe(item, file_path)

                if any_extracted:
                    _update_item_db_state(item_id, file_path, target_lang)
                    # 0.71.0 — foreign-track cleanup runs after successful
                    # extraction + sidecar trashing. Gated by effective policy
                    # (series override + global default); no-op otherwise.
                    # Any failure is swallowed with logging — we must not
                    # break the happy path because of a cleanup glitch.
                    try:
                        from services.foreign_track_cleanup import (
                            maybe_run_foreign_track_cleanup,
                        )

                        maybe_run_foreign_track_cleanup(item, file_path)
                    except Exception as cleanup_exc:
                        logger.warning(
                            "[batch-probe] item %d: foreign-track cleanup raised: %s",
                            item_id,
                            cleanup_exc,
                        )
                else:
                    # All extractions failed
                    _bump_probe_state_counter("skipped")

    except Exception as exc:
        logger.warning("[batch-probe] item %d failed: %s", item_id, exc)
        _bump_probe_state_counter("failed")

    with _batch_probe_lock:
        _batch_probe_state["processed"] += 1
        snapshot = dict(_batch_probe_state)
    socketio.emit("batch_probe_progress", snapshot)


def _run_batch_probe(items, app):
    """Background thread: ffprobe all items, extract all embedded sub streams, update DB."""
    from ass_utils import get_media_streams

    max_workers = getattr(get_settings(), "scan_metadata_max_workers", 4)
    _init_batch_probe_state(len(items))
    start_time = time.time()
    try:
        with app.app_context(), ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_item = {
                executor.submit(get_media_streams, item["file_path"], True): item for item in items
            }
            for future in as_completed(future_to_item):
                _process_probe_result(future_to_item[future], future)
    finally:
        _finalize_batch_probe(start_time)


@bp.route("/wanted/batch-probe", methods=["POST"])
def batch_probe():
    """Run ffprobe on all unresolved wanted items to detect embedded subtitles.
    ---
    post:
      tags:
        - Wanted
      summary: Batch metadata pre-scan
      description: >
        Runs ffprobe in parallel on all wanted items with empty existing_sub,
        detects embedded target-language subtitle streams, and updates
        existing_sub to embedded_srt or embedded_ass. Returns 202 immediately;
        progress is emitted via WebSocket batch_probe_progress events.
      security:
        - apiKeyAuth: []
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                series_id:
                  type: integer
                  nullable: true
                  description: Optional Sonarr series ID to limit scope
      responses:
        202:
          description: Probe started
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  total_items:
                    type: integer
        200:
          description: Nothing to probe (all items already have existing_sub)
        409:
          description: Probe already running
    """
    from db.wanted import get_wanted_items

    data = request.get_json(force=True, silent=True) or {}
    series_id = data.get("series_id")

    # Claim the slot before slow DB work to avoid race condition
    with _batch_probe_lock:
        if _batch_probe_state["running"]:
            return jsonify({"error": "Batch probe already running"}), 409
        _batch_probe_state["running"] = True

    try:
        page = get_wanted_items(page=1, per_page=5000, series_id=series_id)
        items = [it for it in page.get("data", []) if not it.get("existing_sub")]
    except Exception:
        with _batch_probe_lock:
            _batch_probe_state["running"] = False
        raise

    if not items:
        with _batch_probe_lock:
            _batch_probe_state["running"] = False
        return jsonify({"status": "nothing_to_probe", "total_items": 0})

    app = current_app._get_current_object()
    threading.Thread(
        target=_run_batch_probe,
        args=(items, app),
        daemon=True,
    ).start()
    return jsonify({"status": "started", "total_items": len(items)}), 202


@bp.route("/wanted/batch-probe/status", methods=["GET"])
def batch_probe_status():
    """Get current batch-probe progress.
    ---
    get:
      tags:
        - Wanted
      summary: Batch probe status
      description: Returns current state of the background batch metadata probe operation.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Current batch-probe state
    """
    with _batch_probe_lock:
        return jsonify(dict(_batch_probe_state))
