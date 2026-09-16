"""Approve pending originals — one item or a batch in the background.

A pending original is a genuine subtitle the re-seek job found for an episode
that only has a machine translation (see ``services.mt_reseek``). Approving it
runs a real provider search and install, about 30 seconds per item, so a batch
cannot be a single request: ``claim_batch`` + ``run_batch`` process the items
one after another on a background thread and publish progress through
``batch_state`` for the pending list to report.

Every approval — single or batched — goes through ``approve_one``, so a batch
gets exactly the single-item guarantees: an original that does not install
leaves the machine translation in place and keeps the pending marker.
"""

from __future__ import annotations

import json
import logging
import threading

from services.background_tasks import submit_background

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_state: dict = {"running": False, "total": 0, "done": 0, "installed": 0, "kept": 0}


def load_pending_payload(item: dict) -> dict | None:
    """Parse ``item['mt_pending_original']``; ``None`` if absent or unparseable.

    A corrupt marker is logged and treated as "nothing pending" rather than
    raising, so it cannot make the item permanently un-actionable.
    """
    raw = item.get("mt_pending_original")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("mt-pending: unparseable mt_pending_original for wanted %s", item.get("id"))
        return None


def approve_one(item: dict, payload: dict) -> bool:
    """Install the pending original; clear the marker only when it installed."""
    from db.wanted import set_mt_pending_original
    from services.mt_reseek import _replace_original

    if not _replace_original(item, payload):
        return False
    # On success the wanted row is deleted by the normal success path; this
    # is then a harmless no-op.
    set_mt_pending_original(item["id"], None)
    return True


def batch_state() -> dict:
    """A copy of the current (or last) batch's progress."""
    with _lock:
        return dict(_state)


def claim_batch(item_ids: list[int]) -> bool:
    """Mark a batch as running; False if one is already in progress."""
    with _lock:
        if _state["running"]:
            return False
        _state.update(running=True, total=len(item_ids), done=0, installed=0, kept=0)
        return True


def start_batch(app, item_ids: list[int]) -> bool:
    """Claim and submit a batch; False if one is already running."""
    if not claim_batch(item_ids):
        return False
    submit_background(run_batch, app, list(item_ids))
    return True


def run_batch(app, item_ids: list[int]) -> None:
    """Approve each item in order; a failing item never stops the batch."""
    from db.wanted import get_wanted_item

    try:
        for item_id in item_ids:
            installed = False
            try:
                with app.app_context():
                    item = get_wanted_item(item_id)
                    payload = load_pending_payload(item) if item else None
                    if item and payload is not None:
                        installed = approve_one(item, payload)
            except Exception:
                logger.exception("mt-pending batch: approving wanted %s failed", item_id)
            with _lock:
                _state["done"] += 1
                _state["installed" if installed else "kept"] += 1
    finally:
        with _lock:
            _state["running"] = False
        logger.info("mt-pending batch finished: %s", batch_state())


def reset_for_tests() -> None:
    with _lock:
        _state.update(running=False, total=0, done=0, installed=0, kept=0)
