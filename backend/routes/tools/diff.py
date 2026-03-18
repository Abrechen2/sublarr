"""Subtitle diff routes: diff, diff/apply."""

import logging
import os
import shutil
import tempfile

from flask import jsonify, request

from routes.tools import bp
from security_utils import is_safe_path

logger = logging.getLogger(__name__)


@bp.route("/diff", methods=["POST"])
def compute_diff():
    """Compute a cue-level diff between two subtitle file contents.
    ---
    post:
      summary: Diff two subtitle files
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [original, modified]
              properties:
                original:
                  type: string
                  description: Original subtitle file content (ASS/SRT string)
                modified:
                  type: string
                  description: Modified subtitle file content (ASS/SRT string)
      responses:
        200:
          description: Diff result
          content:
            application/json:
              schema:
                type: object
                properties:
                  diffs:
                    type: array
                  total:
                    type: integer
                  changed:
                    type: integer
        400:
          description: Missing required field
    """
    import difflib

    import pysubs2

    def _cue_to_dict(event):
        return {
            "start": event.start / 1000.0,
            "end": event.end / 1000.0,
            "text": event.plaintext,
            "style": event.style,
        }

    data = request.get_json() or {}
    original_content = data.get("original", "")
    modified_content = data.get("modified", "")

    if not original_content:
        return jsonify({"error": "original content is required"}), 400
    if not modified_content:
        return jsonify({"error": "modified content is required"}), 400

    try:
        orig_subs = pysubs2.SSAFile.from_string(original_content)
        mod_subs = pysubs2.SSAFile.from_string(modified_content)
    except Exception as exc:
        return jsonify({"error": f"Failed to parse subtitle content: {exc}"}), 400

    orig_events = [e for e in orig_subs.events if e.type == "Dialogue"]
    mod_events = [e for e in mod_subs.events if e.type == "Dialogue"]

    matcher = difflib.SequenceMatcher(
        None,
        [e.plaintext for e in orig_events],
        [e.plaintext for e in mod_events],
        autojunk=False,
    )

    diffs = []
    changed = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                diffs.append(
                    {
                        "type": "unchanged",
                        "original": _cue_to_dict(orig_events[i1 + k]),
                        "modified": _cue_to_dict(mod_events[j1 + k]),
                    }
                )
        elif tag == "replace":
            orig_slice = orig_events[i1:i2]
            mod_slice = mod_events[j1:j2]
            for k in range(max(len(orig_slice), len(mod_slice))):
                orig_cue = _cue_to_dict(orig_slice[k]) if k < len(orig_slice) else None
                mod_cue = _cue_to_dict(mod_slice[k]) if k < len(mod_slice) else None
                diffs.append({"type": "modified", "original": orig_cue, "modified": mod_cue})
                changed += 1
        elif tag == "delete":
            for k in range(i1, i2):
                diffs.append(
                    {"type": "removed", "original": _cue_to_dict(orig_events[k]), "modified": None}
                )
                changed += 1
        elif tag == "insert":
            for k in range(j1, j2):
                diffs.append(
                    {"type": "added", "original": None, "modified": _cue_to_dict(mod_events[k])}
                )
                changed += 1

    return jsonify({"diffs": diffs, "total": len(diffs), "changed": changed})


@bp.route("/diff/apply", methods=["POST"])
def apply_diff():
    """Apply a selective diff to a subtitle file on disk.

    Accepts original and modified subtitle content plus a list of diff indices
    to reject.  All non-rejected changes from *modified* are written back to
    *file_path* using an atomic tempfile + os.replace.  A .bak backup is
    created before the write.
    ---
    post:
      summary: Apply diff to subtitle file
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [file_path, original, modified, rejected_indices]
              properties:
                file_path:
                  type: string
                original:
                  type: string
                modified:
                  type: string
                rejected_indices:
                  type: array
                  items:
                    type: integer
      responses:
        200:
          description: Applied successfully
        400:
          description: Missing or malformed input
        403:
          description: Path traversal denied
        404:
          description: File not found
    """
    import difflib

    import pysubs2

    from config import get_settings

    data = request.get_json() or {}
    file_path = data.get("file_path", "")
    original_content = data.get("original", "")
    modified_content = data.get("modified", "")
    rejected_indices = data.get("rejected_indices") or []

    if not file_path:
        return jsonify({"error": "file_path is required"}), 400
    if not original_content:
        return jsonify({"error": "original content is required"}), 400
    if not modified_content:
        return jsonify({"error": "modified content is required"}), 400

    settings = get_settings()
    abs_path = os.path.abspath(file_path)
    if not is_safe_path(abs_path, settings.media_path):
        return jsonify({"error": "Access denied"}), 403
    if not os.path.isfile(abs_path):
        return jsonify({"error": "File not found"}), 404

    try:
        orig_subs = pysubs2.SSAFile.from_string(original_content)
        mod_subs = pysubs2.SSAFile.from_string(modified_content)
    except Exception as exc:
        return jsonify({"error": f"Failed to parse subtitle content: {exc}"}), 400

    orig_events = [e for e in orig_subs.events if e.type == "Dialogue"]
    mod_events = [e for e in mod_subs.events if e.type == "Dialogue"]

    matcher = difflib.SequenceMatcher(
        None,
        [e.plaintext for e in orig_events],
        [e.plaintext for e in mod_events],
        autojunk=False,
    )

    new_events = []
    diff_index = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                new_events.append(mod_events[j1 + k])
        elif tag == "replace":
            orig_slice = orig_events[i1:i2]
            mod_slice = mod_events[j1:j2]
            for k in range(max(len(orig_slice), len(mod_slice))):
                if diff_index in rejected_indices:
                    if k < len(orig_slice):
                        new_events.append(orig_slice[k])
                else:
                    if k < len(mod_slice):
                        new_events.append(mod_slice[k])
                diff_index += 1
        elif tag == "delete":
            for k in range(i1, i2):
                if diff_index in rejected_indices:
                    new_events.append(orig_events[k])
                diff_index += 1
        elif tag == "insert":
            for k in range(j1, j2):
                if diff_index not in rejected_indices:
                    new_events.append(mod_events[k])
                diff_index += 1

    # Build a new SSAFile — never mutate mod_subs directly
    result_subs = pysubs2.SSAFile()
    result_subs.info = mod_subs.info
    result_subs.styles = mod_subs.styles
    result_subs.events = new_events

    # Determine output format from file extension
    ext = os.path.splitext(abs_path)[1].lower().lstrip(".")
    out_format = ext if ext in ("ass", "srt", "vtt") else "ass"
    encode = "utf-8-sig" if out_format == "ass" else "utf-8"

    # Create .bak backup before overwriting
    bak_path = abs_path + ".bak"
    shutil.copy2(abs_path, bak_path)

    # Atomic write via tempfile + os.replace
    tmp_fd, tmp_path_str = tempfile.mkstemp(dir=os.path.dirname(abs_path), suffix=f".{out_format}")
    try:
        with os.fdopen(tmp_fd, "w", encoding=encode) as fh:
            fh.write(result_subs.to_string(out_format))
        os.replace(tmp_path_str, abs_path)
    except Exception:
        os.unlink(tmp_path_str)
        raise

    return jsonify({"status": "applied", "file_path": abs_path, "backup": bak_path})
