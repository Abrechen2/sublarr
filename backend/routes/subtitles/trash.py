"""Trash management: soft-delete, batch-delete, list/restore/purge."""

from __future__ import annotations

import logging
import os
import shutil
import uuid
from datetime import datetime

from flask import jsonify, request

from config import get_settings, map_path
from db.activity import log_activity
from db.models.activity import EVENT_DELETE
from routes.subtitles import bp
from routes.subtitles.helpers import (
    _auto_purge_old_trash,
    _get_batch_dir,
    _get_trash_root,
    _read_manifest,
    _trash_sidecar,
    _write_manifest,
    scan_subtitle_sidecars,
)

logger = logging.getLogger(__name__)


@bp.route("/library/subtitles", methods=["DELETE"])
def delete_subtitles():
    """Move one or more subtitle sidecar files to trash (soft-delete).

    Body: { "paths": ["/abs/path/to/file.de.ass", ...], "blacklist": false }
    Set blacklist=true to also add each subtitle to the blacklist (looks up
    provider/subtitle_id from subtitle_downloads; silent-fail if not found).
    Response: { "batch_id": "...", "deleted": [...], "failed": [...] }

    Use POST /library/trash/{batch_id}/restore to undo.
    Security: only files inside SUBLARR_MEDIA_PATH with subtitle extensions are allowed.
    """
    body = request.get_json(force=True, silent=True) or {}
    paths = body.get("paths", [])
    do_blacklist = bool(body.get("blacklist", False))
    if not isinstance(paths, list) or not paths:
        return jsonify({"error": "paths must be a non-empty list"}), 400

    settings = get_settings()
    media_path = getattr(settings, "media_path", "/media")
    retention = getattr(settings, "subtitle_trash_retention_days", 7)
    _auto_purge_old_trash(media_path, retention)

    batch_id = uuid.uuid4().hex
    batch_dir = _get_batch_dir(media_path, batch_id)

    deleted: list[str] = []
    failed: list[dict] = []
    manifest_files: list[dict] = []

    for path in paths:
        if not isinstance(path, str):
            failed.append({"path": str(path), "error": "Invalid path type"})
            continue

        if do_blacklist:
            from db.blacklist import blacklist_subtitle_sidecar

            blacklist_subtitle_sidecar(path)

        trash_path, err = _trash_sidecar(path, media_path, batch_dir)
        if err:
            failed.append({"path": path, "error": err})
            log_activity(
                EVENT_DELETE,
                file_path=path,
                status="failed",
                details={"error": err, "batch_id": batch_id},
            )
        else:
            deleted.append(path)
            manifest_files.append({"original": path, "trashed": trash_path})
            log_activity(
                EVENT_DELETE,
                file_path=path,
                status="success",
                details={"trash_path": trash_path, "batch_id": batch_id},
            )

    if manifest_files:
        _write_manifest(batch_dir, batch_id, manifest_files)

    return jsonify({"batch_id": batch_id, "deleted": deleted, "failed": failed}), 200


@bp.route("/library/series/<int:series_id>/subtitles/batch-delete", methods=["POST"])
def batch_delete_series_subtitles(series_id: int):
    """Move subtitle sidecars for a series to trash, filtered by language and/or format.

    Body: { "languages": ["chi", "jpn", "rus"], "formats": ["srt"] }
    "languages" = list of language codes TO DELETE (not to keep).
    Omit a key to match all values for that dimension.
    Response: { "batch_id": "...", "deleted": N, "failed": N }

    Use POST /library/trash/{batch_id}/restore to undo.
    """
    from sonarr_client import get_sonarr_client

    body = request.get_json(force=True, silent=True) or {}
    # languages/formats = the ones TO DELETE (empty/absent = delete all)
    # Normalise to lowercase so filenames like "DE" match request value "de"
    delete_languages: set[str] | None = (
        {l.lower() for l in body["languages"]} if body.get("languages") else None
    )
    delete_formats: set[str] | None = (
        {f.lower() for f in body["formats"]} if body.get("formats") else None
    )

    client = get_sonarr_client()

    # Collect video file paths — via Sonarr or standalone DB
    video_paths: list[str] = []
    if client is None:
        from sqlalchemy import text

        from db import get_db
        from db.standalone import get_standalone_series

        if get_standalone_series(series_id) is None:
            return jsonify({"error": "Sonarr not configured"}), 503

        db = get_db()
        rows = db.execute(
            text("SELECT file_path FROM wanted_items WHERE standalone_series_id=:sid"),
            {"sid": series_id},
        ).fetchall()
        video_paths = [row.file_path for row in rows if row.file_path]
    else:
        episode_files = client.get_episode_files_by_series(series_id)
        for file_info in (episode_files or {}).values():
            raw_path = file_info.get("path")
            if raw_path:
                video_paths.append(map_path(raw_path))

    if not video_paths:
        return jsonify({"batch_id": None, "deleted": 0, "failed": 0}), 200

    settings = get_settings()
    media_path = getattr(settings, "media_path", "/media")
    retention = getattr(settings, "subtitle_trash_retention_days", 7)
    _auto_purge_old_trash(media_path, retention)

    batch_id = uuid.uuid4().hex
    batch_dir = _get_batch_dir(media_path, batch_id)

    deleted_count = 0
    failed_count = 0
    manifest_files: list[dict] = []

    for video_path in video_paths:
        if not os.path.exists(video_path):
            continue

        sidecars = scan_subtitle_sidecars(video_path)
        for sidecar in sidecars:
            lang = sidecar["language"].lower()
            fmt = sidecar["format"].lower()

            if delete_languages is not None and lang not in delete_languages:
                continue
            if delete_formats is not None and fmt not in delete_formats:
                continue

            trash_path, err = _trash_sidecar(sidecar["path"], media_path, batch_dir)
            if err:
                logger.warning("batch-delete: could not trash %s: %s", sidecar["path"], err)
                failed_count += 1
            else:
                manifest_files.append({"original": sidecar["path"], "trashed": trash_path})
                deleted_count += 1

    if manifest_files:
        _write_manifest(batch_dir, batch_id, manifest_files)

    return jsonify({"batch_id": batch_id, "deleted": deleted_count, "failed": failed_count}), 200


@bp.route("/library/trash", methods=["GET"])
def list_trash():
    """List all trash batches with file count, total size, and context.

    Response: { "batches": [{ batch_id, created_at, expires_at,
                               file_count, size_bytes, series_name, language }] }
    """
    settings = get_settings()
    media_path = getattr(settings, "media_path", "/media")
    retention = getattr(settings, "subtitle_trash_retention_days", 30)
    _auto_purge_old_trash(media_path, retention)

    trash_root = _get_trash_root(media_path)
    if not os.path.isdir(trash_root):
        return jsonify({"batches": []}), 200

    batches = []
    for entry in os.scandir(trash_root):
        if not entry.is_dir():
            continue
        manifest = _read_manifest(entry.path)
        if manifest is None:
            continue
        files = manifest.get("files", [])
        total_bytes = 0
        for f in files:
            try:
                total_bytes += os.path.getsize(f["trashed"])
            except OSError:
                pass

        created_at = manifest.get("created_at")
        expires_at = None
        if created_at and retention > 0:
            try:
                from datetime import timedelta

                expires_dt = datetime.fromisoformat(created_at) + timedelta(days=retention)
                expires_at = expires_dt.isoformat()
            except (ValueError, TypeError):
                pass

        batches.append(
            {
                "batch_id": manifest["batch_id"],
                "created_at": created_at,
                "expires_at": expires_at,
                "file_count": len(files),
                "size_bytes": total_bytes,
                "series_name": manifest.get("series_name", ""),
                "language": manifest.get("language", ""),
                "files": [f.get("original", "") for f in files],
            }
        )

    batches.sort(key=lambda b: b.get("created_at") or "", reverse=True)
    return jsonify({"batches": batches}), 200


@bp.route("/library/trash/<batch_id>/restore", methods=["POST"])
def restore_trash_batch(batch_id: str):
    """Restore all files from a trash batch to their original locations.

    Response: { "restored": N, "failed": N }
    """
    if not batch_id.isalnum():
        return jsonify({"error": "Invalid batch_id"}), 400

    settings = get_settings()
    media_path = getattr(settings, "media_path", "/media")
    batch_dir = _get_batch_dir(media_path, batch_id)

    manifest = _read_manifest(batch_dir)
    if manifest is None:
        return jsonify({"error": "Batch not found"}), 404

    restored = 0
    failed = 0

    for f in manifest.get("files", []):
        trashed = f.get("trashed")
        original = f.get("original")
        if not trashed or not original:
            failed += 1
            continue
        if not os.path.exists(trashed):
            logger.warning("restore: trashed file missing: %s", trashed)
            failed += 1
            continue
        # Restore: create parent dirs if needed
        try:
            os.makedirs(os.path.dirname(original), exist_ok=True)
            shutil.move(trashed, original)
            restored += 1
        except OSError as exc:
            logger.warning("restore: failed to move %s -> %s: %s", trashed, original, exc)
            failed += 1
            continue

        # Restore .quality.json sidecar if it was trashed
        quality_trashed = trashed + ".quality.json"
        if os.path.exists(quality_trashed):
            try:
                shutil.move(quality_trashed, original + ".quality.json")
            except OSError:
                pass

    # Remove batch dir if fully restored
    if failed == 0:
        try:
            shutil.rmtree(batch_dir)
        except OSError:
            pass

    return jsonify({"restored": restored, "failed": failed}), 200


@bp.route("/library/trash/<batch_id>", methods=["DELETE"])
def purge_trash_batch(batch_id: str):
    """Permanently delete all files in a trash batch (cannot be undone).

    Response: { "purged": N }
    """
    if not batch_id.isalnum():
        return jsonify({"error": "Invalid batch_id"}), 400

    settings = get_settings()
    media_path = getattr(settings, "media_path", "/media")
    batch_dir = _get_batch_dir(media_path, batch_id)

    if not os.path.isdir(batch_dir):
        return jsonify({"error": "Batch not found"}), 404

    manifest = _read_manifest(batch_dir)
    file_count = len(manifest.get("files", [])) if manifest else 0

    try:
        shutil.rmtree(batch_dir)
    except OSError as exc:
        return jsonify({"error": str(exc)}), 500

    return jsonify({"purged": file_count}), 200
