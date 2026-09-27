"""Export / import endpoints for API-key configuration.

Handles Sublarr ZIP export, ZIP/CSV import, and Bazarr-config migration.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import zipfile
from datetime import UTC, datetime

from flask import jsonify, request, send_file

from routes.api_keys import bp
from routes.api_keys.helpers import API_KEY_REGISTRY

logger = logging.getLogger(__name__)


@bp.route("/export", methods=["POST"])
def export_keys():
    """Export API keys and related data as a ZIP archive.
    ---
    post:
      tags:
        - API Keys
      summary: Export config as ZIP
      description: >
        Exports config entries (with secrets masked), language profiles,
        and glossary entries as a ZIP archive.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: ZIP file
          content:
            application/zip:
              schema:
                type: string
                format: binary
    """
    from config import get_settings
    from db.profiles import get_all_language_profiles
    from db.repositories import TranslationRepository

    settings = get_settings()
    safe_config = settings.get_safe_config()

    # Collect profiles
    profiles = get_all_language_profiles()

    # Collect all glossary entries (across all series)
    all_glossary = []
    try:
        TranslationRepository()
        # Get all glossary entries -- use a broad query
        from db.models import GlossaryEntry
        from extensions import db as sa_db

        with sa_db.session() as session:
            rows = session.query(GlossaryEntry).all()
            for row in rows:
                all_glossary.append(
                    {
                        "id": row.id,
                        "series_id": row.series_id,
                        "source_term": row.source_term,
                        "target_term": row.target_term,
                        "notes": row.notes or "",
                    }
                )
    except Exception as exc:
        logger.warning("Could not export glossary entries: %s", exc)

    # Build ZIP in memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("config.json", json.dumps(safe_config, indent=2))
        zf.writestr("profiles.json", json.dumps(profiles, indent=2))
        zf.writestr("glossary.json", json.dumps(all_glossary, indent=2))
        zf.writestr(
            "manifest.json",
            json.dumps(
                {
                    "format": "sublarr-export",
                    "version": 1,
                    "exported_at": datetime.now(UTC).isoformat(),
                },
                indent=2,
            ),
        )
    buf.seek(0)

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"sublarr_export_{timestamp}.zip",
    )


@bp.route("/import", methods=["POST"])
def import_keys():
    """Import config from a Sublarr ZIP export or a CSV of API keys.
    ---
    post:
      tags:
        - API Keys
      summary: Import config from file
      description: >
        Accepts a ZIP (Sublarr export) or CSV file. ZIP imports config entries,
        profiles, and glossary. CSV imports rows as service,key_name,key_value.
        Masked secrets (containing '***') are skipped.
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
      responses:
        200:
          description: Import result
        400:
          description: No file provided or unsupported format
    """
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    uploaded = request.files["file"]
    filename = uploaded.filename or ""

    if filename.endswith(".zip"):
        return _import_zip(uploaded)
    elif filename.endswith(".csv"):
        return _import_csv(uploaded)
    else:
        # Try to detect format from content
        content = uploaded.read()
        uploaded.seek(0)
        if content[:4] == b"PK\x03\x04":
            return _import_zip(uploaded)
        return jsonify({"error": "Unsupported file format. Use .zip or .csv"}), 400


def _import_zip(uploaded) -> tuple:
    """Import from a Sublarr ZIP export."""
    from archive_utils import safe_read_zip_member
    from config import Settings, reload_settings
    from db.config import get_all_config_entries, save_config_entry

    try:
        zf = zipfile.ZipFile(io.BytesIO(uploaded.read()))
    except zipfile.BadZipFile:
        return jsonify({"error": "Invalid ZIP file"}), 400

    result = {"config_imported": 0, "profiles_imported": 0, "glossary_imported": 0, "skipped": []}

    # Each ``zf.read(name)`` decompresses the named entry into memory.
    # ``MAX_CONTENT_LENGTH=16 MB`` already caps the upload, but a 16 MB
    # ZIP can decompress to gigabytes (>1000:1 ratio is trivial with
    # repeated content). ``safe_read_zip_member`` enforces a 50 MB
    # uncompressed cap and a 100:1 ratio limit per entry — same rules as
    # the rest of the archive pipeline (archive_utils.py).
    if "config.json" in zf.namelist():
        try:
            config_data = json.loads(safe_read_zip_member(zf, "config.json"))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if not isinstance(config_data, dict):
            return jsonify({"error": "config.json must be a JSON object"}), 400
        valid_keys = (
            set(Settings.model_fields.keys()) if hasattr(Settings, "model_fields") else set()
        )
        for key, value in config_data.items():
            str_val = str(value)
            # Skip masked secrets
            if "***" in str_val:
                result["skipped"].append(key)
                continue
            if not valid_keys or key in valid_keys:
                save_config_entry(key, str_val)
                result["config_imported"] += 1

    # Import profiles.json
    if "profiles.json" in zf.namelist():
        try:
            from db.profiles import create_language_profile

            try:
                profiles_data = json.loads(safe_read_zip_member(zf, "profiles.json"))
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
            if not isinstance(profiles_data, list):
                logger.warning("profiles.json must be a JSON list — skipping")
                profiles_data = []
            for p in profiles_data:
                if not isinstance(p, dict):
                    continue
                try:
                    create_language_profile(
                        name=p.get("name", "Imported"),
                        source_lang=p.get("source_lang", "en"),
                        source_name=p.get("source_name", "English"),
                        target_langs=p.get("target_langs", []),
                        target_names=p.get("target_names", []),
                        translation_backend=p.get("translation_backend", "ollama"),
                        fallback_chain=p.get("fallback_chain"),
                        forced_preference=p.get("forced_preference", "disabled"),
                    )
                    result["profiles_imported"] += 1
                except Exception as exc:
                    logger.warning("Failed to import profile '%s': %s", p.get("name"), exc)
        except Exception as exc:
            logger.warning("Failed to parse profiles.json: %s", exc)

    # Import glossary.json
    if "glossary.json" in zf.namelist():
        try:
            from db.repositories import add_glossary_entry

            try:
                glossary_data = json.loads(safe_read_zip_member(zf, "glossary.json"))
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
            if not isinstance(glossary_data, list):
                logger.warning("glossary.json must be a JSON list — skipping")
                glossary_data = []
            for g in glossary_data:
                if not isinstance(g, dict):
                    continue
                try:
                    add_glossary_entry(
                        series_id=g.get("series_id", 0),
                        source_term=g.get("source_term", ""),
                        target_term=g.get("target_term", ""),
                        notes=g.get("notes", ""),
                    )
                    result["glossary_imported"] += 1
                except Exception as exc:
                    logger.warning("Failed to import glossary entry: %s", exc)
        except Exception as exc:
            logger.warning("Failed to parse glossary.json: %s", exc)

    # Reload settings
    all_overrides = get_all_config_entries()
    reload_settings(all_overrides)

    return jsonify({"status": "imported", **result})


def _import_csv(uploaded) -> tuple:
    """Import API keys from a CSV file (service, key_name, key_value)."""
    from config import reload_settings
    from db.config import get_all_config_entries, save_config_entry

    content = uploaded.read().decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(content))

    # Defense in depth: MAX_CONTENT_LENGTH already caps the upload at 16 MB,
    # but each row triggers a save_config_entry DB write. Cap iteration so a
    # malformed (e.g. binary-as-CSV) upload that decodes to thousands of
    # ambiguous rows can't pin a worker.
    _MAX_CSV_ROWS = 10000

    imported = 0
    skipped = []
    errors = []

    for row_num, row in enumerate(reader, start=1):
        if row_num > _MAX_CSV_ROWS:
            errors.append(
                f"CSV truncated: stopped after {_MAX_CSV_ROWS} rows "
                f"(file contains more — split it before retrying)"
            )
            break
        if len(row) < 3:
            errors.append(f"Row {row_num}: expected 3 columns, got {len(row)}")
            continue

        service, key_name, key_value = row[0].strip(), row[1].strip(), row[2].strip()

        # Skip masked values
        if "***" in key_value:
            skipped.append(key_name)
            continue

        # Validate service exists in registry
        entry = API_KEY_REGISTRY.get(service)
        if entry is None:
            errors.append(f"Row {row_num}: unknown service '{service}'")
            continue

        # Validate key belongs to this service
        if key_name not in entry["keys"]:
            errors.append(f"Row {row_num}: key '{key_name}' not valid for service '{service}'")
            continue

        save_config_entry(key_name, key_value)
        imported += 1

    # Reload settings
    all_overrides = get_all_config_entries()
    reload_settings(all_overrides)

    return jsonify(
        {
            "status": "imported",
            "imported": imported,
            "skipped": skipped,
            "errors": errors,
        }
    )


@bp.route("/import/bazarr", methods=["POST"])
def import_bazarr():
    """Import configuration from a Bazarr config directory.
    ---
    post:
      tags:
        - API Keys
      summary: Import from Bazarr
      description: >
        Accepts a ZIP of a Bazarr config directory, a config.yaml/config.ini,
        a bazarr.db, or several of these as repeated "file" parts. Returns a
        preview of what will be imported; send the same files again with
        confirm=true to apply. Imports the Sonarr/Radarr connection,
        OpenSubtitles login, language profiles and blacklist.
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
                confirm:
                  type: string
                  description: Set to 'true' to apply the import
      responses:
        200:
          description: Preview or import result
        400:
          description: No file provided
    """
    # Several parts may be sent under "file" (config and database side by side).
    uploads = request.files.getlist("file")
    if not uploads:
        return jsonify({"error": "No file provided"}), 400
    if len(uploads) > _MAX_BAZARR_UPLOADS:
        return jsonify({"error": f"At most {_MAX_BAZARR_UPLOADS} files per import"}), 400

    confirm = request.form.get("confirm", "false").lower() == "true"

    try:
        from bazarr_migrator import (
            apply_migration,
            migrate_bazarr_db,
            parse_bazarr_config,
            planned_config_entries,
            preview_migration,
        )
    except ImportError as exc:
        return jsonify({"error": f"Bazarr migrator not available: {exc}"}), 500

    config_data = {}
    db_data = {}

    for uploaded in uploads:
        content = uploaded.read()
        filename = uploaded.filename or ""

        # Handle ZIP archive of Bazarr config directory
        if filename.endswith(".zip") or content[:4] == b"PK\x03\x04":
            from archive_utils import safe_read_zip_member

            try:
                zf = zipfile.ZipFile(io.BytesIO(content))
                for name in zf.namelist():
                    basename = name.rsplit("/", 1)[-1] if "/" in name else name
                    if basename in ("config.yaml", "config.yml", "config.ini"):
                        try:
                            raw = safe_read_zip_member(zf, name)
                        except ValueError as exc:
                            return jsonify({"error": str(exc)}), 400
                        file_content = raw.decode("utf-8", errors="replace")
                        config_data = _merge_bazarr_config(
                            config_data, parse_bazarr_config(file_content, basename), basename
                        )
                    elif basename.endswith(".db"):
                        try:
                            db_bytes = safe_read_zip_member(zf, name)
                        except ValueError as exc:
                            return jsonify({"error": str(exc)}), 400
                        db_data = _take_bazarr_db(db_data, db_bytes, basename, migrate_bazarr_db)
            except zipfile.BadZipFile:
                return jsonify({"error": "Invalid ZIP file"}), 400
        elif content[: len(_SQLITE_MAGIC)] == _SQLITE_MAGIC:
            # A bare bazarr.db — used to be decoded as text and parsed as a config.
            db_data = _take_bazarr_db(db_data, content, filename, migrate_bazarr_db)
        else:
            file_content = content.decode("utf-8", errors="replace")
            config_data = _merge_bazarr_config(
                config_data, parse_bazarr_config(file_content, filename), filename
            )

    # A file that parses but holds nothing Sublarr can take (any text file
    # "parses" as an empty config) is answered here, not with an empty preview.
    if (
        not planned_config_entries(config_data)
        and not db_data.get("profiles")
        and not db_data.get("blacklist")
    ):
        warnings = config_data.get("warnings", []) + db_data.get("warnings", [])
        return jsonify({"error": "No importable Bazarr settings found", "warnings": warnings}), 400

    if confirm:
        result = apply_migration(config_data, db_data)
        _invalidate_after_bazarr_import(result.get("saved_keys", []))
        return jsonify({"status": "applied", **result})

    from db.config import get_all_config_entries

    preview = preview_migration(config_data, db_data, current=get_all_config_entries())
    return jsonify({"status": "preview", **preview})


_SQLITE_MAGIC = b"SQLite format 3\x00"
# config + database, or a couple of config backups; more is not a Bazarr import.
_MAX_BAZARR_UPLOADS = 4


def _read_bazarr_db_bytes(db_bytes: bytes, migrate_bazarr_db) -> dict:
    """Run the Bazarr DB reader on uploaded bytes (sqlite3 needs a real file)."""
    import os
    import tempfile

    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
        tmp.write(db_bytes)
        tmp_path = tmp.name
    try:
        return migrate_bazarr_db(tmp_path)
    finally:
        os.unlink(tmp_path)


_BAZARR_CONFIG_SECTIONS = ("sonarr", "radarr", "general")


def _merge_bazarr_config(current: dict, parsed: dict, source: str) -> dict:
    """Combine a further Bazarr config with what earlier files gave.

    A later file fills in and overrides per field, never per whole file, so a
    section only the first file had survives. Said out loud in the warnings.
    """
    if not current:
        return parsed
    merged = {**current}
    for section in _BAZARR_CONFIG_SECTIONS:
        later = {k: v for k, v in (parsed.get(section) or {}).items() if v not in ("", None)}
        merged[section] = {**(current.get(section) or {}), **later}
    merged["warnings"] = [
        *current.get("warnings", []),
        *parsed.get("warnings", []),
        f"More than one Bazarr config: values from {source} were merged over the earlier one.",
    ]
    return merged


def _take_bazarr_db(current: dict, db_bytes: bytes, source: str, migrate_bazarr_db) -> dict:
    """Read a Bazarr database, unless one was already read (the first wins)."""
    if not current:
        return _read_bazarr_db_bytes(db_bytes, migrate_bazarr_db)
    return {
        **current,
        "warnings": [
            *current.get("warnings", []),
            f"Only one Bazarr database is imported; {source} was ignored.",
        ],
    }


def _invalidate_after_bazarr_import(saved_keys: list[str]) -> None:
    """Drop the clients built from config the import just replaced.

    apply_migration reloads the settings; the Sonarr/Radarr clients and the
    provider manager are singletons that would otherwise keep the old values
    until the next restart.
    """
    if any(k.startswith("sonarr_") for k in saved_keys):
        from sonarr_client import invalidate_client

        invalidate_client()
    if any(k.startswith("radarr_") for k in saved_keys):
        from radarr_client import invalidate_client

        invalidate_client()
    if any(k.startswith("opensubtitles_") for k in saved_keys):
        from providers import invalidate_manager

        invalidate_manager()
