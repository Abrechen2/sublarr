"""Cue-level subtitle fixes: overlap-fix, timing-normalize, merge-lines, split-lines."""

import logging

from flask import jsonify, request

from routes.tools import bp
from routes.tools._helpers import _create_backup, _validate_file_path

logger = logging.getLogger(__name__)


@bp.route("/overlap-fix", methods=["POST"])
def overlap_fix():
    """Trim overlapping cue end times so consecutive cues no longer overlap.
    ---
    post:
      security:
        - apiKeyAuth: []
      summary: Fix subtitle overlaps
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [file_path]
              properties:
                file_path:
                  type: string
      responses:
        200:
          description: Overlaps fixed
          content:
            application/json:
              schema:
                type: object
                properties:
                  fixed:
                    type: integer
                  backup_path:
                    type: string
    """
    import pysubs2

    data = request.get_json(force=True, silent=True) or {}
    error, result = _validate_file_path(data.get("file_path", ""))
    if error:
        return jsonify({"error": error}), result

    abs_path = result
    try:
        bak = _create_backup(abs_path)
        subs = pysubs2.load(abs_path)
        fixed = 0
        for i in range(len(subs) - 1):
            if subs[i].end > subs[i + 1].start:
                subs[i].end = subs[i + 1].start - 1
                fixed += 1
        subs.save(abs_path)
    except Exception as exc:
        logger.error("overlap-fix failed for %s: %s", abs_path, exc)
        return jsonify({"error": f"overlap-fix failed: {exc}"}), 500

    logger.info("overlap-fix: %d overlaps fixed in %s", fixed, abs_path)
    return jsonify({"fixed": fixed, "backup_path": bak})


@bp.route("/timing-normalize", methods=["POST"])
def timing_normalize():
    """Extend too-short cues and report too-long cues.
    ---
    post:
      security:
        - apiKeyAuth: []
      summary: Normalize subtitle timing
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [file_path]
              properties:
                file_path:
                  type: string
                min_ms:
                  type: integer
                  default: 500
                max_ms:
                  type: integer
                  default: 10000
    """
    import pysubs2

    data = request.get_json(force=True, silent=True) or {}
    error, result = _validate_file_path(data.get("file_path", ""))
    if error:
        return jsonify({"error": error}), result

    abs_path = result
    min_ms = int(data.get("min_ms", 500))
    max_ms = int(data.get("max_ms", 10000))
    try:
        bak = _create_backup(abs_path)
        subs = pysubs2.load(abs_path)
        extended = too_long = 0
        for cue in subs:
            dur = cue.end - cue.start
            if dur < min_ms:
                cue.end = cue.start + min_ms
                extended += 1
            elif dur > max_ms:
                too_long += 1
        subs.save(abs_path)
    except Exception as exc:
        logger.error("timing-normalize failed for %s: %s", abs_path, exc)
        return jsonify({"error": f"timing-normalize failed: {exc}"}), 500

    logger.info("timing-normalize: extended=%d, too_long=%d in %s", extended, too_long, abs_path)
    return jsonify({"extended": extended, "too_long": too_long, "backup_path": bak})


@bp.route("/merge-lines", methods=["POST"])
def merge_lines():
    """Merge consecutive cues separated by a short gap.
    ---
    post:
      security:
        - apiKeyAuth: []
      summary: Merge consecutive subtitle lines
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [file_path]
              properties:
                file_path:
                  type: string
                gap_ms:
                  type: integer
                  default: 200
    """
    import pysubs2

    data = request.get_json(force=True, silent=True) or {}
    error, result = _validate_file_path(data.get("file_path", ""))
    if error:
        return jsonify({"error": error}), result

    abs_path = result
    gap_ms = int(data.get("gap_ms", 200))
    try:
        bak = _create_backup(abs_path)
        subs = pysubs2.load(abs_path)
        new_subs = pysubs2.SSAFile()
        new_subs.styles = subs.styles
        merged = 0
        i = 0
        while i < len(subs):
            cue = subs[i]
            while i + 1 < len(subs) and subs[i + 1].start - cue.end <= gap_ms:
                cue = pysubs2.SSAEvent(
                    start=cue.start,
                    end=subs[i + 1].end,
                    text=cue.text + r"\N" + subs[i + 1].text,
                )
                i += 1
                merged += 1
            new_subs.append(cue)
            i += 1
        new_subs.save(abs_path)
    except Exception as exc:
        logger.error("merge-lines failed for %s: %s", abs_path, exc)
        return jsonify({"error": f"merge-lines failed: {exc}"}), 500

    logger.info("merge-lines: %d merges in %s", merged, abs_path)
    return jsonify({"merged": merged, "backup_path": bak})


@bp.route("/split-lines", methods=["POST"])
def split_lines():
    r"""Split cues containing \N or exceeding max_chars at natural boundaries.
    ---
    post:
      security:
        - apiKeyAuth: []
      summary: Split long subtitle lines
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [file_path]
              properties:
                file_path:
                  type: string
                max_chars:
                  type: integer
                  default: 80
    """
    import pysubs2

    data = request.get_json(force=True, silent=True) or {}
    error, result = _validate_file_path(data.get("file_path", ""))
    if error:
        return jsonify({"error": error}), result

    abs_path = result
    max_chars = int(data.get("max_chars", 80))
    try:
        bak = _create_backup(abs_path)
        subs = pysubs2.load(abs_path)
        new_subs = pysubs2.SSAFile()
        new_subs.styles = subs.styles
        split_count = 0

        for cue in subs:
            parts = cue.text.split(r"\N")
            if len(parts) <= 1 and len(cue.text) <= max_chars:
                new_subs.append(cue)
                continue
            dur = cue.end - cue.start
            per_part = dur // max(len(parts), 1)
            for idx, part in enumerate(parts):
                new_subs.append(
                    pysubs2.SSAEvent(
                        start=cue.start + idx * per_part,
                        end=cue.start + (idx + 1) * per_part,
                        text=part.strip(),
                    )
                )
            split_count += 1

        new_subs.save(abs_path)
    except Exception as exc:
        logger.error("split-lines failed for %s: %s", abs_path, exc)
        return jsonify({"error": f"split-lines failed: {exc}"}), 500

    logger.info("split-lines: %d splits in %s", split_count, abs_path)
    return jsonify({"split": split_count, "backup_path": bak})
