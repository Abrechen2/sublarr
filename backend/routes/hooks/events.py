"""Event catalog endpoint."""

from flask import jsonify

from routes.hooks import bp

# ---- Event Catalog -----------------------------------------------------------


@bp.route("/events/catalog", methods=["GET"])
def get_event_catalog():
    """Return the EVENT_CATALOG as a JSON list for UI dropdowns.
    ---
    get:
      tags:
        - Events
      summary: Get event catalog
      description: Returns all available event types with labels, descriptions, and payload key definitions for hook/webhook configuration.
      responses:
        200:
          description: Event catalog
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
                  properties:
                    name:
                      type: string
                    label:
                      type: string
                    description:
                      type: string
                    payload_keys:
                      type: array
                      items:
                        type: string
    """
    from events.catalog import EVENT_CATALOG

    items = []
    for name, meta in EVENT_CATALOG.items():
        items.append(
            {
                "name": name,
                "label": meta.get("label", name),
                "description": meta.get("description", ""),
                "payload_keys": meta.get("payload_keys", []),
            }
        )
    return jsonify(items)
