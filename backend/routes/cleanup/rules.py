"""Cleanup-rule CRUD + run + preview routes."""

import json
import logging

from flask import jsonify, request

from error_utils import handle_api_error
from routes.cleanup import bp

logger = logging.getLogger(__name__)


@bp.route("/rules", methods=["GET"])
def list_rules():
    """List all cleanup rules.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Cleanup
      summary: List cleanup rules
      description: Returns all configured cleanup rules.
      responses:
        200:
          description: Cleanup rules
          content:
            application/json:
              schema:
                type: object
                properties:
                  rules:
                    type: array
    """
    from db.repositories.cleanup import CleanupRepository

    repo = CleanupRepository()
    rules = repo.get_rules()
    return jsonify({"rules": rules})


@bp.route("/rules", methods=["POST"])
def create_rule():
    """Create a new cleanup rule.
    ---
    post:
      security:
        - apiKeyAuth: []
      tags:
        - Cleanup
      summary: Create cleanup rule
      description: Creates a new cleanup rule with the specified type and configuration.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - name
                - rule_type
              properties:
                name:
                  type: string
                  maxLength: 100
                rule_type:
                  type: string
                  enum: [dedup, orphaned, old_backups]
                config_json:
                  type: string
                  default: "{}"
                enabled:
                  type: boolean
                  default: true
      responses:
        201:
          description: Rule created
        400:
          description: Invalid parameters
    """
    from db.repositories.cleanup import CleanupRepository

    data = request.get_json() or {}
    name = data.get("name", "").strip()
    rule_type = data.get("rule_type", "").strip()
    config_json = data.get("config_json", "{}")
    enabled = data.get("enabled", True)
    schedule = data.get("schedule", "manual")

    if not name:
        return jsonify({"error": "name is required"}), 400

    valid_types = {
        "dedup",
        "orphaned",
        "old_backups",
        "language_filter",
        "format_upgrade",
        "orphan_files",
        "orphan_db",
    }
    if rule_type not in valid_types:
        return jsonify({"error": f"rule_type must be one of: {sorted(valid_types)}"}), 400

    # Validate config_json is valid JSON
    try:
        json.loads(config_json) if isinstance(config_json, str) else config_json
    except (json.JSONDecodeError, TypeError):
        return jsonify({"error": "config_json must be valid JSON"}), 400

    if isinstance(config_json, dict):
        config_json = json.dumps(config_json)

    repo = CleanupRepository()
    rule = repo.create_rule(
        name=name,
        rule_type=rule_type,
        config_json=config_json,
        enabled=enabled,
        schedule=schedule,
    )

    return jsonify(rule), 201


@bp.route("/rules/<int:rule_id>", methods=["PUT"])
def update_rule(rule_id: int):
    """Update a cleanup rule.
    ---
    put:
      security:
        - apiKeyAuth: []
      tags:
        - Cleanup
      summary: Update cleanup rule
      description: Updates an existing cleanup rule.
      parameters:
        - in: path
          name: rule_id
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
                rule_type:
                  type: string
                  enum: [dedup, orphaned, old_backups, language_filter, format_upgrade, orphan_files, orphan_db]
                config_json:
                  type: string
                enabled:
                  type: boolean
                schedule:
                  type: string
                  enum: [manual, daily, weekly, after_scan]
      responses:
        200:
          description: Rule updated
        404:
          description: Rule not found
    """
    from db.repositories.cleanup import CleanupRepository

    data = request.get_json() or {}

    # Validate config_json if provided
    if "config_json" in data:
        cfg = data["config_json"]
        try:
            json.loads(cfg) if isinstance(cfg, str) else cfg
        except (json.JSONDecodeError, TypeError):
            return jsonify({"error": "config_json must be valid JSON"}), 400
        if isinstance(cfg, dict):
            data["config_json"] = json.dumps(cfg)

    repo = CleanupRepository()
    result = repo.update_rule(rule_id, **data)

    if result is None:
        return jsonify({"error": "Rule not found"}), 404

    return jsonify(result)


@bp.route("/rules/<int:rule_id>", methods=["DELETE"])
def delete_rule(rule_id: int):
    """Delete a cleanup rule.
    ---
    delete:
      security:
        - apiKeyAuth: []
      tags:
        - Cleanup
      summary: Delete cleanup rule
      description: Deletes a cleanup rule by ID.
      parameters:
        - in: path
          name: rule_id
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Rule deleted
        404:
          description: Rule not found
    """
    from db.repositories.cleanup import CleanupRepository

    repo = CleanupRepository()
    deleted = repo.delete_rule(rule_id)

    if not deleted:
        return jsonify({"error": "Rule not found"}), 404

    return jsonify({"status": "deleted", "id": rule_id})


@bp.route("/rules/<int:rule_id>/run", methods=["POST"])
@handle_api_error("Rule execution failed")
def run_rule(rule_id: int):
    """Execute a cleanup rule manually.
    ---
    post:
      security:
        - apiKeyAuth: []
      tags:
        - Cleanup
      summary: Run cleanup rule
      description: Manually executes a cleanup rule and returns the result.
      parameters:
        - in: path
          name: rule_id
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Rule execution result
        404:
          description: Rule not found
        500:
          description: Execution error
    """
    from extensions import socketio
    from services.cleanup_rule_runner import execute_rule

    try:
        result = execute_rule(rule_id, socketio=socketio)
        return jsonify(result)
    except ValueError as e:
        code = 404 if "not found" in str(e) else 400
        return jsonify({"error": str(e)}), code
    except Exception as e:
        logger.error("Rule %d failed: %s", rule_id, e)
        return jsonify({"error": str(e)}), 500


@bp.route("/rules/<int:rule_id>/preview", methods=["POST"])
def preview_rule_endpoint(rule_id: int):
    """Dry-run a cleanup rule — return what would be deleted without deleting.
    ---
    post:
      security:
        - apiKeyAuth: []
      tags:
        - Cleanup
      summary: Preview cleanup rule
      description: Runs a cleanup rule in dry-run mode and returns what would be affected without making any changes.
      parameters:
        - in: path
          name: rule_id
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Preview results
        404:
          description: Rule not found
        400:
          description: Preview not supported for rule type
        500:
          description: Preview error
    """
    from services.cleanup_rule_runner import preview_rule

    try:
        result = preview_rule(rule_id)
        return jsonify(result)
    except ValueError as e:
        code = 404 if "not found" in str(e) else 400
        return jsonify({"error": str(e)}), code
    except Exception as e:
        logger.error("Preview for rule %d failed: %s", rule_id, e)
        return jsonify({"error": str(e)}), 500
