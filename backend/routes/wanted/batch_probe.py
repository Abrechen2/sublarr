"""Wanted batch-probe route — ffprobe all items, extract embedded streams, update DB.

Delegates the actual extract+cleanup pipeline to
``services.embedded_extractor`` so that the auto path
(``routes/wanted/extract.py::_extract_embedded_sub``) and this UI-driven
path stay in lock-step. This module only owns:

  - WebSocket progress emission
  - the counters surfaced in the Batch-Probe modal (found/extracted/
    skipped/failed)
  - the ``has_target_language_audio`` short-circuit (don't bother
    extracting subs for content that's already in the target language)
  - the foreign-track cleanup hook (gated by per-series policy)
"""

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import current_app, jsonify, request

from config import get_settings
from events import emit_event
from extensions import socketio
from routes.batch_state import _batch_probe_lock, _batch_probe_state
from routes.wanted import bp
from services.background_tasks import submit_background
from services.embedded_extractor import (
    compute_keep_langs,
    extract_and_cleanup,
    resolve_profile_for_item,
)

logger = logging.getLogger(__name__)


# Backwards-compat shim — older code imported this private name directly.
_resolve_profile_for_item = resolve_profile_for_item


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
            settings = get_settings()
            profile = resolve_profile_for_item(item, settings)
            keep_langs = compute_keep_langs(profile, settings)

            result = extract_and_cleanup(
                file_path=file_path,
                probe_data=probe_data,
                keep_langs=keep_langs,
                target_language=target_lang,
                log_label=f"batch-probe item {item_id}",
                remove_from_container=bool(
                    getattr(settings, "embedded_extract_remove_from_container", False)
                ),
            )

            if not result.any_extracted:
                _bump_probe_state_counter("skipped")
            else:
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

    except Exception as exc:
        logger.warning("[batch-probe] item %d failed: %s", item_id, exc)
        _bump_probe_state_counter("failed")

    with _batch_probe_lock:
        _batch_probe_state["processed"] += 1
        snapshot = dict(_batch_probe_state)
    socketio.emit("batch_probe_progress", snapshot)


def _gated_probe(file_path: str):
    """One probe, one media-gate slot — the pool size alone cannot bound
    concurrency across two batches running at once."""
    from ass_utils import get_media_streams
    from services.media_io_gate import media_io_gate

    with media_io_gate.slot("batch probe"):
        return get_media_streams(file_path, True)


def _run_batch_probe(items, app):
    """Background thread: ffprobe all items, extract all embedded sub streams, update DB."""
    from services.media_io_gate import media_io_gate

    max_workers = media_io_gate.cap_workers(getattr(get_settings(), "scan_metadata_max_workers", 4))
    _init_batch_probe_state(len(items))
    start_time = time.time()
    try:
        with app.app_context(), ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_item = {
                executor.submit(_gated_probe, item["file_path"]): item for item in items
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
    submit_background(_run_batch_probe, items, app)
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
