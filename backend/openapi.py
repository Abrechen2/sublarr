"""OpenAPI specification for Sublarr API.

Provides a module-level APISpec instance and a helper to register all
Flask view functions that contain YAML docstrings.
"""

import logging

from apispec import APISpec
from apispec_webframeworks.flask import FlaskPlugin

from version import __version__

logger = logging.getLogger(__name__)

spec = APISpec(
    title="Sublarr API",
    version=__version__,
    openapi_version="3.0.3",
    info={
        "description": "Standalone Subtitle Manager & Translator for Anime/Media",
        "license": {"name": "GPL-3.0", "url": "https://www.gnu.org/licenses/gpl-3.0.html"},
    },
    plugins=[FlaskPlugin()],
)

# Security scheme for optional API key authentication
spec.components.security_scheme(
    "apiKeyAuth",
    {
        "type": "apiKey",
        "in": "header",
        "name": "X-Api-Key",
        "description": "Optional API key for authenticated endpoints",
    },
)


def register_all_paths(app):
    """Register all Flask view functions with YAML docstrings into the spec.

    Must be called AFTER register_blueprints() and within app context so all
    views are discoverable. Silently skips views without ``---`` markers or
    that fail parsing.
    """
    registered = 0
    skipped = 0

    with app.test_request_context():
        for name, view_func in app.view_functions.items():
            # Skip static file serving
            if name == "static":
                continue

            # Only process views with YAML docstrings (contain '---')
            docstring = getattr(view_func, "__doc__", None) or ""
            if "---" not in docstring:
                skipped += 1
                continue

            try:
                spec.path(view=view_func)
                registered += 1
            except Exception as exc:
                logger.debug("Skipped OpenAPI path for %s: %s", name, exc)
                skipped += 1

    logger.info("OpenAPI: registered %d paths, skipped %d views", registered, skipped)
