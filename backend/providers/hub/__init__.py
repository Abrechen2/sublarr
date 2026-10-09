"""Subtitle providers taken over from the Bazarr+ Provider Hub catalog.

The bundles under ``bundles/`` are copied verbatim from
https://github.com/LavX/bazarr-provider-catalog at the commits recorded in
``bundles/SOURCES.json`` (MIT, see ``bundles/LICENSE``). They are reviewed
and pinned here instead of being fetched at runtime: Bazarr+ isolates each
bundle in its own worker process, Sublarr runs them in-process, so code from
another repository must not change under us without a review.

Each bundle's files are checked against the SHA-256 in its manifest before
it is imported; an edited file is refused, not loaded. ``scripts/
sync_provider_catalog.py`` shows what changed upstream and copies a reviewed
bundle across.

Which catalog providers are NOT here, and why:
- duplicates of a provider Sublarr already ships (addic7ed, subdl, ...);
- the eight that need the cloudscraper/Js2Py stack (Js2Py had a sandbox
  escape, CVE-2024-28397);
- the SDK smoke provider, whisperai and embeddedsubtitles (Sublarr has its
  own Whisper and embedded-track handling).
"""

from __future__ import annotations

import functools
import hashlib
import importlib.util
import json
import logging
import os
import sys
import threading

from providers.hub.adapter import HubProvider, config_key
from providers.hub.languages import manifest_languages

logger = logging.getLogger(__name__)

_LOAD_LOCK = threading.Lock()
BUNDLES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bundles")


def _field_type(schema: dict, secret: bool) -> str:
    if secret:
        return "password"
    kind = schema.get("type")
    if kind == "boolean":
        return "checkbox"
    if schema.get("enum"):
        return "select"
    if kind in ("integer", "number"):
        return "number"
    return "text"


def _default_text(value) -> str:
    """A schema default as ``config_entries`` stores it: always a string."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def config_fields_for(hub_id: str, manifest: dict) -> list[dict]:
    """Sublarr ``config_fields`` from a bundle manifest's JSON-schema subset."""
    schema = manifest.get("config_schema") or {}
    required = set(schema.get("required") or [])
    secrets = set(manifest.get("secret_fields") or [])
    fields = []
    for prop, spec in (schema.get("properties") or {}).items():
        secret = prop in secrets or bool(spec.get("secret"))
        field = {
            "key": config_key(hub_id, prop),
            "label": spec.get("title") or prop,
            "type": _field_type(spec, secret),
            "required": prop in required,
            "default": _default_text(spec.get("default")),
            "help": spec.get("description") or "",
        }
        if spec.get("enum"):
            field["options"] = [str(option) for option in spec["enum"]]
        fields.append(field)
    return fields


def verify_bundle(bundle_dir: str, manifest: dict) -> list[str]:
    """Files whose content no longer matches the manifest's SHA-256.

    The entry module has to be one of the hashed files: a manifest that does
    not list it would otherwise load unchecked code.
    """
    files = manifest.get("files") or {}
    entry = f"{manifest.get('entry_module') or 'provider'}.py"
    bad = [] if entry in files else [entry]
    for name, expected in files.items():
        path = os.path.join(bundle_dir, name)
        if os.path.basename(name) != name or not os.path.isfile(path):
            bad.append(name)
            continue
        with open(path, "rb") as fh:
            if hashlib.sha256(fh.read()).hexdigest() != expected:
                bad.append(name)
    return bad


def _load_impl(hub_id: str, bundle_dir: str, manifest: dict) -> type:
    """Import the bundle's entry class under a private module name."""
    module_name = f"sublarr_hub_{hub_id}"
    entry = manifest.get("entry_module") or "provider"
    spec = importlib.util.spec_from_file_location(
        module_name, os.path.join(bundle_dir, f"{entry}.py")
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {entry}.py")
    module = importlib.util.module_from_spec(spec)
    # Bundles with helper modules import them by bare name (``captcha_templates``).
    # sys.path is process-wide, so two loads must not interleave.
    with _LOAD_LOCK:
        added = bundle_dir not in sys.path
        if added:
            sys.path.insert(0, bundle_dir)
        try:
            spec.loader.exec_module(module)
        finally:
            if added:
                sys.path.remove(bundle_dir)
    return getattr(module, manifest["entry_class"])


def build_provider_class(hub_id: str, bundle_dir: str, manifest: dict) -> type[HubProvider]:
    impl = _load_impl(hub_id, bundle_dir, manifest)
    return type(
        f"Hub{manifest['entry_class']}",
        (HubProvider,),
        {
            "name": hub_id,
            "hub_id": hub_id,
            "manifest": manifest,
            "impl_class": impl,
            "languages": manifest_languages(manifest.get("languages") or []),
            "config_fields": config_fields_for(hub_id, manifest),
            "__module__": __name__,
        },
    )


def discover_bundles(bundles_dir: str = BUNDLES_DIR) -> list[tuple[str, str, dict]]:
    found = []
    for hub_id in sorted(os.listdir(bundles_dir)):
        bundle_dir = os.path.join(bundles_dir, hub_id)
        manifest_path = os.path.join(bundle_dir, "provider.json")
        if not os.path.isfile(manifest_path):
            continue
        with open(manifest_path, encoding="utf-8") as fh:
            manifest = json.load(fh)
        if manifest.get("provider_id") != hub_id:
            logger.warning(
                "hub: %s declares provider_id %r, skipped", hub_id, manifest.get("provider_id")
            )
            continue
        found.append((hub_id, bundle_dir, manifest))
    return found


def secret_config_keys(bundles_dir: str = BUNDLES_DIR) -> set[str]:
    """``config_entries`` keys that hold credentials, from the manifests alone."""
    keys = set()
    for hub_id, _bundle_dir, manifest in discover_bundles(bundles_dir):
        for field in config_fields_for(hub_id, manifest):
            if field["type"] == "password":
                keys.add(field["key"])
    return keys


@functools.lru_cache(maxsize=1)
def _vendored_secret_keys() -> frozenset[str]:
    return frozenset(secret_config_keys())


def is_hub_secret_key(key: str) -> bool:
    """Whether a ``hub.<id>.<field>`` key holds a credential (manifest ``secret_fields``)."""
    return key in _vendored_secret_keys()


def register_hub_providers(bundles_dir: str = BUNDLES_DIR) -> list[str]:
    """Register every intact bundle; return the names that were registered."""
    from providers.registry import _PROVIDER_CLASSES, register_provider

    registered = []
    for hub_id, bundle_dir, manifest in discover_bundles(bundles_dir):
        if hub_id in _PROVIDER_CLASSES:
            continue
        bad = verify_bundle(bundle_dir, manifest)
        if bad:
            logger.warning(
                "hub: %s refused, files differ from its manifest: %s", hub_id, ", ".join(bad)
            )
            continue
        try:
            register_provider(build_provider_class(hub_id, bundle_dir, manifest))
        except Exception as exc:  # noqa: BLE001 — one bad bundle must not stop the rest
            logger.warning("hub: %s could not be loaded: %s", hub_id, exc)
            continue
        registered.append(hub_id)
    if registered:
        logger.info("hub: %d catalog providers available", len(registered))
    return registered


__all__ = [
    "BUNDLES_DIR",
    "HubProvider",
    "build_provider_class",
    "config_fields_for",
    "discover_bundles",
    "is_hub_secret_key",
    "register_hub_providers",
    "secret_config_keys",
    "verify_bundle",
]
