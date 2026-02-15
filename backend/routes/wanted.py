"""Wanted routes — /wanted, /wanted/batch-search, /wanted/search-all."""

import os
import logging
import threading

from flask import Blueprint, request, jsonify

from extensions import socketio
from events import emit_event

bp = Blueprint("wanted", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)

# Wanted batch state (in-memory for real-time tracking)
wanted_batch_state = {
    "running": False,
    "total": 0,
    "processed": 0,
    "found": 0,
    "failed": 0,
    "skipped": 0,
    "current_item": None,
}
wanted_batch_lock = threading.Lock()


@bp.route("/wanted", methods=["GET"])
def list_wanted():
    """Get paginated wanted items."""
    from db.wanted import get_wanted_items

    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 200)
    item_type = request.args.get("item_type")
    status_filter = request.args.get("status")
    series_id = request.args.get("series_id", type=int)
    subtitle_type = request.args.get("subtitle_type")

    result = get_wanted_items(
        page=page, per_page=per_page,
        item_type=item_type, status=status_filter,
        series_id=series_id, subtitle_type=subtitle_type,
    )
    return jsonify(result)


@bp.route("/wanted/summary", methods=["GET"])
def wanted_summary():
    """Get aggregated wanted stats."""
    from wanted_scanner import get_scanner
    from db.wanted import get_wanted_summary, get_wanted_by_subtitle_type

    scanner = get_scanner()
    summary = get_wanted_summary()
    summary["scan_running"] = scanner.is_scanning
    summary["last_scan_at"] = scanner.last_scan_at
    summary["by_subtitle_type"] = get_wanted_by_subtitle_type()
    return jsonify(summary)


@bp.route("/wanted/refresh", methods=["POST"])
def refresh_wanted():
    """Trigger a wanted scan. Optional body: {series_id: int}"""
    from wanted_scanner import get_scanner

    scanner = get_scanner()
    if scanner.is_scanning:
        return jsonify({"error": "Scan already running"}), 409

    data = request.get_json(silent=True) or {}
    series_id = data.get("series_id")

    def _run_scan():
        if series_id:
            result = scanner.scan_series(series_id)
        else:
            result = scanner.scan_all()
        emit_event("wanted_scan_complete", result)

    thread = threading.Thread(target=_run_scan, daemon=True)
    thread.start()

    return jsonify({"status": "scan_started", "series_id": series_id}), 202


@bp.route("/wanted/<int:item_id>/status", methods=["PUT"])
def update_wanted_item_status(item_id):
    """Update a wanted item's status (e.g. ignore/un-ignore)."""
    from db.wanted import get_wanted_item, update_wanted_status

    data = request.get_json() or {}
    new_status = data.get("status")

    if new_status not in ("wanted", "ignored", "failed"):
        return jsonify({"error": "Invalid status. Use: wanted, ignored, failed"}), 400

    item = get_wanted_item(item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

    update_wanted_status(item_id, new_status, error=data.get("error", ""))
    return jsonify({"status": "updated", "id": item_id, "new_status": new_status})


@bp.route("/wanted/<int:item_id>", methods=["DELETE"])
def delete_wanted(item_id):
    """Remove a wanted item."""
    from db.wanted import get_wanted_item, delete_wanted_item

    item = get_wanted_item(item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

    delete_wanted_item(item_id)
    return jsonify({"status": "deleted", "id": item_id})


@bp.route("/wanted/<int:item_id>/search", methods=["POST"])
def search_wanted(item_id):
    """Search providers for a specific wanted item."""
    from db.wanted import get_wanted_item
    from wanted_search import search_wanted_item

    item = get_wanted_item(item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

    result = search_wanted_item(item_id)

    if result.get("error"):
        return jsonify(result), 400

    return jsonify(result)


@bp.route("/wanted/<int:item_id>/process", methods=["POST"])
def process_wanted(item_id):
    """Download + translate for a single wanted item (async)."""
    from db.wanted import get_wanted_item
    from wanted_search import process_wanted_item

    item = get_wanted_item(item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

    def _run():
        result = process_wanted_item(item_id)
        emit_event("wanted_item_processed", result)
        if result.get("upgraded"):
            emit_event("upgrade_complete", {
                "file_path": result.get("output_path"),
                "provider": result.get("provider"),
            })

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return jsonify({"status": "processing", "wanted_id": item_id}), 202


@bp.route("/wanted/batch-search", methods=["POST"])
def wanted_batch_search():
    """Process all wanted items (async with progress tracking)."""
    from db.wanted import get_wanted_count
    from wanted_search import process_wanted_batch

    with wanted_batch_lock:
        if wanted_batch_state["running"]:
            return jsonify({"error": "Wanted batch already running"}), 409

    data = request.get_json(silent=True) or {}
    item_ids = data.get("item_ids")

    # Determine total count upfront
    if item_ids:
        total = len(item_ids)
    else:
        total = get_wanted_count(status="wanted")

    with wanted_batch_lock:
        wanted_batch_state.update({
            "running": True,
            "total": total,
            "processed": 0,
            "found": 0,
            "failed": 0,
            "skipped": 0,
            "current_item": None,
        })

    def _run_batch():
        try:
            for progress in process_wanted_batch(item_ids):
                with wanted_batch_lock:
                    wanted_batch_state["processed"] = progress["processed"]
                    wanted_batch_state["found"] = progress["found"]
                    wanted_batch_state["failed"] = progress["failed"]
                    wanted_batch_state["skipped"] = progress["skipped"]
                    wanted_batch_state["current_item"] = progress["current_item"]

                socketio.emit("wanted_batch_progress", {
                    "processed": progress["processed"],
                    "total": progress["total"],
                    "found": progress["found"],
                    "failed": progress["failed"],
                    "current_item": progress["current_item"],
                })
        finally:
            with wanted_batch_lock:
                snapshot = dict(wanted_batch_state)
                wanted_batch_state["running"] = False
                wanted_batch_state["current_item"] = None

            emit_event("batch_complete", snapshot)

            try:
                from notifier import send_notification
                send_notification(
                    title="Sublarr: Wanted Batch Complete",
                    body=f"Wanted batch finished: {snapshot.get('succeeded', 0)} found, {snapshot.get('failed', 0)} failed",
                    event_type="batch_complete",
                )
            except Exception:
                pass

    thread = threading.Thread(target=_run_batch, daemon=True)
    thread.start()

    return jsonify({"status": "started", "total_items": total}), 202


@bp.route("/wanted/batch-search/status", methods=["GET"])
def wanted_batch_status():
    """Get wanted batch search progress."""
    with wanted_batch_lock:
        return jsonify(dict(wanted_batch_state))


@bp.route("/wanted/search-all", methods=["POST"])
def wanted_search_all():
    """Trigger a search-all for wanted items (provider search for all pending items)."""
    from wanted_scanner import get_scanner

    scanner = get_scanner()
    if scanner.is_searching:
        return jsonify({"error": "Search already running"}), 409

    def _run_search():
        scanner.search_all(socketio=socketio)

    thread = threading.Thread(target=_run_search, daemon=True)
    thread.start()

    return jsonify({"status": "search_started"}), 202


@bp.route("/wanted/<int:item_id>/extract", methods=["POST"])
def extract_embedded_sub(item_id):
    """Extract an embedded subtitle stream from an MKV file.

    Body: {
        "stream_index": int,  // Optional: specific stream index
        "target_language": "de"  // Optional: target language code
    }
    """
    from ass_utils import run_ffprobe, select_best_subtitle_stream, extract_subtitle_stream
    from translator import get_output_path_for_lang
    from db.wanted import get_wanted_item, delete_wanted_item
    from config import get_settings

    settings = get_settings()

    item = get_wanted_item(item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

    file_path = item.get("file_path")
    if not file_path or not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404

    if not file_path.lower().endswith(('.mkv', '.mp4', '.m4v')):
        return jsonify({"error": "File is not a video container (MKV/MP4)"}), 400

    data = request.get_json(silent=True) or {}
    target_language = data.get("target_language") or item.get("target_language") or settings.target_language

    try:
        # Get ffprobe data
        probe_data = run_ffprobe(file_path, use_cache=True)

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
                    "format": "ass" if stream.get("codec_name", "").lower() in ("ass", "ssa") else "srt",
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

        # Update wanted item if ASS was extracted
        if stream_info["format"] == "ass":
            delete_wanted_item(item_id)
            emit_event("wanted_item_processed", {
                "wanted_id": item_id,
                "status": "found",
                "output_path": output_path,
                "source": "embedded",
            })

        return jsonify({
            "status": "extracted",
            "output_path": output_path,
            "format": stream_info["format"],
            "language": stream_info.get("language", ""),
        })

    except Exception:
        raise  # Handled by global error handler
