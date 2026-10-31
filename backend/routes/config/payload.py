"""One check for every config payload — PUT /config and POST /config/import.

The two endpoints validated differently (audit #61 A07: the import took an
``items_per_page`` of 1 and an unknown sync engine), the export could not be
imported back (A05: its own Ollama default), PUT committed key by key before a
later key was refused (A06), and boot fields that only the environment sets
were accepted and then ignored (A03). Every rule now lives here; the routes
only decide what an error means for them — PUT refuses the whole payload,
the import skips the key and reports it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal

MASK_SENTINEL = "***configured***"
MAX_STRING_LENGTH = 4096

#: Service URLs: dangerous schemes, metadata and link-local hosts are refused.
URL_KEYS = frozenset({"ollama_url", "sonarr_url", "radarr_url", "jellyfin_url"})
#: Services commonly run on the same machine (bare-metal Ollama); loopback is fine.
LOOPBACK_URL_KEYS = frozenset({"ollama_url"})

ENUM_FIELDS: dict[str, frozenset[str]] = {
    "log_level": frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}),
    "auto_sync_engine": frozenset({"ffsubsync", "alass"}),
    "log_format": frozenset({"text", "json"}),
}

#: JSON arrays of instances whose secret subkeys GET masks one by one.
MASKED_BLOB_KEYS = frozenset(
    {
        "sonarr_instances_json",
        "radarr_instances_json",
        "media_servers_json",
        "jellyfin_instances_json",
        "emby_instances_json",
        "plex_instances_json",
        "kodi_instances_json",
        "mediaservers_instances_json",
    }
)
SECRET_SUBKEYS = ("api_key", "apikey", "token", "password", "secret", "auth", "pin")
#: Where an instance's secret is sent; a stored secret is restored only for the same place.
ENDPOINT_FIELDS = ("url", "host", "port", "base_url", "type", "server_url")


@dataclass
class CheckedPayload:
    """``values`` are ready to store; ``errors`` name the refused keys."""

    values: dict[str, str] = field(default_factory=dict)
    errors: list[dict[str, str]] = field(default_factory=list)
    skipped_secrets: list[str] = field(default_factory=list)

    def refuse(self, key: str, message: str) -> None:
        self.errors.append({"key": key, "error": message})


def env_only_keys() -> frozenset[str]:
    """Boot settings that only the environment sets (port, paths, database …)."""
    from config_settings import BootSettings
    from config_singleton import _RUNTIME_OVERRIDABLE_BOOT_FIELDS

    return frozenset(BootSettings.model_fields) - _RUNTIME_OVERRIDABLE_BOOT_FIELDS


def _identity(inst: dict) -> tuple:
    """Which stored instance this is: its ``id``, else where it points.

    Media-server entries carry no id; their address (url, type, name) is what
    makes them the same server.
    """
    if inst.get("id"):
        return ("id", str(inst["id"]))
    return ("endpoint", *(str(inst.get(f) or "") for f in ("url", "type", "name")))


def deep_unmask_blob(new_raw: str, key: str) -> str | None:
    """``new_raw`` with masked secret subkeys taken from the stored instance.

    An instance borrows a stored secret only from the one stored instance
    with the same identity (id, else url/type/name) AND the same address
    (ENDPOINT_FIELDS). Otherwise the mask is dropped and the secret has to be
    entered again — a guessed match, or a changed URL with the mask kept,
    would send the stored key to another host (security review of #61).
    Returns None when ``new_raw`` is not a JSON array.
    """
    from db.config import get_config_entry

    try:
        new_list = json.loads(new_raw) if new_raw else []
    except (TypeError, ValueError):
        return None
    if not isinstance(new_list, list):
        return None
    try:
        stored_list = json.loads(get_config_entry(key) or "[]")
    except (TypeError, ValueError):
        stored_list = []
    stored_dicts = [i for i in stored_list if isinstance(i, dict)]
    identities = [_identity(i) for i in stored_dicts]
    stored_by_identity = {
        ident: inst for ident, inst in zip(identities, stored_dicts) if identities.count(ident) == 1
    }
    for inst in new_list:
        if not isinstance(inst, dict):
            continue
        stored = stored_by_identity.get(_identity(inst))
        if stored and any(inst.get(f) != stored.get(f) for f in ENDPOINT_FIELDS):
            stored = None
        for sub in list(inst):
            if not any(sub.lower() == s or sub.lower().endswith(s) for s in SECRET_SUBKEYS):
                continue
            if inst.get(sub) != MASK_SENTINEL:
                continue
            if stored and isinstance(stored.get(sub), str):
                inst[sub] = stored[sub]
            else:
                inst.pop(sub, None)
    return json.dumps(new_list)


def _importable_dotted(key: str) -> bool:
    from sensitive_keys import is_sensitive_key

    return key.startswith("hub.") and not is_sensitive_key(key)


def _check_value(key: str, value: object) -> tuple[object, str | None]:
    """The value to store, or the reason it is refused (no type check yet)."""
    from routes.config.bounds import BOUNDED_INT_KEYS, coerce_bounded_int, literal_choices
    from security_utils import validate_service_url

    if key == "items_per_page":
        number = value
        if isinstance(number, str):
            try:
                number = int(number.strip())
            except ValueError:
                number = None
        if type(number) is not int or not 10 <= number <= 200:
            return None, "items_per_page must be an integer between 10 and 200"
        return number, None
    if key in BOUNDED_INT_KEYS:
        return coerce_bounded_int(key, value)
    choices = literal_choices(key)
    if choices is not None and value not in choices:
        return None, f"{key} must be one of {sorted(choices, key=str)}"
    if key in ENUM_FIELDS and value not in ENUM_FIELDS[key]:
        return None, f"Invalid value for {key}: must be one of {sorted(ENUM_FIELDS[key])}"
    is_url = key in URL_KEYS or ("." in key and key.lower().endswith(("_url", "url")))
    if is_url and value:
        ok, reason = validate_service_url(str(value), allow_loopback=key in LOOPBACK_URL_KEYS)
        if not ok:
            return None, f"Invalid URL for {key}: {reason}"
    if isinstance(value, str) and len(value) > MAX_STRING_LENGTH:
        return None, f"Value for {key} exceeds maximum length of {MAX_STRING_LENGTH}"
    return value, None


def check_config_payload(data: dict, *, mode: Literal["put", "import"]) -> CheckedPayload:
    """Check ``data`` key by key, then the settings' types and validators together."""
    from config import get_settings
    from config_settings import UISettings
    from config_values import serialize_config_value, validation_errors
    from routes.config.keys import writable_config_keys

    result = CheckedPayload()
    writable = writable_config_keys()
    env_only = env_only_keys()
    secrets: set[str] = set()
    if mode == "import":
        from routes.config.io import _secret_import_keys

        secrets = _secret_import_keys()

    for key, value in data.items():
        if key in secrets:
            result.skipped_secrets.append(key)
            continue
        if str(value) == MASK_SENTINEL:
            continue
        if key in MASKED_BLOB_KEYS and isinstance(value, str):
            value = deep_unmask_blob(value, key)
            if value is None:
                result.refuse(key, f"Invalid JSON payload for {key}")
                continue
        if key in env_only:
            result.refuse(
                key,
                f"{key} is set by the environment (SUBLARR_{key.upper()}) and cannot be changed here",
            )
            continue
        if key not in writable and "." not in key:
            # A misspelled key used to report success and do nothing.
            result.refuse(key, f"Unknown config key: {key}")
            continue
        if mode == "import" and "." in key and not _importable_dotted(key):
            # A backup only carries non-secret catalog settings; plugin and
            # post-processing namespaces (scripts, commands) never come in
            # through an uploaded file.
            result.refuse(key, f"{key} cannot be imported")
            continue
        value, error = _check_value(key, value)
        if error:
            result.refuse(key, error)
            continue
        if isinstance(value, str):
            # Pasted credentials often carry a trailing newline.
            value = value.strip()
        result.values[key] = serialize_config_value(value)

    ui_values = {k: v for k, v in result.values.items() if k in UISettings.model_fields}
    for key, message in validation_errors(get_settings().ui, ui_values).items():
        result.values.pop(key, None)
        result.refuse(key, message)
    return result
