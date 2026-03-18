"""System backup routes — /database/health, /database/backup, /database/backups,
/database/restore, /backup/full/*.
"""

import contextlib
import io
import json
import logging
import os
import zipfile
from datetime import UTC, datetime

from flask import jsonify, request, send_file

from routes.system import bp
from version import __version__

logger = logging.getLogger(__name__)


@bp.route("/database/health", methods=["GET"])
def database_health():
    """Check database integrity and return stats.
    ---
    get:
      tags:
        - System
      summary: Database health check
      description: Runs SQLite integrity check and returns database statistics.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Database is healthy
          content:
            application/json:
              schema:
                type: object
                properties:
                  healthy:
                    type: boolean
                  message:
                    type: string
                  stats:
                    type: object
                    additionalProperties: true
        503:
          description: Database integrity check failed
    """
    from database_health import get_health_report, get_pool_stats

    db_report = get_health_report()
    is_ok = db_report["status"] == "healthy"
    result = {
        "healthy": is_ok,
        "backend": db_report["backend"],
        "message": db_report["status"],
        "stats": db_report.get("details", {}),
    }
    pool = get_pool_stats()
    if pool is not None:
        result["pool"] = pool

    status_code = 200 if is_ok else 503
    return jsonify(result), status_code


@bp.route("/database/backup", methods=["POST"])
def create_backup():
    """Create a manual database backup.
    ---
    post:
      tags:
        - System
      summary: Create database backup
      description: Creates a manual SQLite database backup with optional label.
      security:
        - apiKeyAuth: []
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                label:
                  type: string
                  enum: [daily, weekly, monthly]
                  default: daily
      responses:
        201:
          description: Backup created
          content:
            application/json:
              schema:
                type: object
                properties:
                  path:
                    type: string
                  size_bytes:
                    type: integer
                  label:
                    type: string
    """
    from config import get_settings
    from database_backup import DatabaseBackup

    s = get_settings()
    backup = DatabaseBackup(
        db_path=s.db_path,
        backup_dir=s.backup_dir,
        retention_daily=s.backup_retention_daily,
        retention_weekly=s.backup_retention_weekly,
        retention_monthly=s.backup_retention_monthly,
    )
    data = request.get_json() or {}
    label = data.get("label", "daily")
    if label not in ("daily", "weekly", "monthly"):
        label = "daily"

    result = backup.create_backup(label=label)
    backup.rotate()
    return jsonify(result), 201


@bp.route("/database/backups", methods=["GET"])
def list_backups():
    """List all available database backups.
    ---
    get:
      tags:
        - System
      summary: List database backups
      description: Returns a list of all available SQLite database backup files.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: List of backups
          content:
            application/json:
              schema:
                type: object
                properties:
                  backups:
                    type: array
                    items:
                      type: object
                      properties:
                        filename:
                          type: string
                        size_bytes:
                          type: integer
                        created_at:
                          type: string
    """
    from config import get_settings
    from database_backup import DatabaseBackup

    s = get_settings()
    backup = DatabaseBackup(db_path=s.db_path, backup_dir=s.backup_dir)
    return jsonify({"backups": backup.list_backups()})


@bp.route("/database/restore", methods=["POST"])
def restore_backup():
    """Restore the database from a backup file.
    ---
    post:
      tags:
        - System
      summary: Restore database from backup
      description: Restores the SQLite database from a previously created backup file. Requires explicit confirmation.
      security:
        - apiKeyAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [filename, confirm]
              properties:
                filename:
                  type: string
                  description: Backup filename to restore from
                confirm:
                  type: boolean
                  description: Must be true to proceed with restore
      responses:
        200:
          description: Database restored successfully
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  restored_from:
                    type: string
        400:
          description: Missing filename or confirmation
    """
    from config import get_settings
    from database_backup import DatabaseBackup
    from db import close_db, get_db

    data = request.get_json() or {}
    filename = data.get("filename", "")
    confirm = data.get("confirm", False)

    if not filename:
        return jsonify({"error": "filename is required"}), 400
    if not confirm:
        return jsonify({"error": "Add confirm: true to proceed"}), 400

    if "/" in filename or "\\" in filename or ".." in filename:
        return jsonify({"error": "Invalid filename"}), 400

    s = get_settings()
    backup = DatabaseBackup(db_path=s.db_path, backup_dir=s.backup_dir)
    backup_path = os.path.join(s.backup_dir, filename)
    if not os.path.abspath(backup_path).startswith(os.path.abspath(s.backup_dir) + os.sep):
        return jsonify({"error": "Invalid filename"}), 400

    # Close the current connection before restore
    close_db()

    result = backup.restore_backup(backup_path)

    # Re-open connection
    get_db()

    return jsonify(result)


# ── ZIP Full Backup ────────────────────────────────────────────────────────────


@bp.route("/backup/full", methods=["POST"])
def create_full_backup():
    """Create a full ZIP backup containing manifest, config, and database.
    ---
    post:
      tags:
        - System
      summary: Create full ZIP backup
      description: Creates a ZIP archive containing manifest.json, config.json, and the SQLite database.
      security:
        - apiKeyAuth: []
      responses:
        201:
          description: Full backup created
          content:
            application/json:
              schema:
                type: object
                properties:
                  filename:
                    type: string
                  size_bytes:
                    type: integer
                  created_at:
                    type: string
                    format: date-time
                  contents:
                    type: array
                    items:
                      type: string
    """
    from config import get_settings
    from database_backup import DatabaseBackup

    s = get_settings()
    backup = DatabaseBackup(
        db_path=s.db_path,
        backup_dir=s.backup_dir,
        retention_daily=s.backup_retention_daily,
        retention_weekly=s.backup_retention_weekly,
        retention_monthly=s.backup_retention_monthly,
    )

    # Step 1: Create DB backup
    db_result = backup.create_backup(label="manual")
    db_backup_path = db_result["path"]

    # Step 2: Build config export
    safe_config = s.get_safe_config()

    # Step 3: Create ZIP in memory
    buffer = io.BytesIO()
    now = datetime.now(UTC)
    timestamp = now.strftime("%Y%m%d_%H%M%S")

    db_backend = db_result.get("backend", "sqlite")
    db_archive_name = "sublarr.db" if db_backend == "sqlite" else "sublarr.pgdump"
    contents = ["manifest.json", "config.json", db_archive_name]
    manifest = {
        "version": __version__,
        "created_at": now.isoformat(),
        "schema_version": 1,
        "contents": contents,
        "db_backend": db_backend,
    }

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        zf.writestr("config.json", json.dumps(safe_config, indent=2))
        zf.write(db_backup_path, db_archive_name)

    buffer.seek(0)

    # Step 4: Save ZIP to backup_dir
    zip_filename = f"sublarr_full_{timestamp}.zip"
    zip_path = os.path.join(s.backup_dir, zip_filename)
    with open(zip_path, "wb") as f:
        f.write(buffer.getvalue())

    size_bytes = os.path.getsize(zip_path)
    logger.info("Full ZIP backup created: %s (%d bytes)", zip_path, size_bytes)

    return jsonify(
        {
            "filename": zip_filename,
            "size_bytes": size_bytes,
            "created_at": now.isoformat(),
            "contents": contents,
        }
    ), 201


@bp.route("/backup/full/download/<filename>", methods=["GET"])
def download_full_backup(filename):
    """Download a ZIP backup file.
    ---
    get:
      tags:
        - System
      summary: Download a ZIP backup
      description: Downloads a previously created full ZIP backup file.
      security:
        - apiKeyAuth: []
      parameters:
        - in: path
          name: filename
          required: true
          schema:
            type: string
          description: ZIP backup filename
      responses:
        200:
          description: ZIP file download
          content:
            application/zip:
              schema:
                type: string
                format: binary
        400:
          description: Invalid filename
        404:
          description: Backup file not found
    """
    from config import get_settings

    # Security: validate filename
    if not filename.endswith(".zip") or "/" in filename or "\\" in filename or ".." in filename:
        return jsonify({"error": "Invalid filename"}), 400

    s = get_settings()
    zip_path = os.path.join(s.backup_dir, filename)
    if not os.path.exists(zip_path):
        return jsonify({"error": "Backup file not found"}), 404

    return send_file(
        zip_path, mimetype="application/zip", as_attachment=True, download_name=filename
    )


@bp.route("/backup/full/restore", methods=["POST"])
def restore_full_backup():
    """Restore from a full ZIP backup (config + database).
    ---
    post:
      tags:
        - System
      summary: Restore from full ZIP backup
      description: Uploads and restores a full ZIP backup containing config and database. Secrets are skipped during config import.
      security:
        - apiKeyAuth: []
      requestBody:
        required: true
        content:
          multipart/form-data:
            schema:
              type: object
              properties:
                file:
                  type: string
                  format: binary
                  description: ZIP backup file
      responses:
        200:
          description: Backup restored
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  config_imported:
                    type: array
                    items:
                      type: string
                  db_restored:
                    type: boolean
        400:
          description: Invalid or missing file
    """
    from config import Settings, get_settings, reload_settings
    from database_backup import DatabaseBackup
    from db import close_db, get_db
    from db.config import get_all_config_entries, save_config_entry

    if "file" not in request.files:
        return jsonify({"error": "No file uploaded. Use multipart/form-data with key 'file'"}), 400

    file = request.files["file"]

    # Validate ZIP
    file_stream = io.BytesIO(file.read())
    if not zipfile.is_zipfile(file_stream):
        return jsonify({"error": "Uploaded file is not a valid ZIP archive"}), 400

    file_stream.seek(0)

    try:
        with zipfile.ZipFile(file_stream, "r") as zf:
            # Read and validate manifest
            if "manifest.json" not in zf.namelist():
                return jsonify({"error": "ZIP missing manifest.json"}), 400

            manifest = json.loads(zf.read("manifest.json"))
            if manifest.get("schema_version") != 1:
                return jsonify(
                    {"error": f"Unsupported schema_version: {manifest.get('schema_version')}"}
                ), 400

            s = get_settings()
            imported_keys = []
            db_restored = False

            # Import config if present
            if "config.json" in zf.namelist():
                config_data = json.loads(zf.read("config.json"))
                valid_keys = (
                    set(Settings.model_fields.keys())
                    if hasattr(Settings, "model_fields")
                    else set()
                )
                secret_keys = {
                    "api_key",
                    "sonarr_api_key",
                    "radarr_api_key",
                    "jellyfin_api_key",
                    "opensubtitles_api_key",
                    "opensubtitles_password",
                    "jimaku_api_key",
                    "subdl_api_key",
                    "tmdb_api_key",
                    "tvdb_api_key",
                    "tvdb_pin",
                }

                for key, value in config_data.items():
                    if key in secret_keys:
                        continue
                    if str(value) == "***configured***":
                        continue
                    if not valid_keys or key in valid_keys:
                        save_config_entry(key, str(value))
                        imported_keys.append(key)

            # Restore DB if present (dialect-aware via manifest)
            backup_backend = manifest.get("db_backend", "sqlite")
            db_archive_name = "sublarr.pgdump" if backup_backend == "postgresql" else "sublarr.db"
            suffix = ".pgdump" if backup_backend == "postgresql" else ".db"

            if db_archive_name in zf.namelist():
                import tempfile

                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(zf.read(db_archive_name))
                    tmp_path = tmp.name

                try:
                    backup = DatabaseBackup(db_path=s.db_path, backup_dir=s.backup_dir)
                    close_db()
                    backup.restore_backup(tmp_path)
                    get_db()
                    db_restored = True
                finally:
                    with contextlib.suppress(OSError):
                        os.unlink(tmp_path)

            # Reload settings with DB overrides
            all_overrides = get_all_config_entries()
            reload_settings(all_overrides)

            # Invalidate caches
            try:
                from mediaserver import invalidate_media_server_manager as _inv_media
                from providers import invalidate_manager as _inv_providers
                from radarr_client import invalidate_client as _inv_radarr
                from sonarr_client import invalidate_client as _inv_sonarr

                _inv_sonarr()
                _inv_radarr()
                _inv_media()
                _inv_providers()
            except Exception:
                pass

            logger.info("Full backup restored: config=%s, db=%s", imported_keys, db_restored)

            return jsonify(
                {
                    "status": "restored",
                    "config_imported": imported_keys,
                    "db_restored": db_restored,
                }
            )

    except (json.JSONDecodeError, KeyError, zipfile.BadZipFile) as exc:
        return jsonify({"error": f"Invalid backup file: {exc}"}), 400


@bp.route("/backup/full/list", methods=["GET"])
def list_full_backups():
    """List all ZIP backup files.
    ---
    get:
      tags:
        - System
      summary: List full ZIP backups
      description: Returns a list of all full ZIP backup files with metadata.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: List of ZIP backups
          content:
            application/json:
              schema:
                type: object
                properties:
                  backups:
                    type: array
                    items:
                      type: object
                      properties:
                        filename:
                          type: string
                        size_bytes:
                          type: integer
                        created_at:
                          type: string
                          format: date-time
    """
    from config import get_settings

    s = get_settings()
    backups = []

    if not os.path.isdir(s.backup_dir):
        return jsonify({"backups": []})

    for name in sorted(os.listdir(s.backup_dir), reverse=True):
        if not name.endswith(".zip"):
            continue
        path = os.path.join(s.backup_dir, name)
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        # Parse timestamp from filename: sublarr_full_YYYYMMDD_HHMMSS.zip
        created_at = ""
        if name.startswith("sublarr_full_") and len(name) >= 30:
            ts_part = name[len("sublarr_full_") :].replace(".zip", "")
            try:
                dt = datetime.strptime(ts_part, "%Y%m%d_%H%M%S")
                created_at = dt.replace(tzinfo=UTC).isoformat()
            except ValueError:
                created_at = ""
        backups.append(
            {
                "filename": name,
                "size_bytes": size,
                "created_at": created_at,
            }
        )

    return jsonify({"backups": backups})
