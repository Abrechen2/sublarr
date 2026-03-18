"""Webhook config CRUD endpoints + test."""

from flask import jsonify, request

from routes.hooks import bp

# ---- Webhook Config CRUD -----------------------------------------------------


def _mask_webhook_secret(webhook: dict) -> dict:
    """Return a copy of a webhook config dict with the secret masked."""
    if webhook and webhook.get("secret"):
        return {**webhook, "secret": "***configured***"}
    return webhook


@bp.route("/webhooks", methods=["GET"])
def list_webhooks():
    """List all webhook configs, optionally filtered by event_name.
    ---
    get:
      tags:
        - Events
      summary: List outgoing webhooks
      description: Returns all outgoing webhook configurations. Optionally filter by event name.
      parameters:
        - in: query
          name: event_name
          schema:
            type: string
          description: Filter webhooks by event name
      responses:
        200:
          description: List of webhook configs
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
    """
    from db.hooks import get_webhook_configs

    event_name = request.args.get("event_name")
    configs = get_webhook_configs(event_name=event_name)
    return jsonify([_mask_webhook_secret(w) for w in configs])


@bp.route("/webhooks", methods=["POST"])
def create_webhook():
    """Create a new webhook config.
    ---
    post:
      tags:
        - Events
      summary: Create an outgoing webhook
      description: Creates a new outgoing webhook that sends HTTP POST requests when events fire. Use '*' for event_name to receive all events.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - name
                - event_name
                - url
              properties:
                name:
                  type: string
                event_name:
                  type: string
                  description: Event name from catalog, or '*' for all events
                url:
                  type: string
                  description: Must start with http:// or https://
                secret:
                  type: string
                  description: HMAC signing secret for payload verification
                retry_count:
                  type: integer
                  default: 3
                timeout_seconds:
                  type: integer
                  default: 10
      responses:
        201:
          description: Webhook created
          content:
            application/json:
              schema:
                type: object
        400:
          description: Validation error
    """
    from db.hooks import create_webhook_config
    from events.catalog import EVENT_CATALOG

    data = request.get_json(silent=True) or {}

    name = data.get("name", "").strip()
    event_name = data.get("event_name", "").strip()
    url = data.get("url", "").strip()
    secret = data.get("secret", "")
    retry_count = int(data.get("retry_count", 3))
    timeout_seconds = int(data.get("timeout_seconds", 10))

    if not name:
        return jsonify({"error": "name is required"}), 400
    if not event_name:
        return jsonify({"error": "event_name is required"}), 400
    if event_name != "*" and event_name not in EVENT_CATALOG:
        return jsonify({"error": "event_name must be a valid event or '*' for all events"}), 400
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return jsonify({"error": "url is required and must start with http:// or https://"}), 400

    webhook = create_webhook_config(name, event_name, url, secret, retry_count, timeout_seconds)
    return jsonify(_mask_webhook_secret(webhook)), 201


@bp.route("/webhooks/<int:webhook_id>", methods=["GET"])
def get_webhook(webhook_id):
    """Get a single webhook config by ID.
    ---
    get:
      tags:
        - Events
      summary: Get webhook config
      description: Returns a single outgoing webhook configuration by ID.
      parameters:
        - in: path
          name: webhook_id
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Webhook config
          content:
            application/json:
              schema:
                type: object
        404:
          description: Webhook not found
    """
    from db.hooks import get_webhook_config

    webhook = get_webhook_config(webhook_id)
    if webhook is None:
        return jsonify({"error": "Webhook not found"}), 404
    return jsonify(_mask_webhook_secret(webhook))


@bp.route("/webhooks/<int:webhook_id>", methods=["PUT"])
def update_webhook(webhook_id):
    """Update a webhook config.
    ---
    put:
      tags:
        - Events
      summary: Update an outgoing webhook
      description: Updates an existing outgoing webhook configuration. Only provided fields are changed.
      parameters:
        - in: path
          name: webhook_id
          required: true
          schema:
            type: integer
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                name:
                  type: string
                event_name:
                  type: string
                url:
                  type: string
                secret:
                  type: string
                retry_count:
                  type: integer
                timeout_seconds:
                  type: integer
                enabled:
                  type: boolean
      responses:
        200:
          description: Updated webhook config
          content:
            application/json:
              schema:
                type: object
        404:
          description: Webhook not found
    """
    from db.hooks import get_webhook_config, update_webhook_config

    webhook = get_webhook_config(webhook_id)
    if webhook is None:
        return jsonify({"error": "Webhook not found"}), 404

    data = request.get_json(silent=True) or {}
    allowed_keys = {
        "name",
        "event_name",
        "url",
        "secret",
        "retry_count",
        "timeout_seconds",
        "enabled",
    }
    updates = {k: v for k, v in data.items() if k in allowed_keys}

    if "enabled" in updates:
        updates["enabled"] = 1 if updates["enabled"] else 0

    if updates:
        update_webhook_config(webhook_id, **updates)

    updated = get_webhook_config(webhook_id)
    return jsonify(_mask_webhook_secret(updated))


@bp.route("/webhooks/<int:webhook_id>", methods=["DELETE"])
def delete_webhook(webhook_id):
    """Delete a webhook config.
    ---
    delete:
      tags:
        - Events
      summary: Delete an outgoing webhook
      description: Deletes an outgoing webhook configuration by ID.
      parameters:
        - in: path
          name: webhook_id
          required: true
          schema:
            type: integer
      responses:
        204:
          description: Webhook deleted
    """
    from db.hooks import delete_webhook_config

    delete_webhook_config(webhook_id)
    return "", 204


@bp.route("/webhooks/<int:webhook_id>/test", methods=["POST"])
def test_webhook(webhook_id):
    """Test-fire a webhook with sample payload (blocking).
    ---
    post:
      tags:
        - Events
      summary: Test an outgoing webhook
      description: Sends a test HTTP POST to the webhook URL with sample payload and returns the result. Wildcards use 'config_updated' as the sample event.
      parameters:
        - in: path
          name: webhook_id
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Test result with status code and response
          content:
            application/json:
              schema:
                type: object
                properties:
                  success:
                    type: boolean
                  status_code:
                    type: integer
                  error:
                    type: string
                  duration_ms:
                    type: number
        404:
          description: Webhook not found
    """
    from db.hooks import get_webhook_config
    from events.catalog import EVENT_CATALOG
    from events.webhooks import WebhookDispatcher

    webhook = get_webhook_config(webhook_id)
    if webhook is None:
        return jsonify({"error": "Webhook not found"}), 404

    event_name = webhook.get("event_name", "")
    if event_name == "*":
        event_name = "config_updated"
    catalog_entry = EVENT_CATALOG.get(event_name, {})
    payload_keys = catalog_entry.get("payload_keys", [])
    sample_payload = {key: "test_value" for key in payload_keys}

    dispatcher = WebhookDispatcher()
    result = dispatcher.send_webhook(webhook, event_name, sample_payload)
    return jsonify(result)
