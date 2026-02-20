"""Filter presets routes -- /api/v1/filter-presets"""

from flask import Blueprint, request, jsonify
from db.presets import list_presets, get_preset, create_preset, update_preset, delete_preset

bp = Blueprint("filter_presets", __name__, url_prefix="/api/v1")


@bp.route("/filter-presets", methods=["GET"])
def list_filter_presets():
    """List filter presets by scope.
    ---
    get:
      tags:
        - FilterPresets
      summary: List filter presets
      description: Returns all saved filter presets for a given scope.
      parameters:
        - in: query
          name: scope
          schema:
            type: string
            default: wanted
            enum: [wanted, library, history]
          description: Page scope to filter presets by
      responses:
        200:
          description: List of presets
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
                  properties:
                    id:
                      type: integer
                    name:
                      type: string
                    scope:
                      type: string
                    conditions:
                      type: object
                    is_default:
                      type: boolean
    """
    scope = request.args.get("scope", "wanted")
    return jsonify(list_presets(scope))


@bp.route("/filter-presets", methods=["POST"])
def create_filter_preset():
    """Create a new filter preset.
    ---
    post:
      tags:
        - FilterPresets
      summary: Create filter preset
      description: Creates a new saved filter configuration with a condition tree.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [name, scope]
              properties:
                name:
                  type: string
                  description: Preset display name
                scope:
                  type: string
                  enum: [wanted, library, history]
                conditions:
                  type: object
                  description: Condition tree (AND/OR groups with field/op/value leaves)
                is_default:
                  type: boolean
                  default: false
      responses:
        201:
          description: Preset created
        400:
          description: Invalid input
        422:
          description: Condition validation failed
    """
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    scope = data.get("scope", "")
    conditions = data.get("conditions", {})
    is_default = bool(data.get("is_default", False))
    if not name or scope not in ("wanted", "library", "history"):
        return jsonify({"error": "name and valid scope required"}), 400
    try:
        preset = create_preset(name, scope, conditions, is_default)
        return jsonify(preset), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 422


@bp.route("/filter-presets/<int:preset_id>", methods=["PUT"])
def update_filter_preset(preset_id: int):
    """Update an existing filter preset.
    ---
    put:
      tags:
        - FilterPresets
      summary: Update filter preset
      description: Updates name, conditions, or default flag for an existing filter preset.
      parameters:
        - in: path
          name: preset_id
          required: true
          schema:
            type: integer
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                name:
                  type: string
                conditions:
                  type: object
                is_default:
                  type: boolean
      responses:
        200:
          description: Preset updated
        404:
          description: Preset not found
        422:
          description: Condition validation failed
    """
    data = request.get_json() or {}
    try:
        preset = update_preset(
            preset_id,
            **{k: v for k, v in data.items() if k in ("name", "conditions", "is_default")}
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 422
    if not preset:
        return jsonify({"error": "Not found"}), 404
    return jsonify(preset)


@bp.route("/filter-presets/<int:preset_id>", methods=["DELETE"])
def delete_filter_preset(preset_id: int):
    """Delete a filter preset.
    ---
    delete:
      tags:
        - FilterPresets
      summary: Delete filter preset
      description: Permanently removes a filter preset by ID.
      parameters:
        - in: path
          name: preset_id
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Preset deleted
        404:
          description: Preset not found
    """
    if not delete_preset(preset_id):
        return jsonify({"error": "Not found"}), 404
    return jsonify({"success": True})
