"""Core config routes — GET /config, PUT /config, POST /settings/path-mapping/test."""

import json
import logging
import os
import time

from flask import jsonify, request

from cache_response import cached_get, invalidate_response_cache
from events import emit_event
from routes.config import bp
from security_utils import is_safe_path, validate_service_url

logger = logging.getLogger(__name__)

_MASK_SENTINEL = "***configured***"
# Top-level config keys that hold a JSON-encoded array of instance dicts. Each
# instance dict can carry secret-typed subkeys (api_key/token/password/secret)
# that GET masks but the raw top-level scalar mask check would miss. We deep-
# scan these blobs and merge masked subkeys with the stored instance.
_INSTANCE_BLOB_KEYS = {
    "sonarr_instances_json",
    "radarr_instances_json",
    "jellyfin_instances_json",
    "emby_instances_json",
    "plex_instances_json",
    "kodi_instances_json",
    "mediaservers_instances_json",
}
_SECRET_SUBKEYS = ("api_key", "apikey", "token", "password", "secret", "auth")


def _deep_unmask_instance_blob(new_raw: str, key: str) -> str | None:
    """Replace any masked secret subkeys in new_raw with the stored value.

    Returns the unmasked JSON string, or None if the new payload is unparseable
    (in which case the caller should reject the update with 400 — never persist
    raw mask sentinels into a JSON blob).
    """
    from db.config import get_config_entry

    try:
        new_list = json.loads(new_raw) if new_raw else []
    except (TypeError, ValueError):
        return None
    if not isinstance(new_list, list):
        return None

    stored_raw = get_config_entry(key) or "[]"
    try:
        stored_list = json.loads(stored_raw)
    except (TypeError, ValueError):
        stored_list = []
    stored_by_id = {str(inst.get("id", "")): inst for inst in stored_list if isinstance(inst, dict)}

    for inst in new_list:
        if not isinstance(inst, dict):
            continue
        stored = stored_by_id.get(str(inst.get("id", "")))
        for sub in list(inst.keys()):
            if not any(sub.lower().endswith(s) or sub.lower() == s for s in _SECRET_SUBKEYS):
                continue
            v = inst.get(sub)
            if isinstance(v, str) and v == _MASK_SENTINEL:
                if stored and isinstance(stored.get(sub), str):
                    inst[sub] = stored[sub]
                else:
                    # Mask sent for a secret with no stored value — drop it
                    # rather than persist the literal mask.
                    inst.pop(sub, None)
    return json.dumps(new_list)


@bp.route("/config", methods=["GET"])
@cached_get(ttl_seconds=60)
def get_config():
    """Get current configuration (without secrets).
    ---
    get:
      tags:
        - Config
      summary: Get configuration
      description: Returns the current application configuration with secret values masked.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Configuration object
          content:
            application/json:
              schema:
                type: object
                additionalProperties: true
    """
    from config import get_settings
    from db.config import get_config_entry

    s = get_settings()
    cfg = s.get_safe_config()
    # Include namespaced extension config entries (dot-notation keys not in Pydantic Settings)
    _extension_keys = [
        "translation.context_window_size",
    ]
    for _k in _extension_keys:
        _v = get_config_entry(_k)
        if _v is not None:
            cfg[_k] = _v
    return jsonify(cfg)


@bp.route("/settings/path-mapping/test", methods=["POST"])
def test_path_mapping():
    """Test path mapping by mapping a Sonarr/Radarr path to local path.
    ---
    post:
      tags:
        - Config
      summary: Test path mapping
      description: Maps a remote Sonarr/Radarr path to the local filesystem path and checks if it exists.
      security:
        - apiKeyAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [remote_path]
              properties:
                remote_path:
                  type: string
                  description: Remote path from Sonarr/Radarr
      responses:
        200:
          description: Path mapping result
          content:
            application/json:
              schema:
                type: object
                properties:
                  remote_path:
                    type: string
                  mapped_path:
                    type: string
                  exists:
                    type: boolean
        400:
          description: Missing remote_path
    """
    from config import get_settings, map_path

    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Payload must be a JSON object"}), 400
    remote_path = data.get("remote_path", "").strip()

    if not remote_path:
        return jsonify({"error": "remote_path is required"}), 400

    mapped = map_path(remote_path)
    # Constrain the existence probe to media_path so an authenticated caller
    # cannot use this endpoint to fingerprint the host filesystem (e.g.
    # `/etc/shadow`, container paths, secret-file probing).
    media_path = getattr(get_settings(), "media_path", "/media")
    exists = bool(mapped) and is_safe_path(mapped, media_path) and os.path.exists(mapped)
    return jsonify(
        {
            "remote_path": remote_path,
            "mapped_path": mapped,
            "exists": exists,
        }
    )


@bp.route("/config", methods=["PUT"])
def update_config():
    """Update configuration values and reload settings.
    ---
    put:
      tags:
        - Config
      summary: Update configuration
      description: >
        Saves partial configuration updates to the database and reloads settings.
        Invalidates all cached clients (Sonarr, Radarr, providers, media servers).
        Masked password values ('***configured***') are skipped.
      security:
        - apiKeyAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              additionalProperties: true
              description: Key-value pairs of config settings to update
      responses:
        200:
          description: Configuration saved and reloaded
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  updated_keys:
                    type: array
                    items:
                      type: string
                  config:
                    type: object
                    additionalProperties: true
        400:
          description: No config values provided
    """
    from config import Settings, reload_settings
    from db.config import get_all_config_entries, save_config_entry
    from services.wanted_scanner import invalidate_scanner

    data = request.get_json(silent=True) or {}
    # A JSON list/scalar payload would crash .items() with AttributeError.
    if not isinstance(data, dict):
        return jsonify({"error": "Config payload must be a JSON object"}), 400
    if not data:
        return jsonify({"error": "No config values provided"}), 400

    # Validate that keys exist in Settings
    valid_keys = set(Settings.model_fields.keys()) if hasattr(Settings, "model_fields") else set()
    saved_keys = []

    _ENUM_FIELDS = {
        "log_level": {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"},
        "auto_sync_engine": {"ffsubsync", "alass"},
        "log_format": {"text", "json"},
    }
    # Config keys that hold outbound service URLs — validated to block dangerous schemes
    # and cloud metadata endpoints before being persisted.
    _URL_FIELDS = {
        "ollama_url",
        "sonarr_url",
        "radarr_url",
        "jellyfin_url",
    }
    _MAX_STRING_LENGTH = 4096

    for key, value in data.items():
        # Skip masked password values (user didn't change them)
        if str(value) == _MASK_SENTINEL:
            continue
        # Deep-unmask JSON instance blobs: GET embeds the mask in subkeys
        # (api_key, token, password, …); a naive top-level string compare
        # misses those and persists the literal mask, wiping the credential.
        if key in _INSTANCE_BLOB_KEYS and isinstance(value, str):
            unmasked = _deep_unmask_instance_blob(value, key)
            if unmasked is None:
                return jsonify({"error": f"Invalid JSON payload for {key}"}), 400
            value = unmasked
        # Validate enum fields
        if key in _ENUM_FIELDS and value not in _ENUM_FIELDS[key]:
            return jsonify(
                {"error": f"Invalid value for {key}: must be one of {sorted(_ENUM_FIELDS[key])}"}
            ), 400
        # Validate service URL fields — block dangerous schemes and metadata endpoints.
        # Also validates any extension key (dot-notation) whose name ends with "_url" or "url".
        _is_url_key = key in _URL_FIELDS or ("." in key and key.lower().endswith(("_url", "url")))
        if _is_url_key and value:
            ok, reason = validate_service_url(str(value))
            if not ok:
                return jsonify({"error": f"Invalid URL for {key}: {reason}"}), 400
        # Enforce max string length
        if isinstance(value, str) and len(value) > _MAX_STRING_LENGTH:
            return jsonify(
                {"error": f"Value for {key} exceeds maximum length of {_MAX_STRING_LENGTH}"}
            ), 400
        # Allow known config keys OR namespaced extension keys (dot-notation, e.g. translation.context_window_size)
        is_extension_key = "." in key
        if not valid_keys or key in valid_keys or is_extension_key:
            # Sanitize credentials: strip whitespace from API keys and passwords
            sanitized_value = (
                str(value).strip()
                if isinstance(value, str) or "api_key" in key.lower() or "password" in key.lower()
                else str(value)
            )
            save_config_entry(key, sanitized_value)
            saved_keys.append(key)

    # Perf markers — measure each reconcile phase so a slow save (see the
    # ~12s-lag reports) self-diagnoses in the logs instead of guessing which
    # sub-operation stalls. Deltas are logged in a summary line below.
    _marks: list[tuple[str, float]] = [("start", time.perf_counter())]

    # Reload settings with ALL DB overrides applied
    all_overrides = get_all_config_entries()
    settings = reload_settings(all_overrides)
    _marks.append(("reload_settings", time.perf_counter()))

    # Selectively invalidate singleton clients based on which keys changed
    from mediaserver import invalidate_media_server_manager as _inv_media
    from notifier import invalidate_notifier as _inv_notifier
    from providers import invalidate_manager as _inv_providers
    from providers import update_manager_providers as _upd_providers
    from radarr_client import invalidate_client as _inv_radarr
    from sonarr_client import invalidate_client as _inv_sonarr

    if any(k.startswith("sonarr_") for k in saved_keys):
        _inv_sonarr()
    if any(k.startswith("radarr_") for k in saved_keys):
        _inv_radarr()

    _credential_keys = {
        "opensubtitles_api_key",
        "jimaku_api_key",
        "subdl_api_key",
        "min_score",
        "source_language",
        "target_language",
    }
    # providers_hidden is UI-only; exclude it from backend provider invalidation
    _provider_keys = {
        k
        for k in saved_keys
        if (k.startswith("provider") or k.startswith("scoring_") or k in _credential_keys)
        and k != "providers_hidden"
    }
    if _provider_keys:
        if _provider_keys == {"providers_enabled"}:
            # Only the enabled-set changed: selectively add/remove, keep others intact
            _upd_providers(all_overrides.get("providers_enabled", ""))
        else:
            # Credentials or other provider config changed: full reinit
            _inv_providers()
    if any(
        k.startswith("jellyfin_")
        or k.startswith("emby_")
        or k.startswith("plex_")
        or k.startswith("kodi_")
        or k.startswith("media_server")
        for k in saved_keys
    ):
        _inv_media()
    if any(
        k.startswith("notification")
        or k.startswith("pushover")
        or k.startswith("gotify")
        or k.startswith("ntfy")
        or k.startswith("discord")
        or k.startswith("slack")
        for k in saved_keys
    ):
        _inv_notifier()
    # The scanner/scheduler only needs a restart when a scan/search interval
    # changed. WantedScanner caches no settings (it reads get_settings() lazily
    # at tick time), so provider/scoring/language/UI changes propagate to the
    # next tick without invalidating or restarting anything. Restarting on
    # EVERY save was the ~2.5s term (APScheduler SQLAlchemyJobStore trigger
    # rewrites) behind the ~12s settings-lag reports.
    _SCHEDULER_KEYS = {"wanted_scan_interval_hours", "wanted_search_interval_hours"}
    _scheduler_relevant = any(k in _SCHEDULER_KEYS for k in saved_keys)
    if _scheduler_relevant:
        invalidate_scanner()
    invalidate_response_cache()
    _marks.append(("invalidate_clients", time.perf_counter()))

    # Live-apply logging changes (level / file path / format / rotation) without
    # a restart. _setup_logging is idempotent — it tears down and rebuilds the
    # file + WebSocket handlers — so re-running it with the reloaded settings
    # makes a UI change to any logging setting take effect immediately.
    from app_logging import LOGGING_CONFIG_KEYS

    if any(k in LOGGING_CONFIG_KEYS for k in saved_keys):
        try:
            from app_logging import _setup_logging

            _setup_logging(settings)
        except Exception as _exc:
            logger.warning("Failed to re-apply logging config after update: %s", _exc)

    # Restart scanner scheduler ONLY when an interval changed (see above).
    # invalidate_scanner() nulled the scanner (dropping its _app ref), so the
    # restart re-caches the Flask app + socketio and pushes the new interval
    # into APScheduler. Without an interval change we skip this entirely,
    # keeping a bare UI save (e.g. items_per_page) fast. Without the restart on
    # the interval path, search_all() would fail with "Working outside of
    # application context" because invalidate_scanner() reset _app to None.
    if _scheduler_relevant:
        try:
            from flask import current_app as _capp

            from extensions import socketio as _sock
            from services.wanted_scanner import get_scanner as _get_scanner

            _get_scanner().start_scheduler(app=_capp._get_current_object(), socketio=_sock)
        except Exception as _exc:
            logger.warning("Failed to restart scanner scheduler after config update: %s", _exc)
    _marks.append(("scheduler_restart", time.perf_counter()))

    # Reload media server instances with new config
    try:
        from mediaserver import get_media_server_manager

        get_media_server_manager().load_instances()
    except Exception as exc:
        logger.warning("Media server reload failed after config update: %s", exc)
    _marks.append(("media_reload", time.perf_counter()))

    # Hot-restart the standalone manager when its config or any arr-instance
    # config changed (auto-activation logic depends on arr presence). Without
    # this, toggling standalone_enabled or changing debounce requires a
    # container restart.
    _standalone_keys = {
        "standalone_enabled",
        "standalone_debounce_seconds",
        "standalone_skip_extras",
    }
    _standalone_relevant = any(k in _standalone_keys for k in saved_keys) or any(
        k.startswith("sonarr_") or k.startswith("radarr_") for k in saved_keys
    )
    if _standalone_relevant:
        try:
            from flask import current_app as _capp

            from extensions import socketio as _sock
            from standalone import reload_standalone_manager

            reload_standalone_manager(socketio=_sock, app=_capp._get_current_object())
        except Exception as exc:
            logger.warning("Standalone manager reload failed: %s", exc)

    # Push standalone_scan_interval_hours through APScheduler so the
    # standalone_scan job's trigger picks up the new value (or pauses on 0).
    if "standalone_scan_interval_hours" in saved_keys:
        try:
            from apscheduler.triggers.interval import IntervalTrigger
            from flask import current_app as _capp

            _scheduler = _capp.extensions.get("scheduler")
            if _scheduler is not None:
                _new_h = int(getattr(settings, "standalone_scan_interval_hours", 0) or 0)
                if _new_h <= 0:
                    try:
                        _scheduler.pause_job("standalone_scan")
                    except Exception:
                        logger.debug("standalone_scan: pause_job failed", exc_info=True)
                else:
                    _scheduler.modify_trigger(
                        "standalone_scan", IntervalTrigger(hours=max(1, _new_h))
                    )
                    try:
                        _scheduler.resume_job("standalone_scan")
                    except Exception:
                        pass
        except Exception as exc:
            logger.warning("standalone_scan trigger update failed: %s", exc)

    logger.info("Config updated: %s — settings reloaded", saved_keys)

    emit_event("config_updated", {"updated_keys": saved_keys})

    # Invalidate scoring cache if scoring-related keys changed
    scoring_keys_changed = any(
        k.startswith("scoring_") or k.startswith("provider_modifier_") for k in saved_keys
    )
    if scoring_keys_changed:
        try:
            from providers.base import invalidate_scoring_cache

            invalidate_scoring_cache()
        except Exception as exc:
            logger.warning("Scoring cache invalidation failed after config update: %s", exc)

    _marks.append(("finish", time.perf_counter()))

    # Emit per-phase durations. INFO when the whole reconcile is slow (>1s) so
    # the ~12s-lag class of issue is always visible in prod logs; DEBUG otherwise.
    _deltas = {
        label: round((t - _marks[i][1]) * 1000) for i, (label, t) in enumerate(_marks[1:], start=0)
    }
    _total_ms = round((_marks[-1][1] - _marks[0][1]) * 1000)
    _phases = " ".join(f"{k}={v}ms" for k, v in _deltas.items())
    _summary = f"config reconcile {_total_ms}ms total | {_phases}"
    logger.log(logging.INFO if _total_ms > 1000 else logging.DEBUG, _summary)

    return jsonify(
        {
            "status": "saved",
            "updated_keys": saved_keys,
            "config": settings.get_safe_config(),
        }
    )
