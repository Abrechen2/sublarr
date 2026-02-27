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

    For each .py file (skipping files starting with '_' or '.'):
    1. Load the module using importlib
    2. Inspect members for SubtitleProvider subclasses
    3. Validate each discovered class

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

    # Collect .py files
    py_files = []
    for filename in sorted(os.listdir(plugins_dir)):
        if filename.startswith("_") or filename.startswith("."):
            continue
        if not filename.endswith(".py"):
            continue
        py_files.append(filename)

    if not py_files:
        logger.debug("No plugin files found in %s", plugins_dir)
        return discovered, errors

    logger.info("Scanning %d plugin file(s) in %s", len(py_files), plugins_dir)

    for filename in py_files:
        filepath = os.path.join(plugins_dir, filename)
        module_name = f"sublarr_plugin_{filename[:-3]}"

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
