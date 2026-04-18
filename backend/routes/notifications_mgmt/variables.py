"""Template variable discovery endpoints (from EVENT_CATALOG)."""

from __future__ import annotations

from flask import jsonify

from routes.notifications_mgmt import bp


@bp.route("/variables", methods=["GET"])
def list_variables():
    """List all available template variables grouped by event type.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Notifications
      summary: List template variables
      description: Returns available Jinja2 variables grouped by event type from EVENT_CATALOG.
      responses:
        200:
          description: Variables grouped by event type
    """
    from events.catalog import EVENT_CATALOG

    result = {}
    for name, meta in EVENT_CATALOG.items():
        result[name] = {
            "label": meta.get("label", name),
            "description": meta.get("description", ""),
            "variables": meta.get("payload_keys", []),
        }
    return jsonify(result)


@bp.route("/variables/<event_type>", methods=["GET"])
def get_variables(event_type):
    """Get template variables for a specific event type.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Notifications
      summary: Get event variables
      parameters:
        - in: path
          name: event_type
          required: true
          schema:
            type: string
      responses:
        200:
          description: Variables for event type
        404:
          description: Event type not found
    """
    from events.catalog import EVENT_CATALOG

    meta = EVENT_CATALOG.get(event_type)
    if meta is None:
        return jsonify({"error": f"Unknown event type: {event_type}"}), 404

    return jsonify(
        {
            "event_type": event_type,
            "label": meta.get("label", event_type),
            "description": meta.get("description", ""),
            "variables": meta.get("payload_keys", []),
        }
    )
