"""Wanted extract routes — batch-extract, batch-probe, extract, and _extract_embedded_sub helper."""

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import current_app, jsonify, request

from events import emit_event
from extensions import socketio
from routes.batch_state import (
    _batch_extract_lock,
    _batch_extract_state,
    _batch_probe_lock,
    _batch_probe_state,
)
from routes.wanted import bp

logger = logging.getLogger(__name__)


def _extract_embedded_sub(item_id: int, file_path: str, auto_translate: bool = False) -> dict:
    """Standalone helper: extract embedded subtitle for a wanted item.

    Callable from outside a Flask request context (e.g. from the scanner).
    Returns a result dict with keys: status, output_path, format, language.
    Raises on hard errors; caller is responsible for exception handling.

    Args:
        item_id: ID of the wanted item.
        file_path: Absolute path to the media file.
        auto_translate: If True, trigger translation after extraction.
    """
    from ass_utils import extract_subtitle_stream, get_media_streams, select_best_subtitle_stream
    from config import get_settings
    from db.wanted import get_wanted_item, update_existing_sub, update_wanted_status
    from translator import get_output_path_for_lang

    settings = get_settings()

    item = get_wanted_item(item_id)
    if not item:
        raise ValueError(f"Wanted item {item_id} not found")

    if not file_path or not os.path.exists(file_path):
        raise FileNotFoundError(f"Media file not found: {file_path}")

    if not file_path.lower().endswith((".mkv", ".mp4", ".m4v")):
        raise ValueError(f"File is not a video container (MKV/MP4): {file_path}")

    target_language = item.get("target_language") or settings.target_language

    # Get media stream metadata
    probe_data = get_media_streams(file_path, use_cache=True)

    # Auto-select best subtitle stream for target language
    stream_info = select_best_subtitle_stream(probe_data)
    if not stream_info:
        raise LookupError(f"No suitable subtitle stream found in {file_path}")

    # Determine output path and extract
    output_path = get_output_path_for_lang(file_path, stream_info["format"], target_language)
    extract_subtitle_stream(file_path, stream_info, output_path)

    # Mark item as extracted — keep visible in Wanted for user-initiated cleanup/translate
    update_existing_sub(item_id, stream_info["format"])
    update_wanted_status(item_id, "extracted")
    emit_event(
        "wanted_item_processed",
        {
            "wanted_id": item_id,
            "status": "extracted",
            "output_path": output_path,
            "source": "embedded",
        },
    )

    if auto_translate and stream_info["format"] == "srt":
        # Trigger translation of the extracted SRT in a background thread
        try:
            from translator import Translator

            def _translate_async():
                try:
                    translator = Translator()
                    translator.translate_file(output_path, target_language=target_language)
                except Exception as _exc:
                    logger.warning("[Auto-Translate] Failed for item %d: %s", item_id, _exc)

            threading.Thread(target=_translate_async, daemon=True).start()
        except Exception as exc:
            logger.warning(
                "[Auto-Translate] Could not start translation thread for item %d: %s", item_id, exc
            )

    return {
        "status": "extracted",
        "output_path": output_path,
        "format": stream_info["format"],
        "language": stream_info.get("language", ""),
    }


def _run_batch_extract(item_ids, auto_translate, app):
    """Background thread: extract embedded subs for each item, emit progress events."""
    from db.wanted import get_wanted_item

    with _batch_extract_lock:
        _batch_extract_state.update(
            {
                "running": True,
                "total": len(item_ids),
                "processed": 0,
                "succeeded": 0,
                "failed": 0,
                "skipped": 0,
                "current_item": None,
            }
        )

    try:
        with app.app_context():
            for idx, item_id in enumerate(item_ids):
                item = get_wanted_item(item_id)
                with _batch_extract_lock:
                    _batch_extract_state["current_item"] = (item or {}).get(
                        "title", f"Item {item_id}"
                    )
                try:
                    _extract_embedded_sub(
                        item_id, (item or {}).get("file_path", ""), auto_translate
                    )
                    with _batch_extract_lock:
                        _batch_extract_state["succeeded"] += 1
                except Exception as exc:
                    logger.warning("[batch-extract] item %d failed: %s", item_id, exc)
                    with _batch_extract_lock:
                        _batch_extract_state["failed"] += 1
                with _batch_extract_lock:
                    _batch_extract_state["processed"] = idx + 1
                    snapshot = dict(_batch_extract_state)
                socketio.emit("batch_extract_progress", snapshot)
    finally:
        with _batch_extract_lock:
            _batch_extract_state["running"] = False
            snapshot = dict(_batch_extract_state)
        emit_event("batch_extract_completed", snapshot)


def _run_batch_probe(items, app):
    """Background thread: ffprobe all items, extract all embedded sub streams, update DB."""
    from ass_utils import (
        extract_subtitle_stream,
        get_media_streams,
        get_subtitle_stream_output_path,
        has_target_language_audio,
    )
    from config import get_settings
    from db.wanted import update_existing_sub
    from translator import get_output_path_for_lang

    max_workers = getattr(get_settings(), "scan_metadata_max_workers", 4)

    with _batch_probe_lock:
        _batch_probe_state.update(
            {
                "total": len(items),
                "processed": 0,
                "found": 0,
                "extracted": 0,
                "skipped": 0,
                "failed": 0,
                "current_item": None,
            }
        )

    start_time = time.time()
    try:
        with app.app_context(), ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_item = {
                executor.submit(get_media_streams, item["file_path"], True): item for item in items
            }
            for future in as_completed(future_to_item):
                item = future_to_item[future]
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
                        with _batch_probe_lock:
                            _batch_probe_state["skipped"] += 1
                    else:
                        # Collect all text-based subtitle streams (language-agnostic)
                        sub_streams = []
                        sub_index = 0
                        for stream in probe_data.get("streams", []):
                            if stream.get("codec_type") != "subtitle":
                                continue
                            codec = stream.get("codec_name", "").lower()
                            if codec in ("ass", "ssa"):
                                fmt = "ass"
                            elif codec in (
                                "subrip",
                                "srt",
                                "mov_text",
                                "webvtt",
                                "text",
                                "microdvd",
                            ):
                                fmt = "srt"
                            else:
                                sub_index += 1
                                continue  # skip PGS, VobSub, etc.
                            lang = (stream.get("tags", {}).get("language", "und") or "und").lower()
                            sub_streams.append(
                                {"sub_index": sub_index, "format": fmt, "language": lang}
                            )
                            sub_index += 1

                        if not sub_streams:
                            with _batch_probe_lock:
                                _batch_probe_state["skipped"] += 1
                        else:
                            any_extracted = False
                            for stream_info in sub_streams:
                                out = get_subtitle_stream_output_path(file_path, stream_info)
                                if os.path.exists(out):
                                    any_extracted = True
                                    continue  # already on disk
                                try:
                                    extract_subtitle_stream(file_path, stream_info, out)
                                    logger.info(
                                        "[batch-probe] item %d: extracted %s → %s",
                                        item_id,
                                        stream_info["language"],
                                        out,
                                    )
                                    any_extracted = True
                                except Exception as sub_exc:
                                    logger.warning(
                                        "[batch-probe] item %d stream %d: %s",
                                        item_id,
                                        stream_info["sub_index"],
                                        sub_exc,
                                    )

                            if any_extracted:
                                # Check if target-lang file landed on disk
                                target_ass = get_output_path_for_lang(file_path, "ass", target_lang)
                                target_srt = get_output_path_for_lang(file_path, "srt", target_lang)
                                if os.path.exists(target_ass):
                                    update_existing_sub(item_id, "ass")
                                    logger.info(
                                        "[batch-probe] item %d: target-lang ASS found", item_id
                                    )
                                    with _batch_probe_lock:
                                        _batch_probe_state["found"] += 1
                                elif os.path.exists(target_srt):
                                    update_existing_sub(item_id, "srt")
                                    logger.info(
                                        "[batch-probe] item %d: target-lang SRT found", item_id
                                    )
                                    with _batch_probe_lock:
                                        _batch_probe_state["found"] += 1
                                else:
                                    # Source-lang subs extracted, need translation
                                    with _batch_probe_lock:
                                        _batch_probe_state["extracted"] += 1
                            else:
                                # All extractions failed
                                with _batch_probe_lock:
                                    _batch_probe_state["skipped"] += 1

                except Exception as exc:
                    logger.warning("[batch-probe] item %d failed: %s", item_id, exc)
                    with _batch_probe_lock:
                        _batch_probe_state["failed"] += 1

                with _batch_probe_lock:
                    _batch_probe_state["processed"] += 1
                    snapshot = dict(_batch_probe_state)
                socketio.emit("batch_probe_progress", snapshot)
    finally:
        duration_ms = int((time.time() - start_time) * 1000)
        with _batch_probe_lock:
            _batch_probe_state["running"] = False
            snapshot = dict(_batch_probe_state)
        emit_event("batch_probe_completed", {**snapshot, "duration_ms": duration_ms})


@bp.route("/wanted/batch-extract", methods=["POST"])
def batch_extract():
    """Extract embedded subtitles for multiple wanted items.
    ---
    post:
      tags:
        - Wanted
      summary: Batch extract embedded subtitles
      description: >
        Extracts embedded subtitle streams from MKV/MP4 containers for multiple
        wanted items. Per-item errors do not abort the batch.
      security:
        - apiKeyAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [item_ids]
              properties:
                item_ids:
                  type: array
                  items:
                    type: integer
                  description: List of wanted item IDs
                auto_translate:
                  type: boolean
                  default: false
                  description: Trigger translation after extraction for SRT streams
      responses:
        200:
          description: Batch extraction completed (partial success possible)
          content:
            application/json:
              schema:
                type: object
                properties:
                  succeeded:
                    type: integer
                  failed:
                    type: integer
                  results:
                    type: array
                    items:
                      type: object
        400:
          description: item_ids missing or empty
    """
    from db.wanted import get_wanted_items

    data = request.get_json(force=True, silent=True) or {}
    item_ids = data.get("item_ids", [])
    series_id = data.get("series_id")
    auto_translate = bool(data.get("auto_translate", False))

    # Allow caller to pass series_id to extract all wanted items for that series
    if not item_ids and series_id:
        page = get_wanted_items(page=1, per_page=500, series_id=int(series_id))
        item_ids = [it["id"] for it in page.get("data", [])]

    # Allow empty body to extract all wanted items with missing or embedded subtitles.
    # Include items without any sub AND items probed as embedded_ass/embedded_srt.
    # Exclude items that already have a sidecar (existing_sub = 'ass' or 'srt').
    if not item_ids and not series_id:
        page = get_wanted_items(page=1, per_page=2000)
        item_ids = [
            it["id"]
            for it in page.get("data", [])
            if it.get("existing_sub") in ("embedded_ass", "embedded_srt")
            or not it.get("existing_sub")
        ]

    if not item_ids:
        return jsonify({"error": "No eligible items found", "status": "nothing_to_do"}), 200

    with _batch_extract_lock:
        if _batch_extract_state["running"]:
            return jsonify({"error": "Batch extraction already running"}), 409

    app = current_app._get_current_object()
    threading.Thread(
        target=_run_batch_extract,
        args=(item_ids, auto_translate, app),
        daemon=True,
    ).start()
    return jsonify({"status": "started", "total_items": len(item_ids)}), 202


@bp.route("/wanted/batch-extract/status", methods=["GET"])
def batch_extract_status():
    """Get current batch-extract progress.
    ---
    get:
      tags:
        - Wanted
      summary: Batch extract status
      description: Returns current state of the background batch-extract operation.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Current batch-extract state
    """
    with _batch_extract_lock:
        return jsonify(dict(_batch_extract_state))


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


@bp.route("/wanted/<int:item_id>/extract", methods=["POST"])
def extract_embedded_sub(item_id):
    """Extract an embedded subtitle stream from an MKV file.
    ---
    post:
      tags:
        - Wanted
      summary: Extract embedded subtitle
      description: Extracts an embedded subtitle stream from an MKV/MP4 container for the specified wanted item.
      security:
        - apiKeyAuth: []
      parameters:
        - in: path
          name: item_id
          required: true
          schema:
            type: integer
          description: Wanted item ID
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                stream_index:
                  type: integer
                  description: Specific subtitle stream index to extract
                target_language:
                  type: string
                  description: Target language code (defaults to item or global setting)
      responses:
        200:
          description: Subtitle extracted
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  output_path:
                    type: string
                  format:
                    type: string
                    enum: [ass, srt]
                  language:
                    type: string
        400:
          description: File is not a video container
        404:
          description: Item, file, or subtitle stream not found
    """
    from ass_utils import extract_subtitle_stream, get_media_streams, select_best_subtitle_stream
    from config import get_settings
    from db.wanted import get_wanted_item, update_existing_sub, update_wanted_status
    from translator import get_output_path_for_lang

    settings = get_settings()

    item = get_wanted_item(item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

    file_path = item.get("file_path")
    if not file_path or not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404

    if not file_path.lower().endswith((".mkv", ".mp4", ".m4v")):
        return jsonify({"error": "File is not a video container (MKV/MP4)"}), 400

    data = request.get_json(silent=True) or {}
    target_language = (
        data.get("target_language") or item.get("target_language") or settings.target_language
    )

    try:
        # Get media stream metadata
        probe_data = get_media_streams(file_path, use_cache=True)

        # Select stream
        stream_info = None
        if data.get("stream_index") is not None:
            # Use specific stream index
            stream_index = data["stream_index"]
            streams = probe_data.get("streams", [])
            subtitle_streams = [s for s in streams if s.get("codec_type") == "subtitle"]
            if stream_index < len(subtitle_streams):
                stream = subtitle_streams[stream_index]
                stream_info = {
                    "sub_index": stream_index,
                    "stream_index": stream.get("index"),
                    "format": "ass"
                    if stream.get("codec_name", "").lower() in ("ass", "ssa")
                    else "srt",
                    "language": stream.get("tags", {}).get("language", ""),
                }
        else:
            # Auto-select best stream for target language
            stream_info = select_best_subtitle_stream(probe_data)

        if not stream_info:
            return jsonify({"error": "No suitable subtitle stream found"}), 404

        # Determine output path
        output_path = get_output_path_for_lang(file_path, stream_info["format"], target_language)

        # Extract
        extract_subtitle_stream(file_path, stream_info, output_path)

        # Mark item as extracted — keep visible in Wanted for user-initiated cleanup/translate
        update_existing_sub(item_id, stream_info["format"])
        update_wanted_status(item_id, "extracted")
        emit_event(
            "wanted_item_processed",
            {
                "wanted_id": item_id,
                "status": "extracted",
                "output_path": output_path,
                "source": "embedded",
            },
        )

        return jsonify(
            {
                "status": "extracted",
                "output_path": output_path,
                "format": stream_info["format"],
                "language": stream_info.get("language", ""),
            }
        )

    except Exception:
        raise  # Handled by global error handler
