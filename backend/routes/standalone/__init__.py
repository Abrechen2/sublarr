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

# Submodule imports run at the bottom so `bp` is already defined when the
# @bp.route decorators execute at import time.
from routes.standalone import folders, movies, scan, series  # noqa: E402, F401
