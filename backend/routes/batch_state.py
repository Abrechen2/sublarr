"""Shared in-memory batch state for translate and wanted routes.

These module-level dicts are mutated by translate/wanted routes and read by
the system /stats and /tasks endpoints. Keeping them here avoids system.py
importing from translate.py and wanted.py.
"""

import threading
import time

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

stats_lock = threading.Lock()
_memory_stats = {
    "started_at": time.time(),
    "upgrades": {"srt_to_ass_translated": 0, "srt_upgrade_skipped": 0},
    "quality_warnings": 0,
}

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
