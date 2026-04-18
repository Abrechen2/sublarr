"""Notification template CRUD + preview."""

from __future__ import annotations

from flask import jsonify, request

from routes.notifications_mgmt import bp


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


@bp.route("/templates", methods=["GET"])
def list_templates():
    """List all notification templates.
    ---
    get:
      security:
        - apiKeyAuth: []
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
      security:
        - apiKeyAuth: []
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
      security:
        - apiKeyAuth: []
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
      security:
        - apiKeyAuth: []
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
    allowed = {"name", "title_template", "body_template", "event_type", "service_name", "enabled"}
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
      security:
        - apiKeyAuth: []
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
      security:
        - apiKeyAuth: []
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

    return jsonify(
        {
            "title": rendered_title,
            "body": rendered_body,
            "variables_used": variables,
        }
    )
