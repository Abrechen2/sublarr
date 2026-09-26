"""Allow-list config snapshot for the support bundle.

``Settings.get_safe_config()`` is a deny-list: it masks names containing
password/pin/secret/token/key and ships every other value in clear. For the
bundle a user attaches to a public bug report that is the wrong default —
usernames, internal URLs, trusted proxy IPs, path mappings and the media path
all went out verbatim, and any future credential field whose name lacks one of
the five words would have too.

Here the rule is inverted. A value ships in clear only when it is a bool, int,
float or ``Literal`` choice, or a string field named in ``SAFE_STRING_FIELDS``.
URL fields are reduced to scheme, host class and port. Every other string is
replaced by a presence marker. The finished dict then runs through ``redact()``
with the snapshot's own secret values, as a second line of defence.
"""

from __future__ import annotations

import ipaddress
import types
import typing
from urllib.parse import urlsplit

from config_settings import BootSettings, UISettings, is_sensitive_config_key
from secret_redaction import collect_secret_values, redact, scrub_tree

# Shown instead of a masked value when something is configured; "" otherwise.
MASK_SET = "***configured***"

# String settings that describe behaviour, not the installation: languages,
# enum-like modes, provider names, model names. Adding a field here is a
# statement that its value can never identify a user, host or path.
SAFE_STRING_FIELDS: frozenset[str] = frozenset(
    {
        "log_level",
        "log_format",
        "ollama_model",
        "source_language",
        "target_language",
        "source_language_name",
        "target_language_name",
        "auto_translate_source_languages",
        "translation_default_backend",
        "translation_default_fallback",
        "provider_priorities",
        "providers_enabled",
        "providers_hidden",
        "provider_language_excludes_json",
        "proxy_auth_header",
        "scan_metadata_engine",
        "ai_quality_model",
        "cleanup_foreign_tracks_keep_languages",
        "cleanup_signs_removal_level",
        "release_group_prefer",
        "release_group_exclude",
        "hi_preference",
        "forced_preference",
        "auto_sync_engine",
        "auto_process_common_fixes_config_json",
        "auto_process_sync_fallback_engine",
        "wanted_search_order",
        "provider_budget_stretch_mode",
        "scheduler_profile",
        "anti_captcha_provider",
        "remux_hardlink_policy",
        "auto_cleanup_keep_languages",
        "auto_cleanup_keep_formats",
        "anidb_custom_field_name",
        "interface_language",
        "default_library_view",
        "default_library_sort",
        "datetime_format",
        "subtitle_language_code_format",
        "subtitle_suffix_separator",
        "subtitle_hi_suffix",
        "subtitle_forced_suffix",
        "quiet_hours_start",
        "quiet_hours_end",
        "quiet_hours_timezone",
        "scan_ignore_languages",
        "score_threshold_per_language",
    }
)

_SCALAR_TYPES = (bool, int, float)
_URL_SUFFIXES = ("_url", "_endpoint")


def _field_annotations() -> dict[str, object]:
    return {
        name: field.annotation
        for model in (BootSettings, UISettings)
        for name, field in model.model_fields.items()
    }


def _is_clear_type(annotation: object) -> bool:
    """bool/int/float, a Literal choice, or an Optional of those."""
    if annotation in _SCALAR_TYPES:
        return True
    origin = typing.get_origin(annotation)
    if origin is typing.Literal:
        return True
    if origin in (typing.Union, types.UnionType):
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        return bool(args) and all(_is_clear_type(a) for a in args)
    return False


def _host_class(host: str) -> str:
    if host == "localhost":
        return "<loopback>"
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return "<host>"
    if addr.is_loopback:
        return "<loopback>"
    if addr.is_private or addr.is_link_local:
        return "<private-ip>"
    return "<public-ip>"


def _reduce_url(value: str) -> str:
    """``scheme://<host class>[:port]`` — enough to tell local from remote."""
    try:
        parts = urlsplit(value.strip())
        port = parts.port
    except ValueError:
        return MASK_SET
    if not parts.scheme or not parts.hostname:
        return MASK_SET
    suffix = f":{port}" if port else ""
    return f"{parts.scheme}://{_host_class(parts.hostname)}{suffix}"


def _masked(value: object) -> object:
    if value in ("", None, [], {}):
        return value
    return MASK_SET


def _snapshot_value(name: str, value: object, annotation: object) -> object:
    if is_sensitive_config_key(name):
        return _masked(value)
    if _is_clear_type(annotation) or name in SAFE_STRING_FIELDS:
        return value
    if name.endswith(_URL_SUFFIXES) and isinstance(value, str) and value.strip():
        return _reduce_url(value)
    return _masked(value)


def build_config_snapshot(settings) -> dict:
    """The config as it may appear in a support bundle."""
    annotations = _field_annotations()
    snapshot = {
        name: _snapshot_value(name, value, annotations.get(name))
        for name, value in settings.model_dump().items()
    }
    # Second layer: a secret that slipped into an allow-listed value (a key
    # pasted into the wrong field) is still caught by value and by shape.
    secrets = collect_secret_values(settings)
    return scrub_tree(snapshot, lambda text: redact(text, values=secrets))
