"""Wanted single-extract route + compat shims for the extraction helper.

The actual implementation of ``_extract_embedded_sub`` moved to
``services.embedded_extractor.extract_embedded_sub`` (2026-07-02) so the
services layer no longer imports from routes. The shims below preserve
the historical names — route code and tests patch
``routes.wanted.extract._extract_embedded_sub``.
"""

import logging
import os

from flask import jsonify

from remux import RemuxError, remove_subtitle_stream
from routes.wanted import bp

logger = logging.getLogger(__name__)


def _validate_extract_target(file_path: str) -> str | None:
    """Compat shim — implementation moved to
    :func:`services.embedded_extractor.validate_extract_target`."""
    from services.embedded_extractor import validate_extract_target

    return validate_extract_target(file_path)


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
    """Compat shim — implementation moved to
    :func:`services.embedded_extractor.extract_embedded_sub`.

    Kept so route code and tests that patch
    ``routes.wanted.extract._extract_embedded_sub`` keep working. The
    import is lazy and aliased because this module also defines a Flask
    view named ``extract_embedded_sub``.
    """
    from services.embedded_extractor import extract_embedded_sub as _impl

    return _impl(item_id, file_path, auto_translate=auto_translate)


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
