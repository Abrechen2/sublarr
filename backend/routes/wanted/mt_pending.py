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

import logging

from flask import jsonify

from db.repositories.wanted import WantedRepository
from db.wanted import get_wanted_item, set_mt_pending_original, set_mt_pinned
from routes.wanted import bp

logger = logging.getLogger(__name__)


def _load_pending_payload(item: dict) -> dict | None:
    from services.mt_pending_approval import load_pending_payload

    return load_pending_payload(item)


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
    from services.mt_pending_approval import batch_state

    items = WantedRepository().get_mt_pending_items()
    return jsonify({"data": items, "total": len(items), "batch": batch_state()})


@bp.route("/wanted/mt-pending/approve-batch", methods=["POST"])
def approve_mt_pending_batch():
    """Approve several pending originals in the background.
    ---
    post:
      tags:
        - Wanted
      summary: Approve pending originals in bulk
      description: >
        Validates the ids and answers immediately; the originals are installed
        one after another in the background, each exactly like the single
        approve — one that does not install keeps its machine translation and
        its pending marker. Progress is reported in the ``batch`` field of
        ``GET /wanted/mt-pending``. Items without a pending original are skipped.
      security:
        - apiKeyAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [item_ids]
              properties:
                item_ids:
                  type: array
                  items:
                    type: integer
                  description: Wanted item IDs (max 500)
      responses:
        202:
          description: Batch accepted
          content:
            application/json:
              schema:
                type: object
                properties:
                  accepted:
                    type: array
                    items:
                      type: integer
                  skipped:
                    type: array
                    items:
                      type: integer
        400:
          description: Invalid input
        409:
          description: A batch is already running
    """
    from flask import current_app, request

    from services.mt_pending_approval import start_batch

    data = request.get_json(silent=True) or {}
    item_ids = data.get("item_ids")
    if not item_ids or not isinstance(item_ids, list):
        return jsonify({"error": "item_ids must be a non-empty list of integers"}), 400
    if len(item_ids) > 500:
        return jsonify({"error": "Maximum 500 items per batch"}), 400
    if not all(isinstance(i, int) and not isinstance(i, bool) for i in item_ids):
        return jsonify({"error": "item_ids must contain only integers"}), 400

    accepted, skipped = [], []
    for item_id in dict.fromkeys(item_ids):
        item = get_wanted_item(item_id)
        if item and _load_pending_payload(item) is not None:
            accepted.append(item_id)
        else:
            skipped.append(item_id)
    if not accepted:
        return jsonify(
            {"error": "None of the items has a pending original", "skipped": skipped}
        ), 400

    if not start_batch(current_app._get_current_object(), accepted):
        return jsonify({"error": "A batch approval is already running"}), 409
    return jsonify({"accepted": accepted, "skipped": skipped}), 202


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
        409:
          description: Original could not be installed; machine translation kept
    """
    from services.mt_pending_approval import approve_one

    item = get_wanted_item(item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

    payload = _load_pending_payload(item)
    if payload is None:
        return jsonify({"error": "No pending original for this item"}), 400

    if not approve_one(item, payload):
        # Nothing was installed and the machine translation is back in place.
        # Keep the marker so the approve can be retried from the modal.
        return (
            jsonify(
                {
                    "error": "Original could not be installed; machine translation kept",
                    "id": item_id,
                }
            ),
            409,
        )
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
