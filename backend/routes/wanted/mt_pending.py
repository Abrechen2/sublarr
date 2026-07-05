"""Pending-original approve/reject routes (feature #8b, Phase 2, Task 3).

Exposes the ``mt_on_original_found="notify"`` signal recorded by
``services.mt_reseek._record_pending_notification`` on
``WantedItem.mt_pending_original`` (migration 3c4b1a2d5e6f) — see that
module's docstring for the full provisional-MT re-seek lifecycle.

Deliberately NOT built on the outbound notification system
(``db/models/notifications.py``, ``routes/notifications_mgmt``, ``notifier.py``)
— that system fires external alerts (webhooks/Discord). This is a much
smaller, purely internal in-app signal living directly on the wanted row:

- ``GET /wanted/mt-pending`` — list every item with a pending original.
- ``POST /wanted/<id>/mt-pending/approve`` — install the stored original by
  reusing ``services.mt_reseek._replace_original`` (the exact same
  trash-then-install path ``mt_on_original_found="auto_replace"`` uses),
  then clear the pending marker (it is consumed either way — see
  ``_replace_original``'s docstring for the rare race where the stored
  candidate no longer reproduces).
- ``POST /wanted/<id>/mt-pending/reject`` — clear the pending marker AND pin
  the item (``mt_pinned=1``) so ``services.mt_reseek`` never re-notifies for
  the same MT (mirrors the pinning contract in ``mt_reseek._is_pinned``).

Status-code convention: an unknown ``item_id`` is 404 (no such resource).
An item that exists but has no pending original is 400 — the resource
exists but the requested action does not apply to its current state,
matching ``update_wanted_item_status``'s 400-for-invalid-state handling in
``routes/wanted/list.py`` (as opposed to 404, which would imply the item
itself is missing).
"""

from __future__ import annotations

import json
import logging

from flask import jsonify

from db.repositories.wanted import WantedRepository
from db.wanted import get_wanted_item, set_mt_pending_original, set_mt_pinned
from routes.wanted import bp

logger = logging.getLogger(__name__)


def _load_pending_payload(item: dict) -> dict | None:
    """Parse ``item['mt_pending_original']`` into a dict, or ``None`` if
    absent/unparseable. Unparseable payloads are logged and treated as
    "nothing pending" rather than raising — a corrupt marker must not make
    the item permanently un-actionable via this API."""
    raw = item.get("mt_pending_original")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("mt-pending: unparseable mt_pending_original for wanted %s", item.get("id"))
        return None


@bp.route("/wanted/mt-pending", methods=["GET"])
def list_mt_pending():
    """List wanted items with a pending-original notification.
    ---
    get:
      tags:
        - Wanted
      summary: List pending-original notifications
      description: >
        Returns every wanted item currently carrying a pending-original
        notification (``mt_on_original_found="notify"`` found a qualifying
        provider/embedded original for a provisional machine translation).
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Pending-original items
          content:
            application/json:
              schema:
                type: object
                properties:
                  data:
                    type: array
                    items:
                      type: object
                  total:
                    type: integer
    """
    items = WantedRepository().get_mt_pending_items()
    return jsonify({"data": items, "total": len(items)})


@bp.route("/wanted/<int:item_id>/mt-pending/approve", methods=["POST"])
def approve_mt_pending(item_id):
    """Approve a pending original: install it in place of the MT.
    ---
    post:
      tags:
        - Wanted
      summary: Approve pending original
      description: >
        Installs the genuine original recorded by a prior notify-mode
        re-seek pass (trashes the superseded machine-translation sidecar
        first, then re-runs the original-only search for real) and clears
        the pending marker.
      security:
        - apiKeyAuth: []
      parameters:
        - in: path
          name: item_id
          required: true
          schema:
            type: integer
          description: Wanted item ID
      responses:
        200:
          description: Approved
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  id:
                    type: integer
        400:
          description: Item has no pending original
        404:
          description: Item not found
    """
    from services.mt_reseek import _replace_original

    item = get_wanted_item(item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

    payload = _load_pending_payload(item)
    if payload is None:
        return jsonify({"error": "No pending original for this item"}), 400

    _replace_original(item, payload)
    # Consumed either way: on success the wanted row is deleted by the normal
    # success path (this is then a harmless no-op); on the rare race where the
    # candidate doesn't reproduce, the stale marker must not linger either —
    # the next re-seek pass will record a fresh one if it finds another.
    set_mt_pending_original(item_id, None)

    return jsonify({"status": "approved", "id": item_id})


@bp.route("/wanted/<int:item_id>/mt-pending/reject", methods=["POST"])
def reject_mt_pending(item_id):
    """Reject a pending original: keep the MT, stop re-notifying.
    ---
    post:
      tags:
        - Wanted
      summary: Reject pending original
      description: >
        Clears the pending-original marker and pins the item
        (``mt_pinned=1``) so the ``mt_reseek`` job never re-selects or
        re-notifies for this provisional machine translation again.
      security:
        - apiKeyAuth: []
      parameters:
        - in: path
          name: item_id
          required: true
          schema:
            type: integer
          description: Wanted item ID
      responses:
        200:
          description: Rejected
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  id:
                    type: integer
        400:
          description: Item has no pending original
        404:
          description: Item not found
    """
    item = get_wanted_item(item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

    payload = _load_pending_payload(item)
    if payload is None:
        return jsonify({"error": "No pending original for this item"}), 400

    set_mt_pending_original(item_id, None)
    set_mt_pinned(item_id, True)

    return jsonify({"status": "rejected", "id": item_id})
