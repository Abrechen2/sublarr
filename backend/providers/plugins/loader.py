"""importlib-based module loader for plugin files.

Scans a plugins directory for *.py files, loads them safely using
importlib, and discovers SubtitleProvider subclasses within each module.
Bad plugins (syntax errors, missing dependencies, etc.) are caught and
logged -- they never crash the application.
"""

import importlib.util
import inspect
import logging
import os
import sys

from providers.base import SubtitleProvider
from providers.plugins.manifest import validate_plugin

logger = logging.getLogger(__name__)


def discover_plugins(
    plugins_dir: str, existing_names: set[str]
) -> tuple[dict[str, type], list[dict]]:
    """Scan a directory for plugin provider Python files.

    Two layouts are supported:

    1. Flat: top-level ``<plugin_name>.py`` files in ``plugins_dir``.
    2. Package: ``plugins_dir/<plugin_name>/provider.py`` (or
       ``__init__.py`` as fallback) — this is the layout the marketplace
       install code creates from a downloaded ZIP.

    Files / dirs starting with ``_`` or ``.`` are skipped. For each
    candidate, we load the module via importlib and walk its members for
    ``SubtitleProvider`` subclasses, validating each one.

    Args:
        plugins_dir: Absolute path to the plugins directory.
        existing_names: Set of already-registered provider names.

    Returns:
        (discovered_classes_dict, errors_list) where:
            discovered_classes_dict: {name: cls} for valid plugins
            errors_list: [{"file": str, "error": str}] for failures
    """
    discovered: dict[str, type] = {}
    errors: list[dict] = []

    if not os.path.isdir(plugins_dir):
        logger.debug("Plugins directory does not exist: %s", plugins_dir)
        return discovered, errors

    # Each entry: (display_label, absolute_filepath, module_name)
    candidates: list[tuple[str, str, str]] = []
    for entry in sorted(os.listdir(plugins_dir)):
        if entry.startswith("_") or entry.startswith("."):
            continue
        full = os.path.join(plugins_dir, entry)

        # Layout 1: flat <name>.py
        if os.path.isfile(full) and entry.endswith(".py"):
            candidates.append((entry, full, f"sublarr_plugin_{entry[:-3]}"))
            continue

        # Layout 2: package directory — prefer provider.py, fall back to
        # __init__.py. Marketplace ZIP installs land here, so without this
        # branch every successful install was silently invisible to the
        # plugin manager (regression caught by the 2026-04-30 audit).
        if os.path.isdir(full):
            provider_py = os.path.join(full, "provider.py")
            init_py = os.path.join(full, "__init__.py")
            if os.path.isfile(provider_py):
                candidates.append((f"{entry}/provider.py", provider_py, f"sublarr_plugin_{entry}"))
            elif os.path.isfile(init_py):
                candidates.append((f"{entry}/__init__.py", init_py, f"sublarr_plugin_{entry}"))

    if not candidates:
        logger.debug("No plugin files found in %s", plugins_dir)
        return discovered, errors

    logger.info("Scanning %d plugin candidate(s) in %s", len(candidates), plugins_dir)

    for filename, filepath, module_name in candidates:
        try:
            # Load module using importlib
            spec = importlib.util.spec_from_file_location(module_name, filepath)
            if spec is None or spec.loader is None:
                errors.append({"file": filename, "error": "Could not create module spec"})
                continue

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # Find SubtitleProvider subclasses in the module
            found_in_file = False
            for member_name, member in inspect.getmembers(module, inspect.isclass):
                # Skip imported classes (only classes defined in this module)
                if member.__module__ != module_name:
                    continue

                # Skip the base class itself
                if member is SubtitleProvider:
                    continue

                if not issubclass(member, SubtitleProvider):
                    continue

                # Validate the plugin class
                # Track existing_names + already discovered in this scan
                all_existing = existing_names | set(discovered.keys())
                valid, reason = validate_plugin(member, all_existing)

                if valid:
                    discovered[member.name] = member
                    found_in_file = True
                    logger.info(
                        "Discovered plugin provider: %s (%s) from %s",
                        member.name,
                        member.__name__,
                        filename,
                    )
                else:
                    errors.append(
                        {
                            "file": filename,
                            "error": f"Validation failed for {member.__name__}: {reason}",
                        }
                    )

            if not found_in_file:
                # Module loaded OK but no valid providers found -- not necessarily an error
                logger.debug("No valid SubtitleProvider subclasses found in %s", filename)

        except Exception as e:
            # Catch ALL exceptions: SyntaxError, ImportError, AttributeError, etc.
            logger.warning(
                "Failed to load plugin %s: %s",
                filename,
                e,
                exc_info=True,
            )
            errors.append({"file": filename, "error": str(e)})
            # Clean up partial module load
            if module_name in sys.modules:
                del sys.modules[module_name]

    return discovered, errors


def unload_plugin(module_name: str) -> None:
    """Remove a plugin module from sys.modules.

    Args:
        module_name: The module name (e.g. 'sublarr_plugin_myprovider').
    """
    full_name = (
        module_name
        if module_name.startswith("sublarr_plugin_")
        else f"sublarr_plugin_{module_name}"
    )
    if full_name in sys.modules:
        del sys.modules[full_name]
        logger.debug("Unloaded plugin module: %s", full_name)
