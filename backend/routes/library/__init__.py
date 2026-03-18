"""Library Blueprint package — library list, integrations, series, episodes."""

import logging

from flask import Blueprint

from services.glossary_extractor import extract_candidates  # noqa: F401 (patched in tests)

bp = Blueprint("library", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)

# Import submodules AFTER bp is defined — they register routes on bp
import routes.library.episodes  # noqa: E402, F401
import routes.library.integrations  # noqa: E402, F401
import routes.library.list  # noqa: E402, F401
import routes.library.series  # noqa: E402, F401
