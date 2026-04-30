"""Tests for providers.plugins.loader.discover_plugins.

The 2026-04-30 marketplace audit found that the loader only iterated
``*.py`` files at the top of ``plugins_dir``, while every marketplace
install lands at ``plugins_dir/<plugin_name>/...``. The route returned
``status: installed`` and persisted the DB row, but the manager's
reload() never picked the plugin up. This file pins both layouts so
the regression can't sneak back in.
"""

from __future__ import annotations

import os
import sys
import textwrap

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


_PROVIDER_SRC_FLAT = textwrap.dedent(
    """
    from providers.base import SubtitleProvider


    class FlatProvider(SubtitleProvider):
        name = "flat_provider"
        version = "1.0.0"

        def search(self, *a, **kw):
            return []

        def download(self, *a, **kw):
            return None
    """
).lstrip()


_PROVIDER_SRC_PKG = textwrap.dedent(
    """
    from providers.base import SubtitleProvider


    class PackagedProvider(SubtitleProvider):
        name = "packaged_provider"
        version = "1.0.0"

        def search(self, *a, **kw):
            return []

        def download(self, *a, **kw):
            return None
    """
).lstrip()


def _write(path, body):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)


def test_discover_finds_flat_layout(tmp_path):
    """Existing flat-file layout: plugins_dir/<name>.py."""
    from providers.plugins.loader import discover_plugins

    _write(str(tmp_path / "flat_provider.py"), _PROVIDER_SRC_FLAT)

    discovered, errors = discover_plugins(str(tmp_path), existing_names=set())

    assert errors == []
    assert "flat_provider" in discovered
    assert discovered["flat_provider"].__name__ == "FlatProvider"


def test_discover_finds_package_layout_via_provider_py(tmp_path):
    """Regression: marketplace ZIP installs land at plugins_dir/<name>/provider.py.

    Pre-fix the loader skipped subdirectories and the install endpoint
    silently ended up with status=installed but no live plugin.
    """
    from providers.plugins.loader import discover_plugins

    pkg = tmp_path / "packaged_provider"
    _write(str(pkg / "provider.py"), _PROVIDER_SRC_PKG)
    # __init__.py can be empty; provider.py is what actually carries the class.
    _write(str(pkg / "__init__.py"), "")

    discovered, errors = discover_plugins(str(tmp_path), existing_names=set())

    assert errors == [], f"unexpected errors: {errors}"
    assert "packaged_provider" in discovered
    assert discovered["packaged_provider"].__name__ == "PackagedProvider"


def test_discover_falls_back_to_init_py_when_no_provider_py(tmp_path):
    """If a package-layout plugin only has __init__.py (no provider.py)
    we still load it — the class must be defined directly in __init__.py."""
    from providers.plugins.loader import discover_plugins

    pkg = tmp_path / "init_only_plugin"
    _write(
        str(pkg / "__init__.py"),
        _PROVIDER_SRC_PKG.replace("PackagedProvider", "InitProvider").replace(
            "packaged_provider", "init_only_provider"
        ),
    )

    discovered, errors = discover_plugins(str(tmp_path), existing_names=set())

    assert errors == []
    assert "init_only_provider" in discovered


def test_discover_skips_underscore_and_dot_subdirs(tmp_path):
    """Subdirs starting with _ or . must be ignored (matches flat-layout rule)."""
    from providers.plugins.loader import discover_plugins

    _write(
        str(tmp_path / "_private" / "provider.py"),
        _PROVIDER_SRC_PKG.replace("PackagedProvider", "PrivateProvider").replace(
            "packaged_provider", "private_provider"
        ),
    )
    _write(
        str(tmp_path / ".hidden" / "provider.py"),
        _PROVIDER_SRC_PKG.replace("PackagedProvider", "HiddenProvider").replace(
            "packaged_provider", "hidden_provider"
        ),
    )

    discovered, errors = discover_plugins(str(tmp_path), existing_names=set())

    assert "private_provider" not in discovered
    assert "hidden_provider" not in discovered
    assert errors == []


def test_discover_handles_empty_subdirectory(tmp_path):
    """A subdir without provider.py or __init__.py is silently ignored
    (a left-behind empty folder must not register as an error)."""
    from providers.plugins.loader import discover_plugins

    (tmp_path / "empty_plugin").mkdir()

    discovered, errors = discover_plugins(str(tmp_path), existing_names=set())

    assert discovered == {}
    assert errors == []


def test_discover_mixed_layouts(tmp_path):
    """Flat and package layouts coexist in the same plugins_dir."""
    from providers.plugins.loader import discover_plugins

    _write(str(tmp_path / "flat_provider.py"), _PROVIDER_SRC_FLAT)
    _write(str(tmp_path / "packaged_provider" / "provider.py"), _PROVIDER_SRC_PKG)

    discovered, errors = discover_plugins(str(tmp_path), existing_names=set())

    assert errors == []
    assert "flat_provider" in discovered
    assert "packaged_provider" in discovered
