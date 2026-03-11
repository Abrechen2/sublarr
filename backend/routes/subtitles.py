"""Subtitle sidecar management routes.

Provides filesystem-based discovery, soft-deletion (trash), and restore of
subtitle sidecar files (.lang.ass, .lang.srt, etc.) next to video files.

Endpoints:
  GET  /library/episodes/<ep_id>/subtitles              — sidecars for one episode
  GET  /library/series/<series_id>/subtitles            — sidecars for all episodes in a series
  DELETE /library/subtitles                             — move one or more sidecar files to trash
  POST /library/series/<series_id>/subtitles/batch-delete — batch-trash by language/format filter
  GET  /library/trash                                   — list all trash batches
  POST /library/trash/<batch_id>/restore                — restore a batch
  DELETE /library/trash/<batch_id>                      — permanently delete a batch
  GET  /subtitles/download?path=                        — download a subtitle file by path
"""

import glob as _glob
import io
import json
import logging
import os
import shutil
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

from flask import Blueprint, jsonify, request, send_file

from config import get_settings, map_path
from security_utils import is_safe_path

bp = Blueprint("subtitles", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)

_SUBTITLE_EXTS = {"ass", "srt", "vtt", "ssa"}


# ─── Filesystem helpers ────────────────────────────────────────────────────────


def scan_subtitle_sidecars(video_path: str) -> list[dict]:
    """Scan filesystem for all subtitle sidecar files next to video_path.

    Returns a list of dicts with path, language, format, size_bytes, modified_at.
    Files must match the pattern: <base>.<lang>.<ext> where ext is a subtitle extension.
    The video file itself is excluded.
    """
    base, _ = os.path.splitext(video_path)
    result = []
    try:
        for fpath in _glob.glob(_glob.escape(base) + ".*"):
            if fpath == video_path:
                continue
            parts = os.path.basename(fpath).split(".")
            # Need at least: basename.lang.ext (3 parts)
            if len(parts) < 3:
                continue
            ext = parts[-1].lower()
            if ext not in _SUBTITLE_EXTS:
                continue
            lang = parts[-2]
            # Reject obviously invalid language codes (quality, backup, etc.)
            if not lang or len(lang) > 8 or "." in lang:
                continue
            try:
                stat = os.stat(fpath)
            except OSError:
                continue
            result.append(
                {
                    "path": fpath,
                    "language": lang,
                    "format": ext,
                    "size_bytes": stat.st_size,
                    "modified_at": stat.st_mtime,
                }
            )
    except Exception as exc:
        logger.warning("scan_subtitle_sidecars failed for %s: %s", video_path, exc)
    return result


# ─── Trash helpers ─────────────────────────────────────────────────────────────


def _get_trash_root(media_path: str) -> str:
    return os.path.join(media_path, ".sublarr_trash")


def _get_batch_dir(media_path: str, batch_id: str) -> str:
    return os.path.join(_get_trash_root(media_path), batch_id)


def _write_manifest(batch_dir: str, batch_id: str, files: list[dict]) -> None:
    """Write a manifest.json recording original paths for a trash batch."""
    manifest = {
        "batch_id": batch_id,
        "created_at": datetime.now(UTC).isoformat(),
        "files": files,  # [{"original": "...", "trashed": "..."}]
    }
    manifest_path = os.path.join(batch_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)


def _read_manifest(batch_dir: str) -> dict | None:
    manifest_path = os.path.join(batch_dir, "manifest.json")
    try:
        with open(manifest_path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _auto_purge_old_trash(media_path: str, retention_days: int) -> int:
    """Permanently remove trash batches older than retention_days. 0 = keep forever."""
    if retention_days <= 0:
        return 0
    trash_root = _get_trash_root(media_path)
    if not os.path.isdir(trash_root):
        return 0

    cutoff = datetime.now(UTC).timestamp() - retention_days * 86400
    purged = 0
    for entry in os.scandir(trash_root):
        if not entry.is_dir():
            continue
        manifest = _read_manifest(entry.path)
        if manifest is None:
            continue
        created_at_str = manifest.get("created_at", "")
        try:
            created_ts = datetime.fromisoformat(created_at_str).timestamp()
        except (ValueError, TypeError):
            continue
        if created_ts < cutoff:
            try:
                shutil.rmtree(entry.path)
                purged += 1
                logger.info(
                    "auto-purge: removed trash batch %s (age > %dd)",
                    manifest["batch_id"],
                    retention_days,
                )
            except OSError as exc:
                logger.warning("auto-purge: could not remove %s: %s", entry.path, exc)
    return purged


def _trash_sidecar(path: str, media_path: str, batch_dir: str) -> tuple[str, str | None]:
    """Move a subtitle file into the trash batch directory.

    Returns (trashed_path_or_original, error_or_None).
    """
    if not is_safe_path(path, media_path):
        return path, "Path outside media directory"
    ext = os.path.splitext(path)[1].lstrip(".").lower()
    if ext not in _SUBTITLE_EXTS:
        return path, f"Not a subtitle file: .{ext}"
    if not os.path.exists(path):
        return path, "File not found"

    os.makedirs(batch_dir, exist_ok=True)
    basename = os.path.basename(path)
    trash_path = os.path.join(batch_dir, basename)
    # Resolve name conflicts
    if os.path.exists(trash_path):
        trash_path = os.path.join(batch_dir, f"{uuid.uuid4().hex[:8]}_{basename}")
    try:
        shutil.move(path, trash_path)
    except OSError as exc:
        return path, str(exc)

    # Move .quality.json sidecar too if present
    quality_src = path + ".quality.json"
    if os.path.exists(quality_src):
        try:
            shutil.move(quality_src, trash_path + ".quality.json")
        except OSError:
            pass

    # Remove subtitle_downloads DB entry (best-effort)
    try:
        from extensions import db as sa_db  # noqa: I001
        from sqlalchemy import text as _text  # noqa: I001

        with sa_db.engine.connect() as conn:
            conn.execute(_text("DELETE FROM subtitle_downloads WHERE file_path = :p"), {"p": path})
            conn.commit()
    except Exception as exc:
        logger.debug("Could not remove subtitle_downloads entry for %s: %s", path, exc)

    return trash_path, None


# ─── Endpoints: sidecar discovery ──────────────────────────────────────────────


@bp.route("/library/episodes/<int:ep_id>/subtitles", methods=["GET"])
def list_episode_subtitles(ep_id: int):
    """Return all subtitle sidecar files found next to this episode's video file."""
    from sonarr_client import get_sonarr_client

    client = get_sonarr_client()
    if client is None:
        return jsonify({"error": "Sonarr not configured"}), 503

    raw_path = client.get_episode_file_path(ep_id)
    if not raw_path:
        return jsonify({"error": "Episode has no video file"}), 404

    video_path = map_path(raw_path)
    if not os.path.exists(video_path):
        return jsonify({"error": "Video file not found: " + video_path}), 404

    sidecars = scan_subtitle_sidecars(video_path)
    return jsonify({"subtitles": sidecars, "video_path": video_path}), 200


@bp.route("/library/series/<int:series_id>/subtitles", methods=["GET"])
def list_series_subtitles(series_id: int):
    """Return all subtitle sidecar files for every episode in a series.

    Uses a single Sonarr call to get all episode file paths, then scans in parallel.
    Response: { subtitles: { "<sonarr_ep_id>": [SidecarSubtitle, ...] } }
    """
    from sonarr_client import get_sonarr_client

    client = get_sonarr_client()
    if client is None:
        return jsonify({"error": "Sonarr not configured"}), 503

    episode_files = client.get_episode_files_by_series(series_id)
    if not episode_files:
        return jsonify({"subtitles": {}}), 200

    # Build file_id -> sonarr_episode_id map so results are keyed by episode ID
    # (frontend uses ep.id = Sonarr episode ID, not episode file ID)
    episodes_raw = client.get_episodes(series_id) or []
    file_id_to_ep_id: dict[int, int] = {
        ep["episodeFileId"]: ep["id"]
        for ep in episodes_raw
        if ep.get("hasFile") and ep.get("episodeFileId") and ep.get("id")
    }

    result: dict[str, list[dict]] = {}

    def _scan_one(file_id: int, file_info: dict):
        raw_path = file_info.get("path")
        if not raw_path:
            return file_id, []
        video_path = map_path(raw_path)
        if not os.path.exists(video_path):
            return file_id, []
        return file_id, scan_subtitle_sidecars(video_path)

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(_scan_one, file_id, file_info): file_id
            for file_id, file_info in episode_files.items()
        }
        for future in as_completed(futures):
            try:
                file_id, sidecars = future.result()
                if sidecars:
                    ep_id = file_id_to_ep_id.get(file_id, file_id)
                    result[str(ep_id)] = sidecars
            except Exception as exc:
                logger.warning("Error scanning sidecars for file %s: %s", futures[future], exc)

    return jsonify({"subtitles": result}), 200


# ─── Endpoints: soft-delete (trash) ────────────────────────────────────────────


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
            _blacklist_subtitle(path)

        trash_path, err = _trash_sidecar(path, media_path, batch_dir)
        if err:
            failed.append({"path": path, "error": err})
        else:
            deleted.append(path)
            manifest_files.append({"original": path, "trashed": trash_path})

    if manifest_files:
        _write_manifest(batch_dir, batch_id, manifest_files)

    return jsonify({"batch_id": batch_id, "deleted": deleted, "failed": failed}), 200


def _blacklist_subtitle(subtitle_path: str) -> None:
    """Add a subtitle sidecar to the blacklist (best-effort, never raises).

    Derives the video base path from the subtitle path (strips lang + ext),
    then looks up provider/subtitle_id in subtitle_downloads.
    """
    try:
        from db.blacklist import add_blacklist_entry  # noqa: I001
        from extensions import db as sa_db  # noqa: I001
        from sqlalchemy import text as _text  # noqa: I001

        parts = os.path.basename(subtitle_path).split(".")
        if len(parts) < 3:
            return
        lang = parts[-2]
        base_name = ".".join(parts[:-2])
        base_path = os.path.join(os.path.dirname(subtitle_path), base_name)

        with sa_db.engine.connect() as conn:
            row = conn.execute(
                _text(
                    "SELECT provider_name, subtitle_id, language"
                    " FROM subtitle_downloads"
                    " WHERE file_path LIKE :p AND language = :lang"
                    " ORDER BY downloaded_at DESC LIMIT 1"
                ),
                {"p": base_path + ".%", "lang": lang},
            ).fetchone()

        if row:
            add_blacklist_entry(
                provider_name=row[0] or "manual",
                subtitle_id=row[1] or "",
                language=row[2] or lang,
                file_path=subtitle_path,
                reason="Deleted from library",
            )
    except Exception as exc:
        logger.debug("Could not add blacklist entry for %s: %s", subtitle_path, exc)


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
    delete_languages: list[str] | None = body.get("languages") or None
    delete_formats: list[str] | None = body.get("formats") or None

    client = get_sonarr_client()
    if client is None:
        return jsonify({"error": "Sonarr not configured"}), 503

    episode_files = client.get_episode_files_by_series(series_id)
    if not episode_files:
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

    for file_info in episode_files.values():
        raw_path = file_info.get("path")
        if not raw_path:
            continue
        video_path = map_path(raw_path)
        if not os.path.exists(video_path):
            continue

        sidecars = scan_subtitle_sidecars(video_path)
        for sidecar in sidecars:
            lang = sidecar["language"]
            fmt = sidecar["format"]

            # Only delete if matches the requested language filter
            if delete_languages is not None and lang not in delete_languages:
                continue
            # Only delete if matches the requested format filter
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


# ─── Endpoints: trash management ───────────────────────────────────────────────


@bp.route("/library/trash", methods=["GET"])
def list_trash():
    """List all trash batches with file count and total size.

    Response: { "batches": [{ batch_id, created_at, file_count, size_bytes }] }
    """
    settings = get_settings()
    media_path = getattr(settings, "media_path", "/media")
    retention = getattr(settings, "subtitle_trash_retention_days", 7)
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
        batches.append(
            {
                "batch_id": manifest["batch_id"],
                "created_at": manifest.get("created_at"),
                "file_count": len(files),
                "size_bytes": total_bytes,
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


_SUBTITLE_DOWNLOAD_EXTS = {".ass", ".srt", ".vtt", ".ssa", ".sub"}
_ZIP_SIZE_LIMIT = 50 * 1024 * 1024  # 50 MB


def _get_series_path(series_id: int) -> str | None:
    """Resolve series filesystem path via Sonarr, applying path mapping."""
    from sonarr_client import get_sonarr_client

    try:
        client = get_sonarr_client()
        series = client.get_series_by_id(series_id)
        if not series:
            return None
        raw_path = series.get("path", "")
        return map_path(raw_path) if raw_path else None
    except Exception:
        return None


def _scan_series_subtitles(series_path: str, warnings: list) -> list[dict]:
    """Return subtitle file dicts within series_path."""
    from export_manager import _scan_subtitle_files

    return _scan_subtitle_files(series_path, warnings)


@bp.route("/series/<int:series_id>/subtitles/export", methods=["GET"])
def export_series_subtitles(series_id: int):
    """Export all subtitle sidecar files for a series as a ZIP download.

    Query params:
        lang: optional language code filter (e.g. 'de' keeps only *.de.* files)
    """
    settings = get_settings()
    lang_filter = request.args.get("lang", "").strip().lower()
    media_path = getattr(settings, "media_path", "/media")

    series_path = _get_series_path(series_id)
    if not series_path:
        return jsonify({"error": "Series not found"}), 404

    if not is_safe_path(series_path, media_path):
        return jsonify({"error": "Access denied"}), 403

    warnings: list = []
    subtitle_files = _scan_series_subtitles(series_path, warnings)

    if lang_filter:
        subtitle_files = [
            s for s in subtitle_files
            if f".{lang_filter}." in os.path.basename(s["path"]).lower()
        ]

    buf = io.BytesIO()
    total_bytes = 0

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for sub in subtitle_files:
            sub_path = sub["path"]
            if not os.path.isfile(sub_path):
                continue
            total_bytes += os.path.getsize(sub_path)
            if total_bytes > _ZIP_SIZE_LIMIT:
                return jsonify({"error": "Export too large (50 MB limit)"}), 413
            rel_path = os.path.relpath(sub_path, series_path)
            zf.write(sub_path, rel_path)

    buf.seek(0)
    series_name = os.path.basename(series_path.rstrip("/\\")) or f"series-{series_id}"
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{series_name}-subtitles.zip",
    )


@bp.route("/subtitles/download", methods=["GET"])
def download_subtitle():
    """Serve a single subtitle sidecar file as a browser download.

    Query params:
        path: absolute path to the subtitle file (must be within media_path)
    """
    path = request.args.get("path", "").strip()
    if not path:
        return jsonify({"error": "path parameter required"}), 400

    settings = get_settings()
    media_path = getattr(settings, "media_path", "/media")
    if not is_safe_path(path, media_path):
        return jsonify({"error": "Access denied"}), 403

    ext = os.path.splitext(path)[1].lower()
    if ext not in _SUBTITLE_DOWNLOAD_EXTS:
        return jsonify({"error": "Access denied"}), 403

    if not os.path.isfile(path):
        return jsonify({"error": "File not found"}), 404

    return send_file(path, as_attachment=True, download_name=os.path.basename(path))
