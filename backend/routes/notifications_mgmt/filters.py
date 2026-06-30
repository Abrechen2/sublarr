"""Event filter configuration endpoints (include/exclude event filters)."""

from __future__ import annotations

import json

from flask import jsonify, request

from routes.notifications_mgmt import bp


@bp.route("/filters", methods=["GET"])
def get_filters():
    """Get current notification event filter configuration.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Notifications
      summary: Get notification filters
      description: Returns include/exclude event lists from config_entries.
      responses:
        200:
          description: Current filter config
    """
    from db.repositories.config import ConfigRepository

    config_repo = ConfigRepository()
    include_raw = config_repo.get_config_entry("notification_filter_include_events")
    exclude_raw = config_repo.get_config_entry("notification_filter_exclude_events")

    return jsonify(
        {
            "include_events": json.loads(include_raw) if include_raw else [],
            "exclude_events": json.loads(exclude_raw) if exclude_raw else [],
        }
    )


@bp.route("/filters", methods=["PUT"])
def update_filters():
    """Update notification event filter configuration.
    ---
    put:
      security:
        - apiKeyAuth: []
      tags:
        - Notifications
      summary: Update notification filters
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                include_events:
                  type: array
                  items:
                    type: string
                exclude_events:
                  type: array
                  items:
                    type: string
      responses:
        200:
          description: Filters updated
    """
    from db.repositories.config import ConfigRepository

    data = request.get_json(silent=True) or {}
    config_repo = ConfigRepository()

    if "include_events" in data:
        config_repo.save_config_entry(
            "notification_filter_include_events", json.dumps(data["include_events"])
        )

    if "exclude_events" in data:
        config_repo.save_config_entry(
            "notification_filter_exclude_events", json.dumps(data["exclude_events"])
        )

    return jsonify({"success": True})
