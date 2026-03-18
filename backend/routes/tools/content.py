"""Subtitle content routes: preview, content GET/PUT, backup."""

import logging
import os

from flask import jsonify, request

from routes.tools import bp
from routes.tools._helpers import _create_backup, _validate_file_path

logger = logging.getLogger(__name__)


# -- Preview --------------------------------------------------------------------


@bp.route("/preview", methods=["GET"])
def preview_file():
    """Preview the first 100 lines of a subtitle file.
    ---
    get:
      tags:
        - Tools
      summary: Preview subtitle file
      description: Returns the first 100 lines of a subtitle file with encoding detection.
      parameters:
        - in: query
          name: file_path
          required: true
          schema:
            type: string
          description: Path to subtitle file (must be under media_path)
      responses:
        200:
          description: File preview
          content:
            application/json:
              schema:
                type: object
                properties:
                  format:
                    type: string
                    enum: [ass, srt]
                  lines:
                    type: array
                    items:
                      type: string
                  total_lines:
                    type: integer
                  encoding:
                    type: string
        400:
          description: Invalid file path or unsupported format
        403:
          description: File outside media_path
        404:
          description: File not found
        500:
          description: Processing error
    """
    file_path = request.args.get("file_path", "")

    error, result = _validate_file_path(file_path)
    if error:
        return jsonify({"error": error}), result

    abs_path = result

    try:
        # Detect encoding
        detected_encoding = "utf-8"
        try:
            import chardet

            with open(abs_path, "rb") as f:
                raw = f.read(4096)
            det = chardet.detect(raw)
            detected_encoding = det.get("encoding", "utf-8") or "utf-8"
        except ImportError:
            pass

        with open(abs_path, encoding=detected_encoding, errors="replace") as f:
            all_lines = f.readlines()

        total_lines = len(all_lines)
        preview_lines = [line.rstrip("\n\r") for line in all_lines[:100]]

        ext = os.path.splitext(abs_path)[1].lower()
        fmt = "ass" if ext in (".ass", ".ssa") else "srt"

        return jsonify(
            {
                "format": fmt,
                "lines": preview_lines,
                "total_lines": total_lines,
                "encoding": detected_encoding,
            }
        )

    except Exception as exc:
        logger.error("Preview failed for %s: %s", abs_path, exc)
        return jsonify({"error": f"Preview failed: {exc}"}), 500


# -- Content (Full Read/Write for Editor) --------------------------------------


@bp.route("/content", methods=["GET"])
def get_file_content():
    """Read full subtitle file content for editing.
    ---
    get:
      tags:
        - Tools
      summary: Read full subtitle content
      description: Returns the complete content of a subtitle file with encoding detection and metadata. Used by the subtitle editor for full file loading.
      parameters:
        - in: query
          name: file_path
          required: true
          schema:
            type: string
          description: Path to subtitle file (must be under media_path)
      responses:
        200:
          description: Full file content
          content:
            application/json:
              schema:
                type: object
                properties:
                  format:
                    type: string
                    enum: [ass, srt]
                  content:
                    type: string
                  encoding:
                    type: string
                  size_bytes:
                    type: integer
                  total_lines:
                    type: integer
                  last_modified:
                    type: number
                    description: File modification time (for optimistic concurrency)
        400:
          description: Invalid file path or unsupported format
        403:
          description: File outside media_path
        404:
          description: File not found
        500:
          description: Processing error
    """
    file_path = request.args.get("file_path", "")

    error, result = _validate_file_path(file_path)
    if error:
        return jsonify({"error": error}), result

    abs_path = result

    try:
        # Detect encoding
        detected_encoding = "utf-8"
        try:
            import chardet

            with open(abs_path, "rb") as f:
                raw = f.read()
            det = chardet.detect(raw)
            detected_encoding = det.get("encoding", "utf-8") or "utf-8"
        except ImportError:
            pass

        with open(abs_path, encoding=detected_encoding, errors="replace") as f:
            content = f.read()

        ext = os.path.splitext(abs_path)[1].lower()
        fmt = "ass" if ext in (".ass", ".ssa") else "srt"

        return jsonify(
            {
                "format": fmt,
                "content": content,
                "encoding": detected_encoding,
                "size_bytes": os.path.getsize(abs_path),
                "total_lines": len(content.splitlines()),
                "last_modified": os.path.getmtime(abs_path),
            }
        )

    except Exception as exc:
        logger.error("Content read failed for %s: %s", abs_path, exc)
        return jsonify({"error": f"Content read failed: {exc}"}), 500


@bp.route("/content", methods=["PUT"])
def save_file_content():
    """Save edited subtitle content with optimistic concurrency check.
    ---
    put:
      tags:
        - Tools
      summary: Save edited subtitle content
      description: Saves edited subtitle content after creating a .bak backup. Checks last_modified for optimistic concurrency -- returns 409 if the file was modified since it was loaded.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - file_path
                - content
                - last_modified
              properties:
                file_path:
                  type: string
                  description: Path to subtitle file (must be under media_path)
                content:
                  type: string
                  description: Full edited file content
                last_modified:
                  type: number
                  description: last_modified value from GET /content response
      responses:
        200:
          description: File saved successfully
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  backup_path:
                    type: string
                  new_mtime:
                    type: number
        400:
          description: Invalid parameters
        403:
          description: File outside media_path
        404:
          description: File not found
        409:
          description: File modified since loaded (optimistic concurrency conflict)
        500:
          description: Save error
    """
    data = request.get_json() or {}
    file_path = data.get("file_path", "")
    content = data.get("content")
    last_modified = data.get("last_modified")

    if content is None:
        return jsonify({"error": "content is required"}), 400
    if last_modified is None:
        return jsonify({"error": "last_modified is required"}), 400

    error, result = _validate_file_path(file_path)
    if error:
        return jsonify({"error": error}), result

    abs_path = result

    try:
        # Optimistic concurrency: check if file was modified since loaded
        current_mtime = os.path.getmtime(abs_path)
        if abs(current_mtime - float(last_modified)) > 0.01:
            return jsonify(
                {
                    "error": "File has been modified since you loaded it",
                    "current_mtime": current_mtime,
                }
            ), 409

        # Create backup BEFORE writing (mandatory -- project safety rule)
        bak_path = _create_backup(abs_path)

        # Write content as UTF-8
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)

        new_mtime = os.path.getmtime(abs_path)

        logger.info("Content saved: %s (backup: %s)", abs_path, bak_path)

        return jsonify(
            {
                "status": "saved",
                "backup_path": bak_path,
                "new_mtime": new_mtime,
            }
        )

    except Exception as exc:
        logger.error("Content save failed for %s: %s", abs_path, exc)
        return jsonify({"error": f"Content save failed: {exc}"}), 500


# -- Backup Content (for Diff View) --------------------------------------------


@bp.route("/backup", methods=["GET"])
def get_backup_content():
    """Read backup file content for diff comparison.
    ---
    get:
      tags:
        - Tools
      summary: Read backup file content
      description: Returns the content of the .bak backup file for the given original file path. Used for diff view in the subtitle editor.
      parameters:
        - in: query
          name: file_path
          required: true
          schema:
            type: string
          description: Path to the ORIGINAL subtitle file (not the .bak path)
      responses:
        200:
          description: Backup content
          content:
            application/json:
              schema:
                type: object
                properties:
                  content:
                    type: string
                  encoding:
                    type: string
                  backup_path:
                    type: string
        400:
          description: Invalid file path or unsupported format
        403:
          description: File outside media_path
        404:
          description: Original file or backup not found
        500:
          description: Read error
    """
    file_path = request.args.get("file_path", "")

    error, result = _validate_file_path(file_path)
    if error:
        return jsonify({"error": error}), result

    abs_path = result

    try:
        # Compute backup path (same logic as _create_backup)
        base, ext = os.path.splitext(abs_path)
        bak_path = f"{base}.bak{ext}"

        if not os.path.exists(bak_path):
            return jsonify({"error": f"No backup found for {file_path}"}), 404

        # Detect encoding of backup file
        detected_encoding = "utf-8"
        try:
            import chardet

            with open(bak_path, "rb") as f:
                raw = f.read()
            det = chardet.detect(raw)
            detected_encoding = det.get("encoding", "utf-8") or "utf-8"
        except ImportError:
            pass

        with open(bak_path, encoding=detected_encoding, errors="replace") as f:
            content = f.read()

        return jsonify(
            {
                "content": content,
                "encoding": detected_encoding,
                "backup_path": bak_path,
            }
        )

    except Exception as exc:
        logger.error("Backup read failed for %s: %s", abs_path, exc)
        return jsonify({"error": f"Backup read failed: {exc}"}), 500
