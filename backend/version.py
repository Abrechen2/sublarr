"""Centralized version string for Sublarr.

Read from backend/VERSION (single source of truth for Docker and runtime).
Fallback to 0.0.0-dev if file is missing or unreadable.
"""

import os

_VERSION_FILE = os.path.join(os.path.dirname(__file__), "VERSION")
__version__ = "0.0.0-dev"

try:
    if os.path.isfile(_VERSION_FILE):
        with open(_VERSION_FILE, encoding="utf-8") as f:
            __version__ = f.read().strip() or __version__
except (OSError, IOError):
    pass
