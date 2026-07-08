"""Tests for backend.version -- RC-tag visibility.

Regression: a running RC container's health/footer always reported the
static backend/VERSION content (e.g. "1.6.5"), never the actual image tag
(e.g. "1.6.5-rc.2") baked in via `docker build --build-arg VERSION=$RC_TAG` --
the Dockerfile only used that build-arg for an OCI label, never exposed it to
the running app. Confirmed 2026-07-08 while testing 1.6.5-rc.2 on the RC
server: the footer showed "1.6.5" with no way to tell it apart from prod.
"""

from version import _resolve_version


def test_prefers_env_value_when_set(tmp_path):
    version_file = tmp_path / "VERSION"
    version_file.write_text("1.6.5")

    assert _resolve_version("1.6.5-rc.2", str(version_file)) == "1.6.5-rc.2"


def test_falls_back_to_version_file_when_env_unset(tmp_path):
    version_file = tmp_path / "VERSION"
    version_file.write_text("1.6.5")

    assert _resolve_version(None, str(version_file)) == "1.6.5"
    assert _resolve_version("", str(version_file)) == "1.6.5"
    assert _resolve_version("   ", str(version_file)) == "1.6.5"


def test_falls_back_to_dev_when_both_missing(tmp_path):
    missing = tmp_path / "does-not-exist"

    assert _resolve_version(None, str(missing)) == "0.0.0-dev"


def test_strips_whitespace_from_env_value(tmp_path):
    version_file = tmp_path / "VERSION"
    version_file.write_text("1.6.5")

    assert _resolve_version("  1.6.5-rc.2  \n", str(version_file)) == "1.6.5-rc.2"
