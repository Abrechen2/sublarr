"""Centralized version string for Sublarr.

Prefers the SUBLARR_VERSION env var -- set by the Dockerfile from the
`--build-arg VERSION=$RC_TAG` passed at image build time -- so a running RC
container reports its actual tag (e.g. "1.6.5-rc.2") instead of the plain
release version. Falls back to backend/VERSION (single source of truth for
local dev, where no build-time env is set), then to 0.0.0-dev if both are
unavailable.
"""

import os

_VERSION_FILE = os.path.join(os.path.dirname(__file__), "VERSION")


def _resolve_version(env_value: str | None, version_file: str) -> str:
    if env_value and env_value.strip():
        return env_value.strip()
    try:
        if os.path.isfile(version_file):
            with open(version_file, encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return content
    except OSError:
        pass
    return "0.0.0-dev"


__version__ = _resolve_version(os.environ.get("SUBLARR_VERSION"), _VERSION_FILE)
