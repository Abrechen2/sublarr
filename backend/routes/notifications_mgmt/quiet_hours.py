"""Quiet hours configuration CRUD."""

from __future__ import annotations

import re

from flask import jsonify, request

from routes.notifications_mgmt import bp

_TIME_PATTERN = re.compile(r"^\d{2}:\d{2}$")


@bp.route("/quiet-hours", methods=["GET"])
def list_quiet_hours():
    """List all quiet hours configurations.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Notifications
      summary: List quiet hours configs
      responses:
        200:
          description: List of quiet hours configs
    """
    from db.repositories.notifications import NotificationRepository

    repo = NotificationRepository()
    configs = repo.get_quiet_hours_configs()
    return jsonify(configs)


@bp.route("/quiet-hours", methods=["POST"])
def create_quiet_hours():
    """Create a quiet hours configuration.
    ---
    post:
      security:
        - apiKeyAuth: []
      tags:
        - Notifications
      summary: Create quiet hours config
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - name
                - start_time
                - end_time
              properties:
                name:
                  type: string
                start_time:
                  type: string
                  description: "HH:MM format"
                end_time:
                  type: string
                  description: "HH:MM format"
                days_of_week:
                  type: string
                  description: JSON array of day numbers (0=Monday)
                exception_events:
                  type: string
                  description: JSON array of event types that bypass quiet hours
                enabled:
                  type: integer
      responses:
        201:
          description: Quiet hours config created
        400:
          description: Validation error
    """
    from db.repositories.notifications import NotificationRepository

    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    start_time = data.get("start_time", "").strip()
    end_time = data.get("end_time", "").strip()

    if not name:
        return jsonify({"error": "name is required"}), 400
    if not start_time or not end_time:
        return jsonify({"error": "start_time and end_time are required"}), 400

    if not _TIME_PATTERN.match(start_time):
        return jsonify({"error": "start_time must be in HH:MM format"}), 400
    if not _TIME_PATTERN.match(end_time):
        return jsonify({"error": "end_time must be in HH:MM format"}), 400

    repo = NotificationRepository()
    config = repo.create_quiet_hours(
        name=name,
        start_time=start_time,
        end_time=end_time,
        days_of_week=data.get("days_of_week", "[0,1,2,3,4,5,6]"),
        exception_events=data.get("exception_events", '["error"]'),
        enabled=data.get("enabled", 1),
    )
    return jsonify(config), 201


@bp.route("/quiet-hours/<int:config_id>", methods=["PUT"])
def update_quiet_hours(config_id):
    """Update a quiet hours configuration.
    ---
    put:
      security:
        - apiKeyAuth: []
      tags:
        - Notifications
      summary: Update quiet hours config
      parameters:
        - in: path
          name: config_id
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Config updated
        404:
          description: Not found
    """
    from db.repositories.notifications import NotificationRepository

    data = request.get_json(silent=True) or {}
    allowed = {"name", "start_time", "end_time", "days_of_week", "exception_events", "enabled"}
    update_data = {k: v for k, v in data.items() if k in allowed}

    # Validate time format if provided
    for field in ("start_time", "end_time"):
        if field in update_data and not _TIME_PATTERN.match(update_data[field]):
            return jsonify({"error": f"{field} must be in HH:MM format"}), 400

    repo = NotificationRepository()
    result = repo.update_quiet_hours(config_id, **update_data)
    if result is None:
        return jsonify({"error": "Quiet hours config not found"}), 404
    return jsonify(result)


@bp.route("/quiet-hours/<int:config_id>", methods=["DELETE"])
def delete_quiet_hours(config_id):
    """Delete a quiet hours configuration.
    ---
    delete:
      security:
        - apiKeyAuth: []
      tags:
        - Notifications
      summary: Delete quiet hours config
      parameters:
        - in: path
          name: config_id
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Config deleted
        404:
          description: Not found
    """
    from db.repositories.notifications import NotificationRepository

    repo = NotificationRepository()
    deleted = repo.delete_quiet_hours(config_id)
    if not deleted:
        return jsonify({"error": "Quiet hours config not found"}), 404
    return jsonify({"success": True})
