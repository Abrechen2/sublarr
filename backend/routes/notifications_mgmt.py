"""Notification management routes -- templates, quiet hours, history, event filters.

Blueprint for /api/v1/notifications/* endpoints providing full CRUD
for notification templates, quiet hours, notification history with re-send,
event filters, and template variable discovery.
"""

import json
import logging

from flask import Blueprint, jsonify, request

bp = Blueprint("notifications_mgmt", __name__, url_prefix="/api/v1/notifications")
logger = logging.getLogger(__name__)


def _validate_jinja2_syntax(template_str: str) -> str | None:
    """Validate Jinja2 template syntax.

    Returns:
        None if valid, error message string if invalid.
    """
    if not template_str:
        return None
    try:
        from jinja2 import Environment
        Environment(autoescape=True).parse(template_str)
        return None
    except Exception as e:
        return str(e)


# ---- Template CRUD ----------------------------------------------------------

@bp.route("/templates", methods=["GET"])
def list_templates():
    """List all notification templates.
    ---
    get:
      tags:
        - Notifications
      summary: List notification templates
      description: Returns all notification templates, optionally filtered by event type.
      parameters:
        - in: query
          name: event_type
          schema:
            type: string
          description: Filter by event type
      responses:
        200:
          description: List of templates
    """
    from db.repositories.notifications import NotificationRepository

    event_type = request.args.get("event_type")
    repo = NotificationRepository()
    templates = repo.get_templates(event_type=event_type)
    return jsonify(templates)


@bp.route("/templates", methods=["POST"])
def create_template():
    """Create a new notification template.
    ---
    post:
      tags:
        - Notifications
      summary: Create notification template
      description: Creates a new template with Jinja2 syntax validation.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - name
              properties:
                name:
                  type: string
                title_template:
                  type: string
                body_template:
                  type: string
                event_type:
                  type: string
                service_name:
                  type: string
                enabled:
                  type: integer
      responses:
        201:
          description: Template created
        400:
          description: Validation error
    """
    from db.repositories.notifications import NotificationRepository

    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    title_template = data.get("title_template", "")
    body_template = data.get("body_template", "")

    # Validate Jinja2 syntax
    title_err = _validate_jinja2_syntax(title_template)
    if title_err:
        return jsonify({"error": f"Invalid title template: {title_err}"}), 400

    body_err = _validate_jinja2_syntax(body_template)
    if body_err:
        return jsonify({"error": f"Invalid body template: {body_err}"}), 400

    repo = NotificationRepository()
    template = repo.create_template(
        name=name,
        title_template=title_template,
        body_template=body_template,
        event_type=data.get("event_type"),
        service_name=data.get("service_name"),
        enabled=data.get("enabled", 1),
    )
    return jsonify(template), 201


@bp.route("/templates/<int:template_id>", methods=["GET"])
def get_template(template_id):
    """Get a single notification template.
    ---
    get:
      tags:
        - Notifications
      summary: Get notification template
      parameters:
        - in: path
          name: template_id
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Template details
        404:
          description: Not found
    """
    from db.repositories.notifications import NotificationRepository

    repo = NotificationRepository()
    template = repo.get_template(template_id)
    if template is None:
        return jsonify({"error": "Template not found"}), 404
    return jsonify(template)


@bp.route("/templates/<int:template_id>", methods=["PUT"])
def update_template(template_id):
    """Update a notification template.
    ---
    put:
      tags:
        - Notifications
      summary: Update notification template
      parameters:
        - in: path
          name: template_id
          required: true
          schema:
            type: integer
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
      responses:
        200:
          description: Template updated
        400:
          description: Validation error
        404:
          description: Not found
    """
    from db.repositories.notifications import NotificationRepository

    data = request.get_json(silent=True) or {}

    # Validate Jinja2 syntax if templates provided
    if "title_template" in data:
        err = _validate_jinja2_syntax(data["title_template"])
        if err:
            return jsonify({"error": f"Invalid title template: {err}"}), 400

    if "body_template" in data:
        err = _validate_jinja2_syntax(data["body_template"])
        if err:
            return jsonify({"error": f"Invalid body template: {err}"}), 400

    repo = NotificationRepository()
    # Filter to only allowed update fields
    allowed = {"name", "title_template", "body_template", "event_type",
               "service_name", "enabled"}
    update_data = {k: v for k, v in data.items() if k in allowed}

    result = repo.update_template(template_id, **update_data)
    if result is None:
        return jsonify({"error": "Template not found"}), 404
    return jsonify(result)


@bp.route("/templates/<int:template_id>", methods=["DELETE"])
def delete_template(template_id):
    """Delete a notification template.
    ---
    delete:
      tags:
        - Notifications
      summary: Delete notification template
      parameters:
        - in: path
          name: template_id
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Template deleted
        404:
          description: Not found
    """
    from db.repositories.notifications import NotificationRepository

    repo = NotificationRepository()
    deleted = repo.delete_template(template_id)
    if not deleted:
        return jsonify({"error": "Template not found"}), 404
    return jsonify({"success": True})


@bp.route("/templates/<int:template_id>/preview", methods=["POST"])
def preview_template(template_id):
    """Preview a template rendered with sample data.
    ---
    post:
      tags:
        - Notifications
      summary: Preview template rendering
      description: Renders a template with sample payload data from EVENT_CATALOG.
      parameters:
        - in: path
          name: template_id
          required: true
          schema:
            type: integer
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                variables:
                  type: object
                  description: Optional custom variables to override sample data
      responses:
        200:
          description: Rendered title and body
        404:
          description: Template not found
        400:
          description: Rendering error
    """
    from db.repositories.notifications import NotificationRepository
    from notifier import get_sample_payload, render_template

    repo = NotificationRepository()
    template = repo.get_template(template_id)
    if template is None:
        return jsonify({"error": "Template not found"}), 404

    # Get sample payload for the template's event type
    event_type = template.get("event_type", "")
    sample_vars = get_sample_payload(event_type) if event_type else {}

    # Allow custom variable overrides from request body
    data = request.get_json(silent=True) or {}
    custom_vars = data.get("variables", {})
    variables = {**sample_vars, **custom_vars}

    try:
        rendered_title = render_template(template["title_template"], variables)
        rendered_body = render_template(template["body_template"], variables)
    except Exception as e:
        return jsonify({"error": f"Template rendering failed: {e}"}), 400

    return jsonify({
        "title": rendered_title,
        "body": rendered_body,
        "variables_used": variables,
    })


# ---- Template Variables -----------------------------------------------------

@bp.route("/variables", methods=["GET"])
def list_variables():
    """List all available template variables grouped by event type.
    ---
    get:
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

    return jsonify({
        "event_type": event_type,
        "label": meta.get("label", event_type),
        "description": meta.get("description", ""),
        "variables": meta.get("payload_keys", []),
    })


# ---- Quiet Hours ------------------------------------------------------------

@bp.route("/quiet-hours", methods=["GET"])
def list_quiet_hours():
    """List all quiet hours configurations.
    ---
    get:
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

    # Validate time format HH:MM
    import re
    time_pattern = re.compile(r"^\d{2}:\d{2}$")
    if not time_pattern.match(start_time):
        return jsonify({"error": "start_time must be in HH:MM format"}), 400
    if not time_pattern.match(end_time):
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
    allowed = {"name", "start_time", "end_time", "days_of_week",
               "exception_events", "enabled"}
    update_data = {k: v for k, v in data.items() if k in allowed}

    # Validate time format if provided
    import re
    time_pattern = re.compile(r"^\d{2}:\d{2}$")
    for field in ("start_time", "end_time"):
        if field in update_data and not time_pattern.match(update_data[field]):
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


# ---- History ----------------------------------------------------------------

@bp.route("/history", methods=["GET"])
def list_history():
    """Get paginated notification history.
    ---
    get:
      tags:
        - Notifications
      summary: Get notification history
      parameters:
        - in: query
          name: page
          schema:
            type: integer
            default: 1
        - in: query
          name: per_page
          schema:
            type: integer
            default: 50
        - in: query
          name: event_type
          schema:
            type: string
      responses:
        200:
          description: Paginated notification history
    """
    from db.repositories.notifications import NotificationRepository

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    event_type = request.args.get("event_type")

    repo = NotificationRepository()
    result = repo.get_history(page=page, per_page=per_page, event_type=event_type)
    return jsonify(result)


@bp.route("/history/<int:notification_id>/resend", methods=["POST"])
def resend_notification(notification_id):
    """Re-send a historical notification.
    ---
    post:
      tags:
        - Notifications
      summary: Re-send notification
      parameters:
        - in: path
          name: notification_id
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Notification re-sent
        404:
          description: Not found
    """
    from db.repositories.notifications import NotificationRepository
    from notifier import send_notification

    repo = NotificationRepository()
    notification = repo.get_notification(notification_id)
    if notification is None:
        return jsonify({"error": "Notification not found"}), 404

    # Re-send using original title/body and event_type
    send_notification(
        title=notification["title"],
        body=notification["body"],
        event_type=notification["event_type"],
        is_manual=True,
    )
    return jsonify({"success": True, "message": "Notification re-sent"})


@bp.route("/history", methods=["DELETE"])
def clear_history():
    """Clear notification history.
    ---
    delete:
      tags:
        - Notifications
      summary: Clear notification history
      parameters:
        - in: query
          name: before_date
          schema:
            type: string
          description: Optional ISO date to clear history before
      responses:
        200:
          description: History cleared
    """
    from db.repositories.notifications import NotificationRepository

    before_date = request.args.get("before_date")
    repo = NotificationRepository()
    count = repo.clear_history(before_date=before_date)
    return jsonify({"success": True, "deleted": count})


# ---- Event Filters ----------------------------------------------------------

@bp.route("/filters", methods=["GET"])
def get_filters():
    """Get current notification event filter configuration.
    ---
    get:
      tags:
        - Notifications
      summary: Get notification filters
      description: Returns include/exclude event lists and content filters from config_entries.
      responses:
        200:
          description: Current filter config
    """
    from db.repositories.config import ConfigRepository

    config_repo = ConfigRepository()
    include_raw = config_repo.get_config_entry("notification_filter_include_events")
    exclude_raw = config_repo.get_config_entry("notification_filter_exclude_events")
    content_raw = config_repo.get_config_entry("notification_filter_content_filters")

    return jsonify({
        "include_events": json.loads(include_raw) if include_raw else [],
        "exclude_events": json.loads(exclude_raw) if exclude_raw else [],
        "content_filters": json.loads(content_raw) if content_raw else [],
    })


@bp.route("/filters", methods=["PUT"])
def update_filters():
    """Update notification event filter configuration.
    ---
    put:
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
                content_filters:
                  type: array
                  items:
                    type: object
                    properties:
                      field:
                        type: string
                      operator:
                        type: string
                      value:
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
            "notification_filter_include_events",
            json.dumps(data["include_events"])
        )

    if "exclude_events" in data:
        config_repo.save_config_entry(
            "notification_filter_exclude_events",
            json.dumps(data["exclude_events"])
        )

    if "content_filters" in data:
        config_repo.save_config_entry(
            "notification_filter_content_filters",
            json.dumps(data["content_filters"])
        )

    return jsonify({"success": True})
