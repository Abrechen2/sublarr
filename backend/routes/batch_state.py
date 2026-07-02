"""Shared in-memory batch state for translate and wanted routes.

These module-level dicts are mutated by translate/wanted routes and read by
the system /stats and /tasks endpoints. Keeping them here avoids system.py
importing from translate.py and wanted.py.
"""

import threading

# Translation stats state moved to services.translation_jobs (2026-07-02) so
# the job runner lives entirely in the services layer. Re-exported here for
# routes that still import it from routes.batch_state (same dict/lock objects).
from services.translation_jobs import _memory_stats, stats_lock  # noqa: F401

# --- Translation batch state ------------------------------------------------

batch_state = {
    "running": False,
    "total": 0,
    "processed": 0,
    "succeeded": 0,
    "failed": 0,
    "skipped": 0,
    "current_file": None,
    "errors": [],
}
batch_lock = threading.Lock()

# --- Wanted batch-search state ----------------------------------------------

wanted_batch_state = {
    "running": False,
    "total": 0,
    "processed": 0,
    "found": 0,
    "failed": 0,
    "skipped": 0,
    "current_item": None,
}
wanted_batch_lock = threading.Lock()

# --- Wanted batch-extract state ---------------------------------------------

_batch_extract_state = {
    "running": False,
    "total": 0,
    "processed": 0,
    "succeeded": 0,
    "failed": 0,
    "skipped": 0,
    "current_item": None,
}
_batch_extract_lock = threading.Lock()

# --- Wanted batch-probe state -----------------------------------------------

_batch_probe_state = {
    "running": False,
    "total": 0,
    "processed": 0,
    "found": 0,
    "extracted": 0,
    "skipped": 0,
    "failed": 0,
    "current_item": None,
}
_batch_probe_lock = threading.Lock()
