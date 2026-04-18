"""Cleanup API endpoints package.

Blueprint: /api/v1/cleanup

The package hosts the Blueprint object, shared scan state, and locks.
Route handlers live in domain-scoped submodules that import ``bp`` from
this package and register routes via @bp.route decorators.

Current submodules:
  - dedup: dedup scan + duplicate management
  - orphan: orphan subtitle scan + deletion
  - preview: generic dry-run + non-target-subs
  - rules: cleanup-rule CRUD + run + preview
  - stats: cleanup stats + history
"""

import logging
import threading

from flask import Blueprint

bp = Blueprint("cleanup", __name__, url_prefix="/api/v1/cleanup")
logger = logging.getLogger(__name__)

# Module-level scan state (same pattern as wanted_scanner)
_scan_state = {
    "running": False,
    "scan_id": None,
    "progress": 0,
    "total": 0,
    "result": None,
}
_scan_lock = threading.Lock()

# Module-level orphan state
_orphan_state = {
    "running": False,
    "result": None,
}
_orphan_lock = threading.Lock()

# Submodule imports — triggers @bp.route decorator registration
from routes.cleanup import dedup, orphan, preview, rules, stats  # noqa: E402, F401
