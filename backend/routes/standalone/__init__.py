"""Standalone mode API endpoints.

Manages watched folders, standalone series/movies, metadata refresh,
and scanner control for folder-watch mode without Sonarr/Radarr.

Business logic lives in ``services.standalone_manager``; these modules
contain only thin HTTP adapter handlers and OpenAPI docstrings.

Package layout:
    folders.py  — /folders GET, POST, PUT, DELETE
    series.py   — /series GET, /series/<id> GET, poster, DELETE, scan, refresh-metadata
    movies.py   — /movies GET, /movies/<id> GET, poster, DELETE
    scan.py     — /scan, /scan/<folder_id>, /status
"""

from flask import Blueprint

bp = Blueprint("standalone", __name__, url_prefix="/api/v1/standalone")


# Endpoints that need the sign themselves (a positive id may be Radarr's).
_SIGN_AWARE_ENDPOINTS = frozenset({"standalone.get_movie"})


@bp.url_value_preprocessor
def _accept_wire_ids(_endpoint, values):
    """Accept both id forms in this standalone-only namespace.

    The library hands out negative ids for standalone series/movies
    (docs/specs/standalone-ids.md); these routes keep taking the positive row
    id too. Both name the same row here.
    """
    if not values or _endpoint in _SIGN_AWARE_ENDPOINTS:
        return
    for key in ("series_id", "movie_id"):
        value = values.get(key)
        if isinstance(value, int) and value < 0:
            values[key] = -value


# Submodule imports run at the bottom so `bp` is already defined when the
# @bp.route decorators execute at import time.
from routes.standalone import folders, movies, scan, series  # noqa: E402, F401
