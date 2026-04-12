"""Profile routes — /language-profiles/*, /glossary/*, /prompt-presets/*."""

import logging

from flask import Blueprint, Response, jsonify, request

from cache_response import cached_get, invalidate_response_cache
from services.profile_service import (
    ProfileConflictError,
    ProfileNotFoundError,
    ProfileValidationError,
    assign_profile_to_item,
    create_glossary,
    create_preset,
    create_profile,
    delete_glossary,
    delete_preset,
    delete_profile,
    export_glossary_as_tsv,
    set_default_for_all,
    update_glossary,
    update_preset,
    update_profile,
)

bp = Blueprint("profiles", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)


@bp.route("/language-profiles", methods=["GET"])
@cached_get(ttl_seconds=60)
def list_language_profiles():
    """Get all language profiles.
    ---
    get:
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


@bp.route("/language-profiles/<int:profile_id>/set-as-default-for-all", methods=["POST"])
def set_profile_as_default_for_all_endpoint(profile_id):
    """Set a profile as the global default and remove all explicit item assignments.

    Marks this profile as is_default=1, clears is_default on all others, and
    removes all series_language_profiles / movie_language_profiles rows so every
    item falls back to the new default profile.
    ---
    post:
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


# ─── Glossary Endpoints ──────────────────────────────────────────────────────


@bp.route("/glossary", methods=["GET"])
def list_glossary():
    """Get glossary entries for a series or global glossary.
    ---
    get:
      tags:
        - Profiles
      summary: List glossary entries
      description: >
        Returns glossary entries. When series_id is provided, returns per-series
        entries. When omitted, returns global glossary entries.
        Optionally filter by search query.
      parameters:
        - in: query
          name: series_id
          schema:
            type: integer
          description: Series ID for per-series entries. Omit for global glossary.
        - in: query
          name: query
          schema:
            type: string
          description: Search filter for glossary terms
      responses:
        200:
          description: Glossary entries
          content:
            application/json:
              schema:
                type: object
                properties:
                  entries:
                    type: array
                    items:
                      type: object
                  series_id:
                    type: integer
                    nullable: true
    """
    from db.translation import get_glossary_entries, search_glossary_terms

    series_id = request.args.get("series_id", type=int)
    query = request.args.get("query", "").strip()

    if query:
        entries = search_glossary_terms(series_id, query)
    else:
        entries = get_glossary_entries(series_id)

    return jsonify({"entries": entries, "series_id": series_id})


@bp.route("/glossary", methods=["POST"])
def create_glossary_entry():
    """Create a new glossary entry (per-series or global).
    ---
    post:
      tags:
        - Profiles
      summary: Create a glossary entry
      description: >
        Adds a new source-to-target term mapping for translation consistency.
        Omit or set series_id to null for a global glossary entry.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - source_term
                - target_term
              properties:
                series_id:
                  type: integer
                  nullable: true
                  description: Omit or null for global glossary entry
                source_term:
                  type: string
                target_term:
                  type: string
                notes:
                  type: string
      responses:
        201:
          description: Entry created
          content:
            application/json:
              schema:
                type: object
        400:
          description: Missing required fields
    """
    try:
        entry = create_glossary(request.get_json() or {})
    except ProfileValidationError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(entry), 201


@bp.route("/glossary/<int:entry_id>", methods=["PUT"])
def update_glossary_entry_endpoint(entry_id):
    """Update a glossary entry.
    ---
    put:
      tags:
        - Profiles
      summary: Update a glossary entry
      description: Updates an existing glossary entry. Only provided fields are changed.
      parameters:
        - in: path
          name: entry_id
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
                source_term:
                  type: string
                target_term:
                  type: string
                notes:
                  type: string
      responses:
        200:
          description: Updated entry
          content:
            application/json:
              schema:
                type: object
        400:
          description: No fields to update
        404:
          description: Entry not found
    """
    try:
        entry = update_glossary(entry_id, request.get_json() or {})
    except ProfileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except ProfileValidationError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(entry)


@bp.route("/glossary/<int:entry_id>", methods=["DELETE"])
def delete_glossary_entry_endpoint(entry_id):
    """Delete a glossary entry.
    ---
    delete:
      tags:
        - Profiles
      summary: Delete a glossary entry
      description: Removes a glossary entry by ID.
      parameters:
        - in: path
          name: entry_id
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Entry deleted
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
          description: Entry not found
    """
    try:
        result = delete_glossary(entry_id)
    except ProfileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404

    return jsonify(result)


@bp.route("/glossary/export", methods=["GET"])
def export_glossary_tsv():
    """Export glossary entries as a TSV file download.
    ---
    get:
      tags:
        - Profiles
      summary: Export glossary as TSV
      description: >
        Downloads all glossary entries as a tab-separated values file.
        When series_id is provided, exports only entries for that series.
        When omitted, exports the global glossary.
      parameters:
        - in: query
          name: series_id
          schema:
            type: integer
          description: Series ID for per-series entries. Omit for global glossary.
      responses:
        200:
          description: TSV file download
          content:
            text/tab-separated-values:
              schema:
                type: string
    """
    series_id = request.args.get("series_id", type=int)
    tsv_content, filename = export_glossary_as_tsv(series_id)

    return Response(
        tsv_content,
        status=200,
        mimetype="text/tab-separated-values; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─── Prompt Presets Endpoints ────────────────────────────────────────────────


@bp.route("/prompt-presets", methods=["GET"])
def list_prompt_presets():
    """Get all prompt presets.
    ---
    get:
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
