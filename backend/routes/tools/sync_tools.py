"""Advanced sync route: /advanced-sync."""

import logging

from flask import jsonify, request

from routes.tools import bp
from routes.tools._helpers import _create_backup, _validate_file_path

logger = logging.getLogger(__name__)


def _sync_preview(subs, apply_fn, operation, **params):
    """Generate a preview of sync operation on 5 representative events.

    Returns before/after timestamps for first, 25%, 50%, 75%, last events.
    """
    non_comment = [e for e in subs.events if not e.is_comment]
    if not non_comment:
        return jsonify({"status": "preview", "operation": operation, "events": []})

    # Select 5 representative indices
    n = len(non_comment)
    indices = sorted(
        set(
            [
                0,
                max(0, n // 4),
                max(0, n // 2),
                max(0, 3 * n // 4),
                n - 1,
            ]
        )
    )

    # Capture before timestamps
    before = []
    for i in indices:
        e = non_comment[i]
        before.append({"index": i, "start": e.start, "end": e.end, "text": e.plaintext[:60]})

    # Apply operation
    apply_fn(subs)

    # Capture after timestamps
    non_comment_after = [e for e in subs.events if not e.is_comment]
    preview_events = []
    for idx, b in enumerate(before):
        i = b["index"]
        if i < len(non_comment_after):
            a = non_comment_after[i]
            preview_events.append(
                {
                    "index": i,
                    "text": b["text"],
                    "before": {"start": b["start"], "end": b["end"]},
                    "after": {"start": a.start, "end": a.end},
                }
            )

    return jsonify(
        {
            "status": "preview",
            "operation": operation,
            "events": preview_events,
            **params,
        }
    )


def _chapter_range_preview(in_range_events, offset_ms: int, cr_start: int, cr_end: int):
    """Build a preview response showing before/after timing for chapter-range events."""
    if not in_range_events:
        return jsonify(
            {
                "status": "preview",
                "operation": "offset",
                "offset_ms": offset_ms,
                "chapter_range": {"start_ms": cr_start, "end_ms": cr_end},
                "events": [],
            }
        )

    # Sample up to 5 representative events
    n = len(in_range_events)
    indices = sorted({0, n // 4, n // 2, 3 * n // 4, n - 1})
    sampled = [in_range_events[i] for i in indices]

    events = []
    for ev in sampled:
        events.append(
            {
                "index": in_range_events.index(ev),
                "text": (ev.plaintext or "")[:60],
                "before": {"start": ev.start, "end": ev.end},
                "after": {"start": ev.start + offset_ms, "end": ev.end + offset_ms},
            }
        )

    return jsonify(
        {
            "status": "preview",
            "operation": "offset",
            "offset_ms": offset_ms,
            "chapter_range": {"start_ms": cr_start, "end_ms": cr_end},
            "events": events,
        }
    )


# -- Advanced Sync --------------------------------------------------------------


@bp.route("/advanced-sync", methods=["POST"])
def advanced_sync():
    """Apply advanced sync operations (offset, speed, framerate) via pysubs2.
    ---
    post:
      tags:
        - Tools
      summary: Advanced subtitle sync
      description: Applies advanced timing sync operations to a subtitle file using pysubs2. Supports offset (ms shift), speed (playback rate adjustment), and framerate conversion. Creates a .bak backup before modifying. Supports preview mode.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - file_path
                - operation
              properties:
                file_path:
                  type: string
                  description: Path to subtitle file (must be under media_path)
                operation:
                  type: string
                  enum: [offset, speed, framerate]
                  description: Sync operation type
                offset_ms:
                  type: integer
                  description: Offset in milliseconds (for operation=offset)
                speed_factor:
                  type: number
                  description: Speed multiplier 0.5-2.0 (for operation=speed)
                in_fps:
                  type: number
                  description: Source framerate (for operation=framerate)
                out_fps:
                  type: number
                  description: Target framerate (for operation=framerate)
                preview:
                  type: boolean
                  description: If true, return preview of changes without saving
                  default: false
      responses:
        200:
          description: Sync applied or preview returned
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  operation:
                    type: string
                  events:
                    type: integer
        400:
          description: Invalid parameters
        403:
          description: File outside media_path
        404:
          description: File not found
        500:
          description: Processing error
    """
    import pysubs2

    data = request.get_json() or {}
    file_path = data.get("file_path", "")
    operation = data.get("operation", "")
    preview = data.get("preview", False)
    chapter_range = data.get("chapter_range")

    if operation not in ("offset", "speed", "framerate"):
        return jsonify({"error": "operation must be one of: offset, speed, framerate"}), 400

    error, result = _validate_file_path(file_path)
    if error:
        return jsonify({"error": error}), result

    abs_path = result

    try:
        subs = pysubs2.load(abs_path)
        event_count = len([e for e in subs.events if not e.is_comment])

        if operation == "offset":
            offset_ms = data.get("offset_ms")
            if offset_ms is None or not isinstance(offset_ms, (int, float)):
                return jsonify(
                    {"error": "offset_ms (integer) is required for offset operation"}
                ), 400
            offset_ms = int(offset_ms)

            if chapter_range:
                cr_start = chapter_range.get("start_ms")
                cr_end = chapter_range.get("end_ms")
                if not isinstance(cr_start, (int, float)) or not isinstance(cr_end, (int, float)):
                    return jsonify(
                        {"error": "chapter_range must have start_ms and end_ms integers"}
                    ), 400
                cr_start = int(cr_start)
                cr_end = int(cr_end)

                in_range = [
                    e for e in subs.events if not e.is_comment and cr_start <= e.start < cr_end
                ]

                if preview:
                    return _chapter_range_preview(in_range, offset_ms, cr_start, cr_end)

                _create_backup(abs_path)
                for event in in_range:
                    event.start += offset_ms
                    event.end += offset_ms
                subs.save(abs_path)
                logger.info(
                    "Chapter-range offset %dms [%d-%d ms] applied to %s (%d events)",
                    offset_ms,
                    cr_start,
                    cr_end,
                    abs_path,
                    len(in_range),
                )
                return jsonify(
                    {
                        "status": "synced",
                        "operation": "offset",
                        "events": len(in_range),
                        "offset_ms": offset_ms,
                        "chapter_range": {"start_ms": cr_start, "end_ms": cr_end},
                    }
                )

            if preview:
                return _sync_preview(
                    subs, lambda s: s.shift(ms=offset_ms), operation, offset_ms=offset_ms
                )

            _create_backup(abs_path)
            subs.shift(ms=offset_ms)
            subs.save(abs_path)

            logger.info("Advanced sync (offset %dms) applied to %s", offset_ms, abs_path)
            return jsonify(
                {
                    "status": "synced",
                    "operation": "offset",
                    "events": event_count,
                    "offset_ms": offset_ms,
                }
            )

        elif operation == "speed":
            speed_factor = data.get("speed_factor")
            if speed_factor is None or not isinstance(speed_factor, (int, float)):
                return jsonify(
                    {"error": "speed_factor (float) is required for speed operation"}
                ), 400
            speed_factor = float(speed_factor)
            if not (0.5 <= speed_factor <= 2.0):
                return jsonify({"error": "speed_factor must be between 0.5 and 2.0"}), 400

            def apply_speed(s):
                for event in s.events:
                    event.start = round(event.start / speed_factor)
                    event.end = round(event.end / speed_factor)

            if preview:
                return _sync_preview(subs, apply_speed, operation, speed_factor=speed_factor)

            _create_backup(abs_path)
            apply_speed(subs)
            subs.save(abs_path)

            logger.info("Advanced sync (speed %.2fx) applied to %s", speed_factor, abs_path)
            return jsonify(
                {
                    "status": "synced",
                    "operation": "speed",
                    "events": event_count,
                    "speed_factor": speed_factor,
                }
            )

        elif operation == "framerate":
            in_fps = data.get("in_fps")
            out_fps = data.get("out_fps")
            if in_fps is None or out_fps is None:
                return jsonify(
                    {"error": "in_fps and out_fps are required for framerate operation"}
                ), 400
            in_fps = float(in_fps)
            out_fps = float(out_fps)
            if in_fps <= 0 or out_fps <= 0:
                return jsonify({"error": "in_fps and out_fps must be positive"}), 400

            if preview:
                return _sync_preview(
                    subs,
                    lambda s: s.transform_framerate(in_fps, out_fps),
                    operation,
                    in_fps=in_fps,
                    out_fps=out_fps,
                )

            _create_backup(abs_path)
            subs.transform_framerate(in_fps, out_fps)
            subs.save(abs_path)

            logger.info(
                "Advanced sync (framerate %.3f->%.3f) applied to %s", in_fps, out_fps, abs_path
            )
            return jsonify(
                {
                    "status": "synced",
                    "operation": "framerate",
                    "events": event_count,
                    "in_fps": in_fps,
                    "out_fps": out_fps,
                }
            )

    except Exception as exc:
        logger.error("Advanced sync failed for %s: %s", abs_path, exc)
        return jsonify({"error": f"Advanced sync failed: {exc}"}), 500
