"""Plugin manifest dataclass and validation logic.

Validates that a discovered class is a valid SubtitleProvider plugin:
it must have a name, search/download methods, and be a SubtitleProvider
subclass. Name collisions with existing providers are rejected.

NOTE on safe import: Validation uses exception catching only, no sandboxing.
Plugins run in the same process, same trust model as Bazarr's plugin system.
A malicious plugin could do anything -- this is documented as a known
limitation. Validation catches accidental errors (missing methods, name
collisions, syntax errors), not intentional abuse.
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PluginManifest:
    """Metadata extracted from a plugin provider class."""

    name: str = ""
    version: str = "0.0.0"
    author: str = ""
    description: str = ""
    min_sublarr_version: str = ""
    config_fields: list[dict] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    requires_auth: bool = False


def validate_plugin(cls, existing_names: set[str]) -> tuple[bool, str]:
    """Validate that a class is a usable SubtitleProvider plugin.

    Checks:
        - cls has a non-empty 'name' attribute
        - cls.name is not already registered (no collision with built-ins)
        - cls has callable 'search' and 'download' methods
        - cls is a subclass of SubtitleProvider

    Args:
        cls: The class to validate.
        existing_names: Set of already-registered provider names.

    Returns:
        (True, "OK") if valid, or (False, reason_string) if not.
    """
    from providers.base import SubtitleProvider

    # Must be a class
    if not isinstance(cls, type):
        return False, f"{cls!r} is not a class"

    # Must be a SubtitleProvider subclass
    if not issubclass(cls, SubtitleProvider):
        return False, f"{cls.__name__} is not a SubtitleProvider subclass"

    # Must not be the abstract base class itself
    if cls is SubtitleProvider:
        return False, "Cannot register SubtitleProvider base class as plugin"

    # Must have a non-empty name
    name = getattr(cls, "name", "")
    if not name or name == "unknown":
        return False, f"{cls.__name__} has no 'name' attribute (or name is 'unknown')"

    # Name collision check
    if name in existing_names:
        return False, f"Name collision: '{name}' is already registered by a built-in provider"

    # Must have search method
    if not callable(getattr(cls, "search", None)):
        return False, f"{cls.__name__} missing required 'search' method"

    # Must have download method
    if not callable(getattr(cls, "download", None)):
        return False, f"{cls.__name__} missing required 'download' method"

    return True, "OK"


def extract_manifest(cls) -> PluginManifest:
    """Extract a PluginManifest from a provider class's attributes.

    Uses getattr with defaults for optional fields, so missing attributes
    are not an error.

    Args:
        cls: A validated SubtitleProvider subclass.

    Returns:
        PluginManifest with values read from class attributes.
    """
    languages = getattr(cls, "languages", set())
    if isinstance(languages, set):
        languages = sorted(languages)

    return PluginManifest(
        name=getattr(cls, "name", "unknown"),
        version=getattr(cls, "version", "0.0.0"),
        author=getattr(cls, "author", ""),
        description=getattr(cls, "description", cls.__doc__ or ""),
        min_sublarr_version=getattr(cls, "min_sublarr_version", ""),
        config_fields=getattr(cls, "config_fields", []),
        languages=languages,
        requires_auth=any(
            f.get("required", False) for f in getattr(cls, "config_fields", [])
        ),
    )
