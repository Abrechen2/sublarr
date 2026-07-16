"""Opt-in anonymous usage statistics: consent state, install id, payload, ping job.

See docs/superpowers/specs/2026-07-09-anonymous-usage-stats-design.md.
Telemetry is best-effort and opt-in — it must never affect the running app.
"""

import logging
import platform
import uuid
from datetime import UTC, datetime

import requests

logger = logging.getLogger(__name__)

CONSENT_KEY = "usage_stats_consent"
INSTALL_ID_KEY = "usage_stats_install_id"
_VALID_CONSENT = {"unset", "granted", "denied"}

_ARCH_MAP = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}


# --- consent + install id --------------------------------------------------


def get_consent() -> str:
    """Return the consent state: ``unset`` | ``granted`` | ``denied``."""
    from db.config import get_config_entry

    value = get_config_entry(CONSENT_KEY)
    return value if value in _VALID_CONSENT else "unset"


def set_consent(value: str) -> None:
    """Persist the consent state. Raises ``ValueError`` on an invalid value."""
    if value not in _VALID_CONSENT:
        raise ValueError(f"invalid consent value: {value!r}")
    from db.config import save_config_entry

    save_config_entry(CONSENT_KEY, value)


def get_or_create_install_id() -> str:
    """Return the anonymous install id, generating+persisting it on first call.

    A purely random uuid4 — never derived from IP, hostname, MAC, or paths.
    """
    from db.config import get_config_entry, save_config_entry

    existing = get_config_entry(INSTALL_ID_KEY)
    if existing:
        return existing
    new_id = uuid.uuid4().hex
    save_config_entry(INSTALL_ID_KEY, new_id)
    return new_id


def get_stats_endpoint() -> str:
    """Return the configured ping endpoint (empty string = disabled)."""
    from config import get_settings

    return getattr(get_settings(), "stats_endpoint", "")


# --- payload ---------------------------------------------------------------


def bucket_library_size(n: int) -> str:
    """Map an item count to a coarse deployment-size bucket (never an exact count)."""
    if n < 100:
        return "<100"
    if n < 1000:
        return "100-1k"
    if n < 10000:
        return "1k-10k"
    return "10k+"


def detect_arch() -> str:
    """Return the normalised CPU arch: ``amd64`` | ``arm64`` (raw value otherwise)."""
    machine = platform.machine().lower()
    return _ARCH_MAP.get(machine, machine)


def detect_db_backend() -> str:
    """Return ``postgres`` if the DB URL targets Postgres, else ``sqlite``."""
    from config import get_settings

    url = getattr(get_settings(), "database_url", "") or ""
    return "postgres" if url.startswith("postgres") else "sqlite"


def _enabled_providers() -> list[str]:
    """Effective enabled provider names for the anonymous provider-popularity stat.

    ``providers_enabled`` is a comma-separated allow-list, but an EMPTY value
    means "all registered providers enabled" (see ProviderManager) — which is the
    default for most installs. Returning ``[]`` there made every default install
    under-report as "no providers", so the public chart only ever reflected the
    handful of users who manually curated a subset. Resolve empty to the full
    registered set so the common case is represented faithfully.
    """
    from config import get_settings

    raw = getattr(get_settings(), "providers_enabled", "") or ""
    if raw.strip():
        return [p.strip() for p in raw.split(",") if p.strip()]
    try:
        from providers.registry import _PROVIDER_CLASSES

        return sorted(_PROVIDER_CLASSES.keys())
    except Exception:
        # Telemetry is best-effort — never break a ping over provider resolution.
        return []


# --- anonymous extension groups (features / env / scale) -------------------
#
# Every field below is an enum, bool, or bucket — never a raw count, URL,
# model name, or key. Each reader is defensive (getattr / try-except) so a
# missing or malformed source silently degrades to a safe default rather than
# breaking a ping. See docs/superpowers/specs/2026-07-16-telemetry-extension-
# gdpr-design.md §4-5a.

_KNOWN_MEDIA_SERVER_TYPES = frozenset({"jellyfin", "emby", "plex", "kodi"})


def _safe_rollback() -> None:
    """Roll back a failed telemetry query so it can't poison the session."""
    try:
        from extensions import db

        db.session.rollback()
    except Exception:
        pass


def _translation_backend_type(settings) -> str:
    """Coarse translation backend TYPE — ``ollama`` | ``openai`` | ``none``.

    Reports only the *family* (local Ollama vs. an external API backend), never
    the concrete backend name, model, or URL. ``none`` means translation is
    disabled. Any non-Ollama backend (openai-compat, gemini, deepl, …) maps to
    the external ``openai`` bucket — the payload contract is the three-value
    enum from the design spec, so external engines share one type.
    """
    try:
        if not getattr(settings, "translation_enabled", False):
            return "none"
        backend = (getattr(settings, "translation_default_backend", "") or "").strip().lower()
        if backend == "ollama":
            return "ollama"
        return "openai" if backend else "none"
    except Exception:
        return "none"


def _media_server_type(settings) -> str:
    """Primary media-server TYPE — jellyfin | emby | plex | kodi | multiple | none.

    Reads only the ``type`` of each configured instance from
    ``media_servers_json`` (plus the legacy single Jellyfin/Emby field); never a
    URL, name, or key. When several *distinct* types are configured, reports
    ``multiple`` (rather than picking one arbitrarily) so the enum stays honest.
    """
    try:
        types: list[str] = []
        raw = (getattr(settings, "media_servers_json", "") or "").strip()
        if raw:
            import json

            for entry in json.loads(raw):
                if not isinstance(entry, dict):
                    continue
                t = str(entry.get("type", "")).strip().lower()
                if t in _KNOWN_MEDIA_SERVER_TYPES:
                    types.append(t)
        # Legacy single Jellyfin/Emby integration (jellyfin_url/jellyfin_api_key).
        if not types and (getattr(settings, "jellyfin_url", "") or "").strip():
            types.append("jellyfin")
        distinct = list(dict.fromkeys(types))
        if not distinct:
            return "none"
        if len(distinct) == 1:
            return distinct[0]
        return "multiple"
    except Exception:
        return "none"


def _arr_connected(settings, url_field: str, key_field: str, json_field: str) -> bool:
    """True if a Sonarr/Radarr integration is configured (single or multi-instance).

    Only tests presence — never sends the URL or key itself.
    """
    try:
        url = (getattr(settings, url_field, "") or "").strip()
        key = (getattr(settings, key_field, "") or "").strip()
        if url and key:
            return True
        raw = (getattr(settings, json_field, "") or "").strip()
        if raw:
            import json

            arr = json.loads(raw)
            return isinstance(arr, list) and len(arr) > 0
    except Exception:
        pass
    return False


def _auth_type(settings) -> str:
    """Auth mode TYPE — ``none`` | ``ui`` | ``proxy`` (never a credential)."""
    try:
        if getattr(settings, "proxy_auth_enabled", False):
            return "proxy"
        if (getattr(settings, "api_key", "") or "").strip():
            return "ui"
    except Exception:
        pass
    return "none"


def _update_channel(version: str) -> str:
    """Derive the release channel from the version suffix.

    ``-rc.N`` -> ``rc``, ``-beta`` -> ``beta``, otherwise ``stable``.
    """
    v = (version or "").lower()
    if "-rc" in v:
        return "rc"
    if "-beta" in v:
        return "beta"
    return "stable"


def _count_distinct(*columns) -> int:
    """Sum of distinct non-null counts across the given ORM columns (0 on error)."""
    try:
        from sqlalchemy import func, select

        from extensions import db

        total = 0
        for col in columns:
            total += int(
                db.session.execute(
                    select(func.count(func.distinct(col))).where(col.isnot(None))
                ).scalar()
                or 0
            )
        return total
    except Exception:
        _safe_rollback()
        return 0


def _count_rows(model) -> int:
    """Total row count for an ORM model (0 on error)."""
    try:
        from sqlalchemy import func, select

        from extensions import db

        return int(db.session.execute(select(func.count()).select_from(model)).scalar() or 0)
    except Exception:
        _safe_rollback()
        return 0


def _scale_buckets() -> dict:
    """Coarse deployment-scale buckets — reuses ``bucket_library_size`` on real
    DB counts. Series/movies span both *arr-driven and standalone items."""
    from db.models.core import Job, WantedItem
    from db.models.providers import SubtitleDownload

    series = _count_distinct(WantedItem.sonarr_series_id, WantedItem.standalone_series_id)
    movies = _count_distinct(WantedItem.radarr_movie_id, WantedItem.standalone_movie_id)
    return {
        "series_bucket": bucket_library_size(series),
        "movies_bucket": bucket_library_size(movies),
        "downloads_bucket": bucket_library_size(_count_rows(SubtitleDownload)),
        "translation_jobs_bucket": bucket_library_size(_count_rows(Job)),
    }


def _auto_disabled_count() -> int:
    """Number of providers currently auto-disabled (anonymous fleet-health int)."""
    try:
        from db.providers import get_all_provider_stats_enriched

        stats = get_all_provider_stats_enriched()
        return sum(1 for v in stats.values() if v.get("auto_disabled"))
    except Exception:
        _safe_rollback()
        return 0


def _features(settings) -> dict:
    """Anonymous feature-adoption flags (bool/enum only)."""
    return {
        "translation_enabled": bool(getattr(settings, "translation_enabled", False)),
        "translation_backend": _translation_backend_type(settings),
        "media_server_type": _media_server_type(settings),
        "sonarr_connected": _arr_connected(
            settings, "sonarr_url", "sonarr_api_key", "sonarr_instances_json"
        ),
        "radarr_connected": _arr_connected(
            settings, "radarr_url", "radarr_api_key", "radarr_instances_json"
        ),
        "standalone_mode": bool(getattr(settings, "standalone_enabled", False)),
        "redis_used": bool((getattr(settings, "redis_url", "") or "").strip()),
    }


def _env(settings, version: str) -> dict:
    """Anonymous, low-cardinality environment enums."""
    return {
        "interface_language": str(getattr(settings, "interface_language", "en") or "en"),
        "auth_type": _auth_type(settings),
        "update_channel": _update_channel(version),
    }


def build_usage_payload() -> dict:
    """Build the anonymous usage payload. No IP/hostname/paths/titles/keys.

    The flat core is stable + required; the ``features``/``env``/``scale`` groups
    and ``auto_disabled_count`` are additive extensions. Each extension is
    best-effort — a failure to derive one omits that group rather than breaking
    the ping (older stats-service clients validate the core alone).
    """
    from config import get_settings
    from db.wanted import get_wanted_count
    from version import __version__

    settings = get_settings()
    payload = {
        "install_id": get_or_create_install_id(),
        "version": __version__,
        "arch": detect_arch(),
        "db_backend": detect_db_backend(),
        "providers_enabled": _enabled_providers(),
        "library_size_bucket": bucket_library_size(get_wanted_count()),
        "reported_at": datetime.now(UTC).isoformat(),
    }
    for key, builder in (
        ("features", lambda: _features(settings)),
        ("env", lambda: _env(settings, __version__)),
        ("scale", _scale_buckets),
        ("auto_disabled_count", _auto_disabled_count),
    ):
        try:
            payload[key] = builder()
        except Exception as e:
            logger.debug("usage-stats: skipping %s group: %s", key, e)
    return payload


# --- ping + scheduled tick -------------------------------------------------


def send_ping(payload: dict, endpoint: str) -> bool:
    """POST the payload; return success. Never raises (telemetry is best-effort)."""
    try:
        resp = requests.post(endpoint, json=payload, timeout=5)
        return 200 <= resp.status_code < 300
    except Exception as e:
        logger.debug("usage-stats ping failed: %s", e)
        return False


def _forget_url(endpoint: str) -> str:
    """Derive the ``/v1/forget`` URL from the configured ping endpoint base."""
    e = (endpoint or "").strip().rstrip("/")
    if e.endswith("/v1/ping"):
        base = e[: -len("/v1/ping")]
    elif e.endswith("/ping"):
        base = e[: -len("/ping")]
    else:
        base = e
    return f"{base}/v1/forget"


def forget_install(endpoint: str) -> bool:
    """Right-to-erasure (GDPR Art. 17): ``POST {base}/v1/forget {install_id}``.

    Best-effort — returns success, never raises (mirrors ``send_ping``). A no-op
    returning ``False`` when no endpoint is configured.
    """
    if not endpoint:
        return False
    try:
        payload = {"install_id": get_or_create_install_id()}
        resp = requests.post(_forget_url(endpoint), json=payload, timeout=5)
        return 200 <= resp.status_code < 300
    except Exception as e:
        logger.debug("usage-stats forget failed: %s", e)
        return False


def usage_stats_tick() -> None:
    """APScheduler job entrypoint (module-level + picklable).

    No-op unless consent is granted and an endpoint is configured.
    """
    try:
        if get_consent() != "granted":
            return
        endpoint = get_stats_endpoint()
        if not endpoint:
            return
        send_ping(build_usage_payload(), endpoint)
    except Exception as e:
        logger.debug("usage_stats_tick error: %s", e)
