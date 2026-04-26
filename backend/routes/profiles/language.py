"""Language-profile endpoints: list/create/update/delete/assign + set-default."""

from __future__ import annotations

from flask import jsonify, request

from cache_response import cached_get, invalidate_response_cache
from routes.profiles import bp
from services.profile_service import (
    ProfileConflictError,
    ProfileNotFoundError,
    ProfileValidationError,
    assign_profile_to_item,
    create_profile,
    delete_profile,
    set_default_for_all,
    update_profile,
)


@bp.route("/language-profiles", methods=["GET"])
@cached_get(ttl_seconds=60)
def list_language_profiles():
    """Get all language profiles.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Profiles
      summary: List all language profiles
      description: Returns all configured language profiles including source/target languages, translation backend, and forced subtitle preference.
      responses:
        200:
          description: List of language profiles
          content:
            application/json:
              schema:
                type: object
                properties:
                  profiles:
                    type: array
                    items:
                      type: object
    """
    from db.profiles import get_all_language_profiles

    profiles = get_all_language_profiles()
    return jsonify({"profiles": profiles})


@bp.route("/language-profiles", methods=["POST"])
def create_language_profile_endpoint():
    """Create a new language profile.
    ---
    post:
      security:
        - apiKeyAuth: []
      tags:
        - Profiles
      summary: Create a language profile
      description: Creates a new language profile with source/target languages, translation backend, fallback chain, and forced subtitle preference.
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
                source_language:
                  type: string
                  default: en
                source_language_name:
                  type: string
                  default: English
                target_languages:
                  type: array
                  items:
                    type: string
                  default: ["de"]
                target_language_names:
                  type: array
                  items:
                    type: string
                  default: ["German"]
                translation_backend:
                  type: string
                  default: ollama
                fallback_chain:
                  type: array
                  items:
                    type: string
                forced_preference:
                  type: string
                  enum: [disabled, separate, auto]
                  default: disabled
      responses:
        201:
          description: Profile created
          content:
            application/json:
              schema:
                type: object
        400:
          description: Validation error (missing name or target languages)
        409:
          description: Profile name already exists
    """
    try:
        profile = create_profile(request.get_json() or {})
    except ProfileValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except ProfileConflictError as exc:
        return jsonify({"error": str(exc)}), 409
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    invalidate_response_cache()
    return jsonify(profile), 201


@bp.route("/language-profiles/<int:profile_id>", methods=["PUT"])
def update_language_profile_endpoint(profile_id):
    """Update a language profile.
    ---
    put:
      security:
        - apiKeyAuth: []
      tags:
        - Profiles
      summary: Update a language profile
      description: Updates an existing language profile. Only provided fields are changed.
      parameters:
        - in: path
          name: profile_id
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
                source_language:
                  type: string
                source_language_name:
                  type: string
                target_languages:
                  type: array
                  items:
                    type: string
                target_language_names:
                  type: array
                  items:
                    type: string
                translation_backend:
                  type: string
                fallback_chain:
                  type: array
                  items:
                    type: string
                forced_preference:
                  type: string
                  enum: [disabled, separate, auto]
      responses:
        200:
          description: Updated profile
          content:
            application/json:
              schema:
                type: object
        400:
          description: No fields to update or invalid forced_preference
        404:
          description: Profile not found
        409:
          description: Profile name already exists
    """
    try:
        updated = update_profile(profile_id, request.get_json() or {})
    except ProfileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except ProfileValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except ProfileConflictError as exc:
        return jsonify({"error": str(exc)}), 409
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    invalidate_response_cache()
    return jsonify(updated)


@bp.route("/language-profiles/<int:profile_id>", methods=["DELETE"])
def delete_language_profile_endpoint(profile_id):
    """Delete a language profile (cannot delete default).
    ---
    delete:
      security:
        - apiKeyAuth: []
      tags:
        - Profiles
      summary: Delete a language profile
      description: Deletes a language profile by ID. The default profile cannot be deleted.
      parameters:
        - in: path
          name: profile_id
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Profile deleted
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  id:
                    type: integer
        400:
          description: Profile not found or is the default profile
    """
    try:
        result = delete_profile(profile_id)
    except ProfileNotFoundError:
        return jsonify({"error": "Profile not found or is the default profile"}), 400

    invalidate_response_cache()
    return jsonify(result)


@bp.route("/language-profiles/assign", methods=["PUT"])
def assign_profile():
    """Assign a language profile to a series or movie.

    Body: { type: "series"|"movie", arr_id: int, profile_id: int }
    ---
    put:
      security:
        - apiKeyAuth: []
      tags:
        - Profiles
      summary: Assign profile to series or movie
      description: Assigns a language profile to a specific series or movie by Arr ID.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - type
                - arr_id
                - profile_id
              properties:
                type:
                  type: string
                  enum: [series, movie]
                arr_id:
                  type: integer
                profile_id:
                  type: integer
      responses:
        200:
          description: Profile assigned
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  type:
                    type: string
                  arr_id:
                    type: integer
                  profile_id:
                    type: integer
        400:
          description: Missing required fields or invalid type
        404:
          description: Profile not found
    """
    try:
        result = assign_profile_to_item(request.get_json() or {})
    except ProfileValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    except ProfileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404

    return jsonify(result)


@bp.route("/language-profiles/assign-bulk", methods=["PUT"])
def assign_profile_bulk():
    """Bulk assign a language profile to multiple series or movies.

    Body: { type: "series"|"movie", arr_ids: [int], profile_id: int }
    Returns: { assigned: int, failed: [{arr_id, error}] }
    ---
    put:
      security:
        - apiKeyAuth: []
      tags:
        - Profiles
      summary: Bulk assign a language profile
      description: Assigns a language profile to multiple series or movies in one call.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - type
                - arr_ids
                - profile_id
              properties:
                type:
                  type: string
                  enum: [series, movie]
                arr_ids:
                  type: array
                  items:
                    type: integer
                profile_id:
                  type: integer
      responses:
        200:
          description: Result with per-item success/failure counts
          content:
            application/json:
              schema:
                type: object
                properties:
                  assigned:
                    type: integer
                  failed:
                    type: array
                    items:
                      type: object
        400:
          description: Missing or invalid required fields
    """
    data = request.get_json() or {}
    item_type = data.get("type")
    arr_ids = data.get("arr_ids")
    profile_id = data.get("profile_id")

    if item_type not in {"series", "movie"} or not isinstance(arr_ids, list) or profile_id is None:
        return jsonify({"error": "type, arr_ids, profile_id are required (type ∈ {series, movie})"}), 400

    assigned = 0
    failed: list[dict] = []
    for arr_id in arr_ids:
        try:
            assign_profile_to_item({"type": item_type, "arr_id": arr_id, "profile_id": profile_id})
            assigned += 1
        except (ProfileValidationError, ProfileNotFoundError) as exc:
            failed.append({"arr_id": arr_id, "error": str(exc)})
    return jsonify({"assigned": assigned, "failed": failed})


@bp.route("/language-profiles/<int:profile_id>/set-as-default-for-all", methods=["POST"])
def set_profile_as_default_for_all_endpoint(profile_id):
    """Set a profile as the global default and remove all explicit item assignments.

    Marks this profile as is_default=1, clears is_default on all others, and
    removes all series_language_profiles / movie_language_profiles rows so every
    item falls back to the new default profile.
    ---
    post:
      security:
        - apiKeyAuth: []
      tags:
        - Profiles
      summary: Set profile as default for all items
      description: Sets the given profile as the global default and clears all explicit series/movie profile assignments.
      responses:
        200:
          description: Profile set as default for all items
        404:
          description: Profile not found
    """
    try:
        result = set_default_for_all(profile_id)
    except ProfileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404

    invalidate_response_cache()
    return jsonify(result)
