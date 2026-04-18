"""Prompt-preset endpoints for LLM translation: list / default / create / update / delete."""

from __future__ import annotations

from flask import jsonify, request

from routes.profiles import bp
from services.profile_service import (
    ProfileNotFoundError,
    ProfileValidationError,
    create_preset,
    delete_preset,
    update_preset,
)


@bp.route("/prompt-presets", methods=["GET"])
def list_prompt_presets():
    """Get all prompt presets.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Profiles
      summary: List prompt presets
      description: Returns all configured prompt presets for LLM translation.
      responses:
        200:
          description: List of prompt presets
          content:
            application/json:
              schema:
                type: object
                properties:
                  presets:
                    type: array
                    items:
                      type: object
    """
    from db.translation import get_prompt_presets

    presets = get_prompt_presets()
    return jsonify({"presets": presets})


@bp.route("/prompt-presets/default", methods=["GET"])
def get_default_preset():
    """Get the default prompt preset.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Profiles
      summary: Get default prompt preset
      description: Returns the prompt preset currently marked as default.
      responses:
        200:
          description: Default preset
          content:
            application/json:
              schema:
                type: object
        404:
          description: No default preset found
    """
    from db.translation import get_default_prompt_preset

    preset = get_default_prompt_preset()
    if not preset:
        return jsonify({"error": "No default preset found"}), 404
    return jsonify(preset)


@bp.route("/prompt-presets", methods=["POST"])
def create_prompt_preset():
    """Create a new prompt preset.
    ---
    post:
      security:
        - apiKeyAuth: []
      tags:
        - Profiles
      summary: Create a prompt preset
      description: Creates a new prompt preset for LLM translation. If is_default is true, the previous default is unset.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - name
                - prompt_template
              properties:
                name:
                  type: string
                prompt_template:
                  type: string
                is_default:
                  type: boolean
                  default: false
      responses:
        201:
          description: Preset created
          content:
            application/json:
              schema:
                type: object
        400:
          description: Missing name or prompt_template
    """
    try:
        preset = create_preset(request.get_json() or {})
    except ProfileValidationError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(preset), 201


@bp.route("/prompt-presets/<int:preset_id>", methods=["PUT"])
def update_prompt_preset_endpoint(preset_id):
    """Update a prompt preset.
    ---
    put:
      security:
        - apiKeyAuth: []
      tags:
        - Profiles
      summary: Update a prompt preset
      description: Updates an existing prompt preset. If is_default is set to true, the previous default is unset.
      parameters:
        - in: path
          name: preset_id
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
                prompt_template:
                  type: string
                is_default:
                  type: boolean
      responses:
        200:
          description: Updated preset
          content:
            application/json:
              schema:
                type: object
        400:
          description: No fields to update
        404:
          description: Preset not found
    """
    try:
        preset = update_preset(preset_id, request.get_json() or {})
    except ProfileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except ProfileValidationError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(preset)


@bp.route("/prompt-presets/<int:preset_id>", methods=["DELETE"])
def delete_prompt_preset_endpoint(preset_id):
    """Delete a prompt preset.
    ---
    delete:
      security:
        - apiKeyAuth: []
      tags:
        - Profiles
      summary: Delete a prompt preset
      description: Deletes a prompt preset by ID. Cannot delete the last remaining preset.
      parameters:
        - in: path
          name: preset_id
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Preset deleted
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  id:
                    type: integer
        404:
          description: Preset not found or cannot delete last preset
    """
    try:
        result = delete_preset(preset_id)
    except ProfileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404

    return jsonify(result)
