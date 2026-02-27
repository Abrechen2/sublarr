"""API Key Management routes -- /api/v1/api-keys/*.

Centralized API key registry with test, rotate, export/import, and Bazarr migration.
"""

import csv
import io
import json
import logging
import zipfile
from datetime import UTC, datetime

from flask import Blueprint, jsonify, request, send_file

bp = Blueprint("api_keys", __name__, url_prefix="/api/v1/api-keys")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Registry: maps service name -> config_entries keys + optional test function
# ---------------------------------------------------------------------------

API_KEY_REGISTRY = {
    "sublarr": {
        "keys": ["api_key"],
        "test_fn": None,
        "label": "Sublarr",
    },
    "sonarr": {
        "keys": ["sonarr_api_key"],
        "test_fn": "_test_sonarr",
        "label": "Sonarr",
    },
    "radarr": {
        "keys": ["radarr_api_key"],
        "test_fn": "_test_radarr",
        "label": "Radarr",
    },
    "opensubtitles": {
        "keys": ["opensubtitles_api_key", "opensubtitles_username", "opensubtitles_password"],
        "test_fn": "_test_provider",
        "label": "OpenSubtitles",
    },
    "jimaku": {
        "keys": ["jimaku_api_key"],
        "test_fn": "_test_provider",
        "label": "Jimaku",
    },
    "subdl": {
        "keys": ["subdl_api_key"],
        "test_fn": "_test_provider",
        "label": "SubDL",
    },
    "tmdb": {
        "keys": ["tmdb_api_key"],
        "test_fn": None,
        "label": "TMDB",
    },
    "tvdb": {
        "keys": ["tvdb_api_key"],
        "test_fn": None,
        "label": "TVDB",
    },
    "deepl": {
        "keys": ["deepl_api_key"],
        "test_fn": "_test_deepl",
        "label": "DeepL",
    },
    "apprise": {
        "keys": ["notification_urls_json"],
        "test_fn": "_test_apprise",
        "label": "Apprise Notifications",
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mask_value(val: str) -> str:
    """Mask a secret value, showing first 4 + '***' + last 4 chars.

    Returns all '***' if the value is 8 chars or fewer.
    """
    if not val:
        return ""
    if len(val) <= 8:
        return "***"
    return val[:4] + "***" + val[-4:]


def _get_service_info(service_name: str) -> dict:
    """Build a status dict for a single registered service."""
    from db.config import get_config_entry

    entry = API_KEY_REGISTRY.get(service_name)
    if entry is None:
        return None

    keys_list = []
    for key_name in entry["keys"]:
        raw = get_config_entry(key_name) or ""
        keys_list.append({
            "name": key_name,
            "status": "configured" if raw else "missing",
            "masked_value": _mask_value(raw) if raw else "(not set)",
        })

    all_configured = all(k["status"] == "configured" for k in keys_list)
    any_configured = any(k["status"] == "configured" for k in keys_list)

    return {
        "service": service_name,
        "label": entry["label"],
        "keys": keys_list,
        "status": "configured" if all_configured else ("partial" if any_configured else "missing"),
        "testable": entry["test_fn"] is not None,
    }


# ---------------------------------------------------------------------------
# Test helpers (lazy imports to avoid circular dependencies)
# ---------------------------------------------------------------------------

def _test_sonarr() -> dict:
    """Test Sonarr connection."""
    try:
        from sonarr_client import get_sonarr_client
        client = get_sonarr_client()
        if client is None:
            return {"success": False, "message": "Sonarr client not configured"}
        result = client.test_connection()
        return result if isinstance(result, dict) else {"success": bool(result), "message": "OK" if result else "Failed"}
    except Exception as e:
        return {"success": False, "message": str(e)}


def _test_radarr() -> dict:
    """Test Radarr connection."""
    try:
        from radarr_client import get_radarr_client
        client = get_radarr_client()
        if client is None:
            return {"success": False, "message": "Radarr client not configured"}
        result = client.test_connection()
        return result if isinstance(result, dict) else {"success": bool(result), "message": "OK" if result else "Failed"}
    except Exception as e:
        return {"success": False, "message": str(e)}


def _test_provider(service_name: str) -> dict:
    """Test a subtitle provider by name."""
    try:
        from providers import get_provider_manager
        manager = get_provider_manager()
        provider = manager.get_provider(service_name)
        if provider is None:
            return {"success": False, "message": f"Provider '{service_name}' not found or not enabled"}
        # Use a lightweight connectivity test if available
        if hasattr(provider, "test_connection"):
            return provider.test_connection()
        return {"success": True, "message": f"Provider '{service_name}' is loaded and enabled"}
    except Exception as e:
        return {"success": False, "message": str(e)}


def _test_deepl() -> dict:
    """Test DeepL translation backend."""
    try:
        from translation import get_translation_manager
        manager = get_translation_manager()
        if manager is None:
            return {"success": False, "message": "Translation manager not available"}
        backend = manager.get_backend("deepl")
        if backend is None:
            return {"success": False, "message": "DeepL backend not configured"}
        if hasattr(backend, "test_connection"):
            return backend.test_connection()
        return {"success": True, "message": "DeepL backend is loaded"}
    except Exception as e:
        return {"success": False, "message": str(e)}


def _test_apprise() -> dict:
    """Test Apprise notification delivery."""
    try:
        from notifier import test_notification
        return test_notification()
    except Exception as e:
        return {"success": False, "message": str(e)}


_TEST_DISPATCH = {
    "_test_sonarr": _test_sonarr,
    "_test_radarr": _test_radarr,
    "_test_provider": _test_provider,
    "_test_deepl": _test_deepl,
    "_test_apprise": _test_apprise,
}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@bp.route("/", methods=["GET"])
def list_services():
    """List all registered services with their API key status.
    ---
    get:
      tags:
        - API Keys
      summary: List all services
      description: Returns all registered services with key status and masked values.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: List of services
          content:
            application/json:
              schema:
                type: object
                properties:
                  services:
                    type: array
                    items:
                      type: object
    """
    services = []
    for name in API_KEY_REGISTRY:
        info = _get_service_info(name)
        if info is not None:
            services.append(info)
    return jsonify({"services": services})


@bp.route("/<service>", methods=["GET"])
def get_service(service):
    """Get detailed status for a single service.
    ---
    get:
      tags:
        - API Keys
      summary: Get service detail
      description: Returns key status and masked values for a single service.
      security:
        - apiKeyAuth: []
      parameters:
        - in: path
          name: service
          required: true
          schema:
            type: string
      responses:
        200:
          description: Service detail
        404:
          description: Service not found
    """
    info = _get_service_info(service)
    if info is None:
        return jsonify({"error": f"Service '{service}' not found"}), 404
    return jsonify(info)


@bp.route("/<service>", methods=["PUT"])
def update_service_keys(service):
    """Update API keys for a service and invalidate caches.
    ---
    put:
      tags:
        - API Keys
      summary: Update service keys
      description: >
        Saves new key values for a service, invalidates related caches,
        and returns updated service info.
      security:
        - apiKeyAuth: []
      parameters:
        - in: path
          name: service
          required: true
          schema:
            type: string
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              additionalProperties:
                type: string
      responses:
        200:
          description: Keys updated
        400:
          description: No data provided
        404:
          description: Service not found
    """
    entry = API_KEY_REGISTRY.get(service)
    if entry is None:
        return jsonify({"error": f"Service '{service}' not found"}), 404

    data = request.get_json() or {}
    if not data:
        return jsonify({"error": "No key data provided"}), 400

    from config import reload_settings
    from db.config import get_all_config_entries, save_config_entry

    saved_keys = []
    for key_name in entry["keys"]:
        if key_name in data:
            val = str(data[key_name]).strip()
            # Skip masked values (user did not change)
            if "***" in val:
                continue
            save_config_entry(key_name, val)
            saved_keys.append(key_name)

    # Reload settings so new values take effect
    all_overrides = get_all_config_entries()
    reload_settings(all_overrides)

    # Service-specific invalidation
    _invalidate_for_service(service)

    logger.info("API keys updated for service '%s': %s", service, saved_keys)

    info = _get_service_info(service)
    return jsonify({
        "status": "updated",
        "updated_keys": saved_keys,
        "service": info,
    })


def _invalidate_for_service(service: str):
    """Invalidate singleton caches relevant to a service."""
    try:
        if service == "sonarr":
            from sonarr_client import invalidate_client
            invalidate_client()
        elif service == "radarr":
            from radarr_client import invalidate_client
            invalidate_client()
        elif service == "apprise":
            from notifier import invalidate_notifier
            invalidate_notifier()
        elif service in ("opensubtitles", "jimaku", "subdl"):
            from providers import invalidate_manager
            invalidate_manager()
        elif service == "deepl":
            try:
                from translation import invalidate_translation_manager
                invalidate_translation_manager()
            except ImportError:
                pass
    except Exception as exc:
        logger.warning("Failed to invalidate cache for service '%s': %s", service, exc)


@bp.route("/<service>/test", methods=["POST"])
def test_service(service):
    """Test connection for a service.
    ---
    post:
      tags:
        - API Keys
      summary: Test service connection
      description: Tests the configured API key for a service by performing a connectivity check.
      security:
        - apiKeyAuth: []
      parameters:
        - in: path
          name: service
          required: true
          schema:
            type: string
      responses:
        200:
          description: Test result
          content:
            application/json:
              schema:
                type: object
                properties:
                  success:
                    type: boolean
                  message:
                    type: string
        404:
          description: Service not found
        400:
          description: Service has no test function
    """
    entry = API_KEY_REGISTRY.get(service)
    if entry is None:
        return jsonify({"error": f"Service '{service}' not found"}), 404

    test_fn_name = entry.get("test_fn")
    if test_fn_name is None:
        return jsonify({"error": f"Service '{service}' does not support connection testing"}), 400

    test_fn = _TEST_DISPATCH.get(test_fn_name)
    if test_fn is None:
        return jsonify({"error": "Test function not found"}), 500

    # Provider test functions need the service name
    if test_fn_name == "_test_provider":
        result = test_fn(service)
    else:
        result = test_fn()

    return jsonify(result)


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
                all_glossary.append({
                    "id": row.id,
                    "series_id": row.series_id,
                    "source_term": row.source_term,
                    "target_term": row.target_term,
                    "notes": row.notes or "",
                })
    except Exception as exc:
        logger.warning("Could not export glossary entries: %s", exc)

    # Build ZIP in memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("config.json", json.dumps(safe_config, indent=2))
        zf.writestr("profiles.json", json.dumps(profiles, indent=2))
        zf.writestr("glossary.json", json.dumps(all_glossary, indent=2))
        zf.writestr("manifest.json", json.dumps({
            "format": "sublarr-export",
            "version": 1,
            "exported_at": datetime.now(UTC).isoformat(),
        }, indent=2))
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
    from config import Settings, reload_settings
    from db.config import get_all_config_entries, save_config_entry

    try:
        zf = zipfile.ZipFile(io.BytesIO(uploaded.read()))
    except zipfile.BadZipFile:
        return jsonify({"error": "Invalid ZIP file"}), 400

    result = {"config_imported": 0, "profiles_imported": 0, "glossary_imported": 0, "skipped": []}

    # Import config.json
    if "config.json" in zf.namelist():
        config_data = json.loads(zf.read("config.json"))
        valid_keys = set(Settings.model_fields.keys()) if hasattr(Settings, "model_fields") else set()
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
            profiles_data = json.loads(zf.read("profiles.json"))
            for p in profiles_data:
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
            glossary_data = json.loads(zf.read("glossary.json"))
            for g in glossary_data:
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

    imported = 0
    skipped = []
    errors = []

    for row_num, row in enumerate(reader, start=1):
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

    return jsonify({
        "status": "imported",
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
    })


@bp.route("/import/bazarr", methods=["POST"])
def import_bazarr():
    """Import configuration from a Bazarr config directory.
    ---
    post:
      tags:
        - API Keys
      summary: Import from Bazarr
      description: >
        Accepts a ZIP of Bazarr config files or individual config/DB files.
        Returns a preview of what will be imported. Send confirm=true to apply.
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
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    uploaded = request.files["file"]
    confirm = request.form.get("confirm", "false").lower() == "true"

    try:
        from bazarr_migrator import (
            apply_migration,
            migrate_bazarr_db,
            parse_bazarr_config,
            preview_migration,
        )
    except ImportError as exc:
        return jsonify({"error": f"Bazarr migrator not available: {exc}"}), 500

    config_data = {}
    db_data = {}

    content = uploaded.read()
    filename = uploaded.filename or ""

    # Handle ZIP archive of Bazarr config directory
    if filename.endswith(".zip") or content[:4] == b"PK\x03\x04":
        try:
            zf = zipfile.ZipFile(io.BytesIO(content))
            for name in zf.namelist():
                basename = name.rsplit("/", 1)[-1] if "/" in name else name
                if basename in ("config.yaml", "config.yml", "config.ini"):
                    file_content = zf.read(name).decode("utf-8", errors="replace")
                    parsed = parse_bazarr_config(file_content, basename)
                    config_data.update(parsed)
                elif basename.endswith(".db"):
                    # Extract DB to temp file for sqlite3 access
                    import os
                    import tempfile
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
                        tmp.write(zf.read(name))
                        tmp_path = tmp.name
                    try:
                        db_data = migrate_bazarr_db(tmp_path)
                    finally:
                        os.unlink(tmp_path)
        except zipfile.BadZipFile:
            return jsonify({"error": "Invalid ZIP file"}), 400
    else:
        # Single config file
        file_content = content.decode("utf-8", errors="replace")
        config_data = parse_bazarr_config(file_content, filename)

    if not config_data and not db_data:
        return jsonify({"error": "No Bazarr config or database data found"}), 400

    if confirm:
        result = apply_migration(config_data, db_data)
        return jsonify({"status": "applied", **result})
    else:
        preview = preview_migration(config_data, db_data)
        return jsonify({"status": "preview", **preview})
