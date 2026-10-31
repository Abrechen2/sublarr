"""Core config routes — GET /config, PUT /config, POST /settings/path-mapping/test."""

import logging
import os
import time

from flask import jsonify, request

from cache_response import cached_get, invalidate_response_cache
from events import emit_event
from routes.config import bp
from routes.config.payload import MASK_SENTINEL as _MASK_SENTINEL
from security_utils import is_safe_path

logger = logging.getLogger(__name__)


def _provider_field_owners() -> dict[str, str]:
    """Map each provider credential key to the provider that declares it."""
    owners: dict[str, str] = {}
    try:
        from providers.registry import _PROVIDER_CLASSES

        for name, cls in _PROVIDER_CLASSES.items():
            for field in getattr(cls, "config_fields", None) or []:
                key = field.get("key")
                if key:
                    owners[key] = name
    except Exception:  # pragma: no cover — never break a settings save
        logger.debug("could not read provider config fields", exc_info=True)
    return owners


def _enabled_provider_set(value, all_names: set[str]) -> set[str]:
    """Resolve ``providers_enabled`` to a concrete set. Empty means every non-opt-in provider."""
    from providers.registry import resolve_enabled_names

    return resolve_enabled_names(value) & set(all_names)


def _revive_on_provider_change_enabled() -> bool:
    """Whether the provider trigger may run at all (#214).

    Read fresh rather than cached: the save that switches this off is itself a
    settings save, and it must not fire the thing it just disabled.
    """
    try:
        from config import peek_settings

        return bool(getattr(peek_settings(), "wanted_revive_on_provider_change", True))
    except Exception:  # pragma: no cover — a missing setting means the default
        return True


def _providers_became_usable(data: dict, before: dict) -> set[str]:
    """Provider names this save actually made usable — not merely mentioned.

    #214: the trigger used to fire on the *name* of a saved key, so a save that
    switched a provider OFF, or that resent an unchanged credential, revived up
    to ``wanted_revive_max_per_run`` exhausted items all the same. Nothing had
    become usable, and the revived items then searched every enabled provider —
    on the reporter's install that turned a SubDL test into OpenSubtitles
    downloads, against the daily quota that is his real limit.

    Three things have to be true for a name to come back from here: the key was
    part of this save, its stored value actually changed, and the change points
    at a provider that can now do something it could not before.
    """
    became: set[str] = set()
    try:
        from providers.registry import _PROVIDER_CLASSES

        all_names = set(_PROVIDER_CLASSES)
    except Exception:  # pragma: no cover
        all_names = set()

    if "providers_enabled" in data:
        old_set = _enabled_provider_set(before.get("providers_enabled"), all_names)
        new_set = _enabled_provider_set(data.get("providers_enabled"), all_names)
        # Only additions. Removing a provider makes nothing usable, and a list
        # that merely changed order is not a change at all.
        became |= new_set - old_set

    owners = _provider_field_owners()
    for key, owner in owners.items():
        if key not in data:
            continue
        new_value = data.get(key)
        # The mask means "unchanged" — the save loop skips these too.
        if str(new_value) == _MASK_SENTINEL:
            continue
        new_text = str(new_value).strip() if new_value is not None else ""
        old_text = str(before.get(key) or "").strip()
        # A credential only becomes usable by being set to something, and only
        # if that something is new. Clearing one is the opposite of usable.
        if new_text and new_text != old_text:
            became.add(owner)

    return became


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
    cfg.update(_hub_config_entries())
    return jsonify(cfg)


def _hub_config_entries() -> dict:
    """Stored catalog-provider settings (``hub.<id>.<field>``), secrets masked.

    Which fields are secret comes from the bundle manifests, read as JSON, so
    masking does not depend on the catalog providers being switched on.
    """
    from config_settings import is_sensitive_config_key
    from db.config import get_all_config_entries

    try:
        from providers.hub import secret_config_keys

        secrets = secret_config_keys()
    except Exception:  # noqa: BLE001 — unreadable manifests: mask every hub value
        secrets = None
    out = {}
    for key, value in (get_all_config_entries() or {}).items():
        if not key.startswith("hub."):
            continue
        masked = (
            secrets is None or key in secrets or is_sensitive_config_key(key.rsplit(".", 1)[-1])
        )
        out[key] = (_MASK_SENTINEL if value else "") if masked else value
    return out


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
    from config import reload_settings
    from db.config import get_all_config_entries, save_config_entries
    from services.wanted_scanner import invalidate_scanner

    data = request.get_json(silent=True) or {}
    # A JSON list/scalar payload would crash .items() with AttributeError.
    if not isinstance(data, dict):
        return jsonify({"error": "Config payload must be a JSON object"}), 400
    if not data:
        return jsonify({"error": "No config values provided"}), 400

    # Every key is checked before anything is written, and the payload is
    # saved in one transaction: a refused key no longer leaves the others
    # saved behind a 400 (#61 A06). Same rules as the import (#61 A07).
    from routes.config.payload import check_config_payload

    checked = check_config_payload(data, mode="put")
    if checked.errors:
        return jsonify({"error": checked.errors[0]["error"], "errors": checked.errors}), 400

    # Snapshot the provider-relevant values BEFORE anything is written, so the
    # revive below can tell a real change from a resend (#214). Only the keys
    # this request actually carries are read.
    _provider_before: dict[str, str | None] = {}
    try:
        from db.config import get_config_entry as _get_entry

        _watch_keys = set(_provider_field_owners()) | {"providers_enabled"}
        _provider_before = {k: _get_entry(k) for k in data if k in _watch_keys}
    except Exception:  # pragma: no cover — never break a settings save
        logger.debug("could not snapshot provider config before save", exc_info=True)

    save_config_entries(checked.values)
    saved_keys = list(checked.values)

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
        "subsource_api_key",
        "min_score",
        "source_language",
        "target_language",
    }
    # providers_hidden is UI-only; exclude it from backend provider invalidation.
    # The name matters: a local called `_provider_keys` once shadowed the
    # module-level function of that name for this whole function body, so the
    # later call tried to call a set and raised — silently, because the revive
    # it guarded is wrapped in a catch-all so a bonus behaviour can never fail
    # a settings save. The function is gone now (#214 replaced it), but the
    # lesson is why this one is named for what it holds.
    # Every field a provider declares counts too: a saved Titlovi or
    # LegendasDivx account otherwise reached the provider only after a
    # restart (#61 A01).
    _declared_provider_keys = set(_provider_field_owners())
    provider_cache_keys = {
        k
        for k in saved_keys
        if (
            k.startswith("provider")
            or k.startswith("scoring_")
            or k.startswith("hub.")
            or k in _credential_keys
            or k in _declared_provider_keys
        )
        and k != "providers_hidden"
    }
    if provider_cache_keys:
        if provider_cache_keys == {"providers_enabled"}:
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

    # A provider that just became usable makes every "no result" verdict it
    # was absent for stale (#197). Attempt exhaustion is otherwise permanent
    # and provider-blind: items that burned their attempts while a provider was
    # broken stay parked forever, and fixing it afterwards does nothing for
    # them. Capped per run, so a large parked backlog returns in slices.
    #
    # Which providers *became usable* — not which keys appeared in the request
    # (#214). A save that only switches providers off, or resends unchanged
    # values, revives nothing now.
    _became_usable = _providers_became_usable(data, _provider_before)
    if _became_usable and _revive_on_provider_change_enabled():
        try:
            from services.wanted_revive import revive_after_provider_change

            revived = revive_after_provider_change(sorted(_became_usable))
            if revived:
                logger.info(
                    "provider(s) became usable (%s) — revived %d exhausted item(s)",
                    ", ".join(sorted(_became_usable)),
                    revived,
                )
        except Exception as exc:
            # Never let a bonus behaviour fail the settings save the user asked for.
            logger.warning("revive after provider change failed: %s", exc, exc_info=True)

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
