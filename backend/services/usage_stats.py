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
    from config import get_settings

    raw = getattr(get_settings(), "providers_enabled", "") or ""
    return [p.strip() for p in raw.split(",") if p.strip()]


def build_usage_payload() -> dict:
    """Build the anonymous usage payload. No IP/hostname/paths/titles/keys."""
    from db.wanted import get_wanted_count
    from version import __version__

    return {
        "install_id": get_or_create_install_id(),
        "version": __version__,
        "arch": detect_arch(),
        "db_backend": detect_db_backend(),
        "providers_enabled": _enabled_providers(),
        "library_size_bucket": bucket_library_size(get_wanted_count()),
        "reported_at": datetime.now(UTC).isoformat(),
    }


# --- ping + scheduled tick -------------------------------------------------


def send_ping(payload: dict, endpoint: str) -> bool:
    """POST the payload; return success. Never raises (telemetry is best-effort)."""
    try:
        resp = requests.post(endpoint, json=payload, timeout=5)
        return 200 <= resp.status_code < 300
    except Exception as e:
        logger.debug("usage-stats ping failed: %s", e)
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
