"""Wanted single-extract route + _extract_embedded_sub helper used by the scanner."""

import logging
import os
import threading

from flask import jsonify

from db.activity import log_activity
from db.models.activity import EVENT_EXTRACT
from events import emit_event
from remux import RemuxError, remove_subtitle_stream
from routes.wanted import bp

logger = logging.getLogger(__name__)


def _remove_stream_from_container(file_path: str, stream_info: dict) -> None:
    """Remove a subtitle stream from the video container after extraction.

    Non-fatal: logs a warning and continues if the remux fails.
    """
    global_idx = stream_info.get("stream_index")
    sub_idx = stream_info.get("sub_index", 0)

    if global_idx is None:
        logger.warning(
            "Cannot remove stream from %s: stream_index missing in stream_info", file_path
        )
        return

    try:
        from config import get_settings

        settings = get_settings()
        bak = remove_subtitle_stream(
            video_path=file_path,
            stream_index=global_idx,
            subtitle_track_index=sub_idx,
            use_reflink=getattr(settings, "remux_use_reflink", True),
            trash_dir=getattr(settings, "remux_trash_dir", ".sublarr"),
        )
        logger.info("Removed subtitle stream %d from %s (backup: %s)", global_idx, file_path, bak)
    except RemuxError as exc:
        logger.warning("Could not remove subtitle stream from %s: %s", file_path, exc)
    except Exception as exc:
        logger.warning("Unexpected error removing stream from %s: %s", file_path, exc)


def _extract_embedded_sub(item_id: int, file_path: str, auto_translate: bool = False) -> dict:
    """Standalone helper: extract embedded subtitles for a wanted item.

    Callable from outside a Flask request context (e.g. from the scanner).
    Returns a result dict with keys: status, output_path, format, language.
    Raises on hard errors; caller is responsible for exception handling.

    Behaviour (rev. with shared embedded_extractor pipeline):
      - Extracts EVERY text-based subtitle stream the container offers,
        not just the "best" one. Image subtitles (PGS/VobSub) are skipped.
      - Removes all extracted streams from the container in a single
        mkvmerge pass with a backup in ``remux_trash_dir`` (recoverable).
      - Trashes any sidecar whose language is not in the wanted item's
        profile target_languages — also into ``remux_trash_dir``.
      - Returns the "primary" sidecar (the target-lang match, falling
        back to the first extracted file) so existing callers keep
        receiving a single output_path/format/language.

    Args:
        item_id: ID of the wanted item.
        file_path: Absolute path to the media file.
        auto_translate: If True, trigger translation of the primary
            extracted SRT after extraction. Translation is a Beta-gated
            feature in production; the scheduler-driven drain passes
            False so it stays manual.
    """
    from ass_utils import get_media_streams
    from config import get_settings
    from db.wanted import get_wanted_item, update_existing_sub, update_wanted_status
    from services.embedded_extractor import (
        compute_keep_langs,
        extract_and_cleanup,
        resolve_profile_for_item,
    )

    settings = get_settings()

    item = get_wanted_item(item_id)
    if not item:
        raise ValueError(f"Wanted item {item_id} not found")

    if not file_path or not os.path.exists(file_path):
        raise FileNotFoundError(f"Media file not found: {file_path}")

    if not file_path.lower().endswith((".mkv", ".mp4", ".m4v")):
        raise ValueError(f"File is not a video container (MKV/MP4): {file_path}")

    target_language = item.get("target_language") or settings.target_language

    # Resolve which languages the per-series / per-movie profile asks
    # us to keep. Sidecars in other languages get moved to the trash dir
    # after the extract pass so the user only retains what they want —
    # everything is recoverable via the trash UI.
    profile = resolve_profile_for_item(item, settings)
    keep_langs = compute_keep_langs(profile, settings)

    probe_data = get_media_streams(file_path, use_cache=True)

    result = extract_and_cleanup(
        file_path=file_path,
        probe_data=probe_data,
        keep_langs=keep_langs,
        target_language=target_language,
        log_label=f"auto-extract item {item_id}",
    )

    if not result.any_extracted or result.primary_output_path is None:
        raise LookupError(f"No suitable subtitle stream found in {file_path}")

    output_path = result.primary_output_path
    primary_format = result.primary_format or "srt"

    # Plan B5 — run repair on the primary extracted track (opt-outable).
    # Fixes BOM, newlines, invalid decimals, overlapping cues, encoding
    # mis-detection. Must never abort extraction — fall through on any error.
    try:
        if getattr(settings, "enable_subtitle_repair", True):
            from pathlib import Path as _RepairPath

            from subtitle_repair import repair_bytes as _repair_bytes

            _ext = _RepairPath(output_path).suffix.lstrip(".") or "srt"
            _data = _RepairPath(output_path).read_bytes()
            _repaired = _repair_bytes(_data, fmt=_ext)
            if _repaired != _data:
                _RepairPath(output_path).write_bytes(_repaired)
    except Exception as _repair_err:
        logger.warning(
            "subtitle_repair on embedded extract skipped for %s: %s",
            output_path,
            _repair_err,
        )

    # Mark item as extracted — keep visible in Wanted for user-initiated cleanup/translate
    update_existing_sub(item_id, primary_format)
    update_wanted_status(item_id, "extracted")
    emit_event(
        "wanted_item_processed",
        {
            "wanted_id": item_id,
            "status": "extracted",
            "output_path": output_path,
            "source": "embedded",
            "extracted_count": len(result.extracted),
            "sidecars_trashed": result.sidecars_trashed,
        },
    )

    log_activity(
        EVENT_EXTRACT,
        file_path=str(file_path),
        status="success",
        details={
            "format": primary_format,
            "output_path": output_path,
            "wanted_id": item_id,
            "extracted_count": len(result.extracted),
            "sidecars_trashed": result.sidecars_trashed,
        },
    )

    if auto_translate and primary_format == "srt":
        # Trigger translation of the primary extracted SRT in a background thread
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
        "format": primary_format,
        "language": result.primary_language or "",
        "extracted_count": len(result.extracted),
        "sidecars_trashed": result.sidecars_trashed,
    }


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
    from db.wanted import get_wanted_item

    item = get_wanted_item(item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

    file_path = item.get("file_path")
    if not file_path or not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404

    if not file_path.lower().endswith((".mkv", ".mp4", ".m4v")):
        return jsonify({"error": "File is not a video container (MKV/MP4)"}), 400

    # Delegate to the shared embedded_extractor pipeline so the single-item
    # route, the auto-extract drain, and the batch-probe pipeline all share
    # the same extract-everything-then-trash-non-target semantics. The legacy
    # request fields (`stream_index`, `target_language`) are silently ignored:
    # the new pipeline extracts every text-based stream and labels each
    # sidecar by the stream's actual language, not by the wanted item's
    # target — picking a single stream is no longer a meaningful operation.
    try:
        result = _extract_embedded_sub(item_id, file_path, auto_translate=False)
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except LookupError as exc:
        return jsonify({"error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(result)
