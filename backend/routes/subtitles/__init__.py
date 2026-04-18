"""Subtitle sidecar management routes package.

Filesystem-based discovery, soft-deletion (trash), restore, and export of
subtitle sidecar files (.lang.ass, .lang.srt, etc.) next to video files.

Submodules:
    helpers.py   — scan_subtitle_sidecars + trash helpers
    sidecars.py  — GET /library/{episodes|movies|series}/<id>/subtitles
    trash.py     — DELETE /library/subtitles, batch-delete, list/restore/purge trash
    export.py    — series ZIP export + single-file download

Endpoints:
  GET  /library/episodes/<ep_id>/subtitles
  GET  /library/series/<series_id>/subtitles
  GET  /library/movies/<movie_id>/subtitles
  DELETE /library/subtitles
  POST /library/series/<series_id>/subtitles/batch-delete
  GET  /library/trash
  POST /library/trash/<batch_id>/restore
  DELETE /library/trash/<batch_id>
  GET  /subtitles/download?path=
  GET  /series/<series_id>/subtitles/export
"""

import logging

from flask import Blueprint

bp = Blueprint("subtitles", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)

# Submodule imports — decorators register routes at import time.
from routes.subtitles import export, sidecars, trash  # noqa: E402, F401

# Public re-exports (tests + external callers depend on these):
# - cleanup_scheduler.py:323            — _auto_purge_old_trash
# - routes/remux.py:351                 — _get_trash_root, _read_manifest
# - routes/subtitle_processor.py:329    — scan_subtitle_sidecars
# - routes/tracks.py:200                — scan_subtitle_sidecars (lazy, patched in tests)
# - routes/trash.py:68                  — _get_trash_root, _read_manifest
# - routes/video_sync.py:245            — scan_subtitle_sidecars
# - tests/test_routes_subtitles.py      — scan_subtitle_sidecars
from routes.subtitles.helpers import (  # noqa: E402, F401
    _auto_purge_old_trash,
    _get_trash_root,
    _read_manifest,
    scan_subtitle_sidecars,
)
