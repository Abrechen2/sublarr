"""Plugin marketplace routes package.

Split from the flat routes/marketplace.py (B1M, 2026-04-18). The Blueprint,
`_marketplace` singleton, and `get_marketplace()` helper live here so
submodules can reach them via `from routes.marketplace import ...`.
"""

import logging

from flask import Blueprint

from config import get_settings
from services.marketplace import PluginMarketplace

bp = Blueprint("marketplace", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)

# Singleton marketplace instance
_marketplace: PluginMarketplace | None = None


def get_marketplace() -> PluginMarketplace:
    """Get or create marketplace instance."""
    global _marketplace
    if _marketplace is None:
        settings = get_settings()
        registry_url = getattr(settings, "plugin_registry_url", None)
        if registry_url:
            _marketplace = PluginMarketplace(registry_url)
        else:
            _marketplace = PluginMarketplace()  # Use default registry
    return _marketplace


# Register route submodules — must come after bp and helpers are defined.
from routes.marketplace import (  # noqa: E402, F401
    browse,
    install,
)
