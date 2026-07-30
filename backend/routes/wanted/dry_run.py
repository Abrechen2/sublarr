"""Wanted dry-run route — preview what the automation pipeline would pick.

POST /api/v1/wanted/dry-run runs ``process_wanted_item(dry_run=True)`` for a
small batch of wanted items: the full pipeline (profile gates, provider
search, upgrade decision) executes, but nothing is written to disk or the DB
at the found paths. Each item's pre-run status is restored afterwards so a
preview never leaves rows stuck in "searching" (the pipeline's first
mutation) — the same courtesy services.mt_reseek extends after its preview
call.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import current_app, jsonify, request

from routes.wanted import bp

logger = logging.getLogger(__name__)

# Provider searches take seconds per item; the route is synchronous, so cap
# the batch to keep response times reasonable.
MAX_DRY_RUN_ITEMS = 10
_DRY_RUN_WORKERS = 3


def _dry_run_one(app, item_id: int) -> dict:
    """Run one preview inside its own app context; restore the item's status."""
    with app.app_context():
        from db.wanted import get_wanted_item, update_wanted_status
        from wanted_search import process_wanted_item

        item = get_wanted_item(item_id)
        if not item:
            return {"wanted_id": item_id, "status": "error", "error": "Item not found"}
        prior_status = item.get("status")

        try:
            result = process_wanted_item(item_id, dry_run=True)
        except Exception as exc:
            logger.exception("Dry run failed for wanted %d", item_id)
            result = {"wanted_id": item_id, "status": "error", "error": str(exc)}
        finally:
            # The pipeline bumps status to "searching" before it can know it
            # is a preview. Put back whatever was there — unless a pre-flight
            # gate legitimately resolved the row (e.g. sidecar already
            # present deletes it), in which case there is nothing to restore.
            try:
                if prior_status and get_wanted_item(item_id):
                    update_wanted_status(item_id, prior_status)
            except Exception:
                logger.debug("Could not restore status for wanted %d", item_id, exc_info=True)

        result.setdefault("dry_run", True)
        return result


@bp.route("/wanted/dry-run", methods=["POST"])
def wanted_dry_run():
    """Preview which subtitles the pipeline would download for wanted items.
    ---
    post:
      tags:
        - Wanted
      summary: Dry-run wanted items
      description: >
        Runs the full search pipeline for up to 10 wanted items WITHOUT
        writing anything: providers are queried for real, but no subtitle is
        saved, no history is recorded, and the wanted rows keep their status.
        Returns per-item results with the provider, score, format and output
        path that a real run would produce.
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
                  maxItems: 10
      responses:
        200:
          description: Per-item dry-run results
          content:
            application/json:
              schema:
                type: object
                properties:
                  results:
                    type: array
                    items:
                      type: object
        400:
          description: Invalid request body
    """
    data = request.get_json(force=True, silent=True) or {}
    item_ids = data.get("item_ids")
    if not isinstance(item_ids, list) or not item_ids:
        return jsonify({"error": "item_ids (non-empty list) is required"}), 400
    try:
        item_ids = [int(i) for i in item_ids]
    except (TypeError, ValueError):
        return jsonify({"error": "item_ids must be integers"}), 400
    if len(item_ids) > MAX_DRY_RUN_ITEMS:
        return jsonify({"error": f"At most {MAX_DRY_RUN_ITEMS} items per dry run"}), 400

    app = current_app._get_current_object()
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=min(_DRY_RUN_WORKERS, len(item_ids))) as executor:
        futures = {executor.submit(_dry_run_one, app, item_id): item_id for item_id in item_ids}
        for future in as_completed(futures):
            item_id = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:
                logger.exception("Dry-run worker crashed for wanted %d", item_id)
                results.append({"wanted_id": item_id, "status": "error", "error": str(exc)})

    # Preserve the request order — as_completed returns in finish order.
    order = {item_id: idx for idx, item_id in enumerate(item_ids)}
    results.sort(key=lambda r: order.get(r.get("wanted_id"), len(order)))
    return jsonify({"results": results}), 200
